"""
OpenTelemetry instrumentation and structured request logging.

Enable with OTEL_ENABLED=true (default when using docker compose up).
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING
from app.database import db

from flask import Flask, g, request, session
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from prometheus_client import Counter, Gauge

if TYPE_CHECKING:
    from flask_sqlalchemy import SQLAlchemy

_telemetry_initialized = False

# ---- Negocio ----
products_created_total = Counter(
    "products_created_total", "Productos creados"
)
stock_movements_total = Counter(
    "stock_movements_total", "Movimientos de stock", ["type", "product"]
)
products_total = Gauge(
    "products_total", "Cantidad total de productos activos"
)    # ---- Seguridad ----
auth_failures_total = Counter(
    "auth_failures_total", "Fallos de autenticación", ["source_ip"]
)
invalid_tokens_total = Counter(
    "invalid_tokens_total", "Tokens inválidos recibidos"
)


def record_product_created() -> None:
    products_created_total.inc()


def sync_active_products_total() -> None:
    from app.products.models import Product

    products_total.set(Product.query.filter_by(status="active").count())


def record_stock_movement(movement_type: str, product_sku: str) -> None:
    stock_movements_total.labels(type=movement_type, product=product_sku).inc()


def record_auth_failure(source_ip: str | None) -> None:
    auth_failures_total.labels(source_ip=source_ip or "-").inc()


def record_invalid_token() -> None:
    invalid_tokens_total.inc()

class ContextFormatter(logging.Formatter):
    """Ensure trace/request fields exist on every log record."""

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        span_context = span.get_span_context() if span else None

        if span_context and span_context.is_valid:
            record.traceId = format(span_context.trace_id, "032x")
            record.spanId = format(span_context.span_id, "016x")
        else:
            record.traceId = getattr(record, "traceId", "-")
            record.spanId = getattr(record, "spanId", "-")

        try:
            record.correlationId = getattr(record, "correlationId", getattr(g, "correlation_id", "-"))
            record.user = getattr(record, "user", getattr(g, "user", "-"))
            record.endpoint = getattr(record, "endpoint", getattr(g, "endpoint", "-"))
        except RuntimeError:
            record.correlationId = getattr(record, "correlationId", "-")
            record.user = getattr(record, "user", "-")
            record.endpoint = getattr(record, "endpoint", "-")

        return super().format(record)


def _build_log_format() -> str:
    return (
        "%(asctime)s level=%(levelname)s "
        "traceId=%(traceId)s spanId=%(spanId)s correlationId=%(correlationId)s "
        "user=%(user)s endpoint=%(endpoint)s "
        "logger=%(name)s message=%(message)s"
    )


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = ContextFormatter(_build_log_format())

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.setFormatter(formatter)

    if os.getenv("OTEL_ENABLED", "false").lower() == "true":
        LoggingInstrumentor().instrument(set_logging_format=False)


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def _set_request_context() -> None:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        g.correlation_id = correlation_id
        g.endpoint = request.endpoint or request.path

        user_data = session.get("user", {})
        g.user = (
            user_data.get("preferred_username")
            or user_data.get("email")
            or "-"
        )

        span = trace.get_current_span()
        span_context = span.get_span_context() if span else None
        if span_context and span_context.is_valid:
            g.trace_id = format(span_context.trace_id, "032x")
            g.span_id = format(span_context.span_id, "016x")

    @app.after_request
    def _finish_request(response):
        if hasattr(g, "correlation_id"):
            response.headers["X-Correlation-ID"] = g.correlation_id

        app.logger.info(
            "request completed method=%s path=%s status=%s",
            request.method,
            request.path,
            response.status_code,
        )
        return response


def init_telemetry(app: Flask, db: SQLAlchemy) -> None:
    global _telemetry_initialized

    setup_logging()
    _register_request_hooks(app)

    if os.getenv("OTEL_ENABLED", "false").lower() != "true":
        app.logger.info("OpenTelemetry disabled (set OTEL_ENABLED=true to enable)")
        return

    if _telemetry_initialized:
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "manage-system")
    otlp_endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://alloy:4318/v1/traces",
    )

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "inventory",
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
    )
    trace.set_tracer_provider(provider)

    FlaskInstrumentor().instrument_app(app)
    LoggingInstrumentor().instrument(set_logging_format=False)

    with app.app_context():
        SQLAlchemyInstrumentor().instrument(
            engine=db.engine,
            enable_commenter=True,
        )

    _telemetry_initialized = True
    app.logger.info(
        "OpenTelemetry enabled service=%s endpoint=%s",
        service_name,
        otlp_endpoint,
    )


def init_metrics(app: Flask) -> None:
    """Expose Prometheus metrics at /metrics when prometheus_client is available."""
    if os.getenv("OTEL_ENABLED", "false").lower() != "true":
        return

    try:
        from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
    except ImportError:
        return

    request_count = Counter(
        "flask_http_request_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    request_latency = Histogram(
        "flask_http_request_duration_seconds",
        "HTTP request latency",
        ["method", "endpoint"],
    )

    db_pool_active_connections = Gauge(
        "db_pool_active_connections", "Conexiones activas del pool de DB"
    )
    db_pool_max_connections = Gauge(
        "db_pool_max_connections", "Tamaño máximo configurado del pool de DB"
    )
    
    def _pool():
        with app.app_context():
            return db.engine.pool

    db_pool_active_connections.set_function(lambda: _pool().checkedout())
    db_pool_max_connections.set_function(lambda: _pool().size())

    @app.before_request
    def _metrics_start_timer():
        g._request_start_time = __import__("time").perf_counter()

    @app.after_request
    def _metrics_record(response):
        start = getattr(g, "_request_start_time", None)
        if start is not None:
            elapsed = __import__("time").perf_counter() - start
            endpoint = request.endpoint or "unknown"
            request_latency.labels(request.method, endpoint).observe(elapsed)
            request_count.labels(request.method, endpoint, str(response.status_code)).inc()
        return response

    @app.route("/metrics")
    def metrics():
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
