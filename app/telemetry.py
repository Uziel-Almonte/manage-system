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
    """
    Qué hace: incrementa la métrica de productos creados.
    Por qué lo hace: para contar eventos de creación y exponerlos en observabilidad.
    Cómo lo hace: suma una unidad al contador Prometheus correspondiente.
    De dónde viene: la llamada viene del flujo de creación de productos en la aplicación.
    A dónde va: el valor actualizado queda disponible en las métricas exportadas.
    Librerías externas: sí, usa `prometheus_client` mediante el contador global.
    """
    products_created_total.inc()


def sync_active_products_total() -> None:
    """
    Qué hace: sincroniza el total de productos activos en una métrica Gauge.
    Por qué lo hace: para reflejar el estado actual del inventario en Prometheus.
    Cómo lo hace: consulta la base de datos con SQLAlchemy y asigna el conteo al gauge.
    De dónde viene: la llamada viene de los flujos que crean, actualizan o eliminan productos.
    A dónde va: el número queda expuesto en la métrica `products_total`.
    Librerías externas: sí, usa SQLAlchemy a través del modelo `Product` y `prometheus_client` para el gauge.
    """
    from app.products.models import Product

    products_total.set(Product.query.filter_by(status="active").count())


def record_stock_movement(movement_type: str, product_sku: str) -> None:
    """
    Qué hace: incrementa la métrica de movimientos de stock.
    Por qué lo hace: para observar entradas y salidas por tipo y producto.
    Cómo lo hace: usa etiquetas de Prometheus y suma una unidad al contador.
    De dónde viene: la llamada viene de los flujos que registran cambios de inventario.
    A dónde va: la serie temporal queda disponible en Prometheus con sus labels.
    Librerías externas: sí, usa `prometheus_client`.
    """
    stock_movements_total.labels(type=movement_type, product=product_sku).inc()


def record_auth_failure(source_ip: str | None) -> None:
    """
    Qué hace: incrementa la métrica de fallos de autenticación.
    Por qué lo hace: para monitorear intentos inválidos de acceso.
    Cómo lo hace: registra la IP de origen como etiqueta y suma una unidad.
    De dónde viene: la llamada viene de los puntos donde falla la validación de autenticación.
    A dónde va: el dato queda expuesto en la métrica `auth_failures_total`.
    Librerías externas: sí, usa `prometheus_client`.
    """
    auth_failures_total.labels(source_ip=source_ip or "-").inc()


def record_invalid_token() -> None:
    """
    Qué hace: incrementa la métrica de tokens inválidos recibidos.
    Por qué lo hace: para detectar y medir intentos con JWT incorrectos o expirados.
    Cómo lo hace: suma una unidad al contador Prometheus dedicado.
    De dónde viene: la llamada viene del flujo que valida tokens en la aplicación.
    A dónde va: el valor se expone en Prometheus para alertas u observabilidad.
    Librerías externas: sí, usa `prometheus_client`.
    """
    invalid_tokens_total.inc()

class ContextFormatter(logging.Formatter):
    """
    Qué hace: formatea logs para incluir contexto de traza y request.
    Por qué lo hace: para correlacionar logs con peticiones y spans distribuidos.
    Cómo lo hace: completa campos como traceId, spanId, correlationId, usuario y endpoint antes de delegar al formatter base.
    De dónde viene: toma información del span actual y de Flask `g`/`request`.
    A dónde va: la salida termina en el log estructurado que consume el backend de observabilidad.
    Librerías externas: sí, se apoya en `logging`, `opentelemetry` y en el contexto de Flask.
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Qué hace: inyecta campos de contexto en cada registro antes de formatearlo.
        Por qué lo hace: para que todos los logs lleven trazabilidad uniforme.
        Cómo lo hace: lee el span actual, rellena campos faltantes y maneja el caso sin contexto de request.
        De dónde viene: el contexto viene del span activo y de variables locales de Flask.
        A dónde va: devuelve un string final apto para escribir en consola o colector.
        Librerías externas: sí, usa `opentelemetry.trace` y el sistema de logging de Python.
        """
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
    """
    Qué hace: construye el patrón de formato para logs estructurados.
    Por qué lo hace: para estandarizar la salida de log de la aplicación.
    Cómo lo hace: devuelve una cadena con placeholders de campos de contexto.
    De dónde viene: se usa desde `setup_logging()` al inicializar el formatter.
    A dónde va: alimenta a `logging.Formatter`.
    Librerías externas: no usa una librería externa directamente; solo define el formato para `logging`.
    """
    return (
        "%(asctime)s level=%(levelname)s "
        "traceId=%(traceId)s spanId=%(spanId)s correlationId=%(correlationId)s "
        "user=%(user)s endpoint=%(endpoint)s "
        "logger=%(name)s message=%(message)s"
    )


def setup_logging() -> None:
    """
    Qué hace: configura el logging global de la aplicación.
    Por qué lo hace: para que todos los logs usen el mismo formato y nivel.
    Cómo lo hace: ajusta el logger raíz, aplica el formatter contextual e instrumenta logging si OTEL está activo.
    De dónde viene: se llama durante la inicialización de telemetría.
    A dónde va: deja el sistema de logs listo para consola y trazas correlacionadas.
    Librerías externas: sí, usa `logging` y opcionalmente `LoggingInstrumentor` de OpenTelemetry.
    """
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
        """
        Qué hace: prepara contexto por request antes de ejecutar la vista.
        Por qué lo hace: para tener correlationId, endpoint y usuario disponibles en logs y trazas.
        Cómo lo hace: lee headers, sesión y span activo, y guarda datos en `g`.
        De dónde viene: se ejecuta automáticamente antes de cada request de Flask.
        A dónde va: el contexto queda en `g` y se reutiliza en logging y respuesta.
        Librerías externas: sí, depende de `Flask`, `request`, `session` y OpenTelemetry.
        """
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
        """
        Qué hace: cierra la request añadiendo contexto y registrando el resultado.
        Por qué lo hace: para devolver el correlation ID al cliente y dejar trazabilidad del cierre.
        Cómo lo hace: escribe el header de respuesta y emite un log con método, ruta y estado.
        De dónde viene: se ejecuta automáticamente después de cada request de Flask.
        A dónde va: el encabezado vuelve al cliente y el log va al sistema de observabilidad.
        Librerías externas: sí, usa `Flask` y su ciclo de request/response.
        """
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
    """
    Qué hace: inicializa logging, hooks y OpenTelemetry para la aplicación.
    Por qué lo hace: para habilitar observabilidad consistente en requests, logs y base de datos.
    Cómo lo hace: configura logging, registra hooks, crea el provider OTEL y instrumenta Flask y SQLAlchemy si está habilitado.
    De dónde viene: se llama desde el arranque principal de la aplicación.
    A dónde va: deja la app preparada para exportar trazas y logs a un backend OTEL.
    Librerías externas: sí, usa OpenTelemetry, Flask y SQLAlchemy.
    """
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
    """
    Qué hace: registra métricas Prometheus y expone `/metrics`.
    Por qué lo hace: para que un colector externo pueda leer métricas HTTP y de base de datos.
    Cómo lo hace: crea contadores y gauges, engancha hooks de request y define la ruta `/metrics`.
    De dónde viene: se activa durante la inicialización de telemetría cuando OTEL está habilitado.
    A dónde va: las métricas quedan disponibles para Prometheus o un scraper similar.
    Librerías externas: sí, usa `prometheus_client` y Flask.
    """
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
        """
        Qué hace: toma el tiempo de inicio de la request para medir latencia.
        Por qué lo hace: para calcular duración de cada petición HTTP.
        Cómo lo hace: guarda un timestamp de alta resolución en `g`.
        De dónde viene: se ejecuta automáticamente antes de cada request.
        A dónde va: el valor lo consume `_metrics_record()` al terminar la respuesta.
        Librerías externas: sí, usa Flask y `time.perf_counter`.
        """
        g._request_start_time = __import__("time").perf_counter()

    @app.after_request
    def _metrics_record(response):
        """
        Qué hace: registra latencia y conteo de requests HTTP.
        Por qué lo hace: para medir uso y rendimiento de la API o UI.
        Cómo lo hace: calcula el tiempo transcurrido y actualiza histogramas y contadores Prometheus.
        De dónde viene: se ejecuta automáticamente después de cada respuesta de Flask.
        A dónde va: los datos quedan expuestos en las métricas de Prometheus.
        Librerías externas: sí, usa `prometheus_client` y Flask.
        """
        start = getattr(g, "_request_start_time", None)
        if start is not None:
            elapsed = __import__("time").perf_counter() - start
            endpoint = request.endpoint or "unknown"
            request_latency.labels(request.method, endpoint).observe(elapsed)
            request_count.labels(request.method, endpoint, str(response.status_code)).inc()
        return response

    @app.route("/metrics")
    def metrics():
        """
        Qué hace: expone las métricas en formato Prometheus.
        Por qué lo hace: para que un scraper externo pueda recolectarlas.
        Cómo lo hace: serializa el registro actual con `generate_latest()` y devuelve el content type correcto.
        De dónde viene: la llamada llega desde el colector o navegador que consulte `/metrics`.
        A dónde va: responde directamente al cliente que recolecta métricas.
        Librerías externas: sí, usa `prometheus_client` y Flask.
        """
        return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
