"""
Ejecutar:
    pytest test_contract.py -v

Requiere:
    pip install schemathesis flask
"""

import pytest
import os
import sys
from pathlib import Path

# ── Sobreescribir DATABASE_URL ANTES de cualquier import de la app ────────────
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import schemathesis
from schemathesis.checks import not_a_server_error

sys.path.insert(0, str(Path(__file__).parent.parent))

BASE_DIR = Path(__file__).parent.parent

# ── Importar la app DESPUÉS de setear el env ──────────────────────────────────
from app.main import app as flask_app
from app.database import db as _db

flask_app.config['TESTING'] = True
flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ── Schema filtrado ───────────────────────────────────────────────────────────
schema = schemathesis.openapi.from_path(
    str(BASE_DIR / "openapi_spec.json"),
    encoding="utf-8-sig"
)
schema.app = flask_app

filtered_schema = schema.include(method=["GET", "POST", "PUT", "DELETE", "PATCH"]).exclude(path_regex="^/auth/")


# ── Crear tablas una sola vez para toda la sesión ─────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def setup_database():
    with flask_app.app_context():
        _db.create_all()
    yield
    with flask_app.app_context():
        _db.drop_all()


# ── Cliente con TESTING=True (bypasea require_jwt y login_required) ───────────
@pytest.fixture()
def client():
    with flask_app.test_client() as c:
        yield c


# ── Schemathesis: solo verifica que no haya errores 5xx ───────────────────────
@filtered_schema.parametrize()
def test_api_contract(case):
    response = case.call()
    case.validate_response(response, checks=[not_a_server_error])


# ── PRODUCTS ──────────────────────────────────────────────────────────────────
def test_get_products_returns_list(client):
    res = client.get("/api/products")
    assert res.status_code == 200
    data = res.get_json()
    assert "products" in data
    assert isinstance(data["products"], list)

def test_create_product_missing_required_fields_returns_422(client):
    res = client.post("/api/products", json={"description": "sin campos requeridos"})
    assert res.status_code == 422

def test_get_nonexistent_product_returns_404(client):
    res = client.get("/api/products/99999")
    assert res.status_code == 404

def test_create_and_retrieve_product(client):
    created = client.post("/api/products", json={
        "name": "Producto Test",
        "sku":  "TEST-001",
        "price": 9.99
    })
    assert created.status_code == 201
    product = created.get_json()
    assert "id" in product

    fetched = client.get(f"/api/products/{product['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["name"] == "Producto Test"


# ── STOCK ─────────────────────────────────────────────────────────────────────
def test_get_stock_history_returns_200(client):
    res = client.get("/api/stock/history")
    assert res.status_code == 200

def test_get_stock_alerts_returns_200(client):
    res = client.get("/api/stock/alerts")
    assert res.status_code == 200

def test_create_stock_movement_missing_fields_returns_422(client):
    res = client.post("/api/stock/movement", json={"notes": "sin product_id ni qty"})
    assert res.status_code == 422


# ── REPORTS ───────────────────────────────────────────────────────────────────
def test_get_critical_stock_returns_200(client):
    res = client.get("/api/reports/critical-stock")
    assert res.status_code == 200

def test_get_top_products_returns_200(client):
    res = client.get("/api/reports/top-products")
    assert res.status_code == 200

def test_get_recent_movements_returns_200(client):
    res = client.get("/api/reports/recent-movements")
    assert res.status_code == 200


# ── AUDIT ─────────────────────────────────────────────────────────────────────
def test_get_audit_logs_returns_200(client):
    res = client.get("/api/audit")
    assert res.status_code == 200

def test_get_audit_nonexistent_product_returns_404(client):
    res = client.get("/api/audit/product/99999")
    assert res.status_code == 404

def test_get_audit_nonexistent_movement_returns_404(client):
    res = client.get("/api/audit/movement/99999")
    assert res.status_code == 404


# ── HEALTH ────────────────────────────────────────────────────────────────────
def test_health_check_returns_200(client):
    res = client.get("/health")
    assert res.status_code == 200