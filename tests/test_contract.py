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
    """
    Qué hace: crea y destruye las tablas de prueba una sola vez por sesión.
    Por qué lo hace: para que la suite de contrato tenga una base temporal limpia y estable.
    Cómo lo hace: ejecuta `create_all()` antes de la sesión y `drop_all()` al final.
    De dónde viene: lo invoca Pytest automáticamente por ser `autouse=True`.
    A dónde va: prepara el estado de la base para todos los casos de esta sesión de tests.
    Librerías externas: usa Pytest y SQLAlchemy a través de la app Flask.
    """
    with flask_app.app_context():
        _db.create_all()
    yield
    with flask_app.app_context():
        _db.drop_all()


# ── Limpiar datos entre cada test para no contaminar otros módulos ─────────────
@pytest.fixture(autouse=True)
def clean_tables():
    """
    Qué hace: limpia las tablas entre tests para evitar contaminación de datos.
    Por qué lo hace: para que cada caso de prueba parta de un estado aislado.
    Cómo lo hace: recorre las tablas en orden inverso, elimina los registros y confirma la transacción.
    De dónde viene: Pytest lo ejecuta automáticamente antes y después de cada test.
    A dónde va: deja la base lista para el siguiente caso.
    Librerías externas: usa SQLAlchemy y Pytest.
    """
    yield
    with flask_app.app_context():
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


# ── Cliente con TESTING=True (bypasea require_jwt y login_required) ───────────
@pytest.fixture()
def client():
    """
    Qué hace: crea un cliente de prueba de Flask.
    Por qué lo hace: para poder llamar a la API sin levantar un servidor real.
    Cómo lo hace: usa el `test_client()` de Flask y lo entrega como fixture.
    De dónde viene: cualquier test que reciba `client` lo obtiene de Pytest.
    A dónde va: se usa para hacer requests HTTP simuladas en los tests.
    Librerías externas: sí, usa Flask.
    """
    with flask_app.test_client() as c:
        yield c


# ── Schemathesis: solo verifica que no haya errores 5xx ───────────────────────
@filtered_schema.parametrize()
def test_api_contract(case):
    """
    Qué hace: valida que los endpoints del contrato OpenAPI no devuelvan errores 5xx.
    Por qué lo hace: para detectar regresiones de estabilidad en la API expuesta.
    Cómo lo hace: Schemathesis genera casos desde el schema, ejecuta la llamada y verifica la respuesta.
    De dónde viene: el caso viene del esquema cargado desde `openapi_spec.json`.
    A dónde va: la respuesta se valida contra las comprobaciones de Schemathesis.
    Librerías externas: sí, usa Schemathesis y su check `not_a_server_error`.
    """
    response = case.call()
    case.validate_response(response, checks=[not_a_server_error])


# ── PRODUCTS ──────────────────────────────────────────────────────────────────
def test_get_products_returns_list(client):
    """
    Qué hace: verifica que el listado de productos responda correctamente.
    Por qué lo hace: para asegurar que la API principal expone un payload consumible.
    Cómo lo hace: realiza un GET y comprueba el código y la forma del JSON.
    De dónde viene: la petición se origina en `GET /api/products`.
    A dónde va: espera un JSON con la clave `products`.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/products")
    assert res.status_code == 200
    data = res.get_json()
    assert "products" in data
    assert isinstance(data["products"], list)

def test_create_product_missing_required_fields_returns_422(client):
    """
    Qué hace: valida que crear un producto sin campos mínimos falle con 422.
    Por qué lo hace: para confirmar que el esquema de entrada protege la API.
    Cómo lo hace: envía un JSON incompleto y verifica la respuesta.
    De dónde viene: la petición sale de `POST /api/products`.
    A dónde va: espera un error de validación antes de tocar la base.
    Librerías externas: usa Flask y el validador del endpoint.
    """
    res = client.post("/api/products", json={"description": "sin campos requeridos"})
    assert res.status_code == 422

def test_get_nonexistent_product_returns_404(client):
    """
    Qué hace: verifica que pedir un producto inexistente devuelva 404.
    Por qué lo hace: para asegurar que la API maneja IDs inválidos de forma explícita.
    Cómo lo hace: consulta un ID que no existe y comprueba el código HTTP.
    De dónde viene: la petición sale de `GET /api/products/99999`.
    A dónde va: espera una respuesta de no encontrado.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/products/99999")
    assert res.status_code == 404

def test_create_and_retrieve_product(client):
    """
    Qué hace: crea un producto y luego lo recupera por ID.
    Por qué lo hace: para validar el ciclo básico de persistencia y lectura.
    Cómo lo hace: publica un producto, extrae el ID y luego hace una consulta GET.
    De dónde viene: ambas peticiones vienen de la API `/api/products`.
    A dónde va: espera que el registro guardado se pueda leer con los mismos datos.
    Librerías externas: usa Flask para las requests.
    """
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
    """
    Qué hace: verifica que el historial de stock responda correctamente.
    Por qué lo hace: para confirmar que el endpoint de trazabilidad está operativo.
    Cómo lo hace: consulta la ruta de historial y valida el código HTTP.
    De dónde viene: la petición sale de `GET /api/stock/history`.
    A dónde va: espera una respuesta satisfactoria con datos de movimientos.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/stock/history")
    assert res.status_code == 200

def test_get_stock_alerts_returns_200(client):
    """
    Qué hace: comprueba que la ruta de alertas de stock responda.
    Por qué lo hace: para validar que el sistema puede exponer alertas sin error.
    Cómo lo hace: hace una consulta GET al endpoint de alertas.
    De dónde viene: la petición sale de `GET /api/stock/alerts`.
    A dónde va: espera un 200 como respuesta.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/stock/alerts")
    assert res.status_code == 200

def test_create_stock_movement_missing_fields_returns_422(client):
    """
    Qué hace: valida que un movimiento de stock incompleto falle.
    Por qué lo hace: para proteger la integridad del inventario.
    Cómo lo hace: envía un JSON incompleto y espera un error de validación.
    De dónde viene: la petición sale de `POST /api/stock/movement`.
    A dónde va: espera un 422 por campos faltantes.
    Librerías externas: usa Flask y la validación del endpoint.
    """
    res = client.post("/api/stock/movement", json={"notes": "sin product_id ni qty"})
    assert res.status_code == 422


# ── REPORTS ───────────────────────────────────────────────────────────────────
def test_get_critical_stock_returns_200(client):
    """
    Qué hace: verifica la ruta de stock crítico.
    Por qué lo hace: para asegurar que el dashboard de reportes puede consultar alertas críticas.
    Cómo lo hace: hace una petición GET al endpoint de reportes.
    De dónde viene: la petición sale de `GET /api/reports/critical-stock`.
    A dónde va: espera un 200 con la lista correspondiente.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/reports/critical-stock")
    assert res.status_code == 200

def test_get_top_products_returns_200(client):
    """
    Qué hace: verifica la ruta de productos más vendidos o más relevantes.
    Por qué lo hace: para confirmar que el reporte principal puede obtener el ranking.
    Cómo lo hace: consulta el endpoint de top products.
    De dónde viene: la petición sale de `GET /api/reports/top-products`.
    A dónde va: espera un 200.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/reports/top-products")
    assert res.status_code == 200

def test_get_recent_movements_returns_200(client):
    """
    Qué hace: valida el endpoint de movimientos recientes.
    Por qué lo hace: para asegurar que el reporte de actividad esté disponible.
    Cómo lo hace: consulta la ruta de recientes y comprueba el código HTTP.
    De dónde viene: la petición sale de `GET /api/reports/recent-movements`.
    A dónde va: espera un 200.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/reports/recent-movements")
    assert res.status_code == 200


# ── AUDIT ─────────────────────────────────────────────────────────────────────
def test_get_audit_logs_returns_200(client):
    """
    Qué hace: comprueba que la ruta principal de auditoría responda.
    Por qué lo hace: para validar el acceso al historial de cambios.
    Cómo lo hace: llama al endpoint de auditoría y verifica el estado HTTP.
    De dónde viene: la petición sale de `GET /api/audit`.
    A dónde va: espera un 200.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/audit")
    assert res.status_code == 200

def test_get_audit_nonexistent_product_returns_404(client):
    """
    Qué hace: valida que consultar auditoría de un producto inexistente devuelva 404.
    Por qué lo hace: para asegurar que la API maneja referencias inválidas.
    Cómo lo hace: consulta un ID ficticio y revisa el código.
    De dónde viene: la petición sale de `GET /api/audit/product/99999`.
    A dónde va: espera una respuesta de no encontrado.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/audit/product/99999")
    assert res.status_code == 404

def test_get_audit_nonexistent_movement_returns_404(client):
    """
    Qué hace: valida que consultar auditoría de un movimiento inexistente devuelva 404.
    Por qué lo hace: para mantener consistencia en el manejo de IDs inválidos.
    Cómo lo hace: hace la consulta con un ID que no existe y verifica el estado.
    De dónde viene: la petición sale de `GET /api/audit/movement/99999`.
    A dónde va: espera un 404.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/api/audit/movement/99999")
    assert res.status_code == 404


# ── HEALTH ────────────────────────────────────────────────────────────────────
def test_health_check_returns_200(client):
    """
    Qué hace: valida que el endpoint de salud responda correctamente.
    Por qué lo hace: para confirmar que el servicio está vivo y operando.
    Cómo lo hace: ejecuta una petición GET al health check.
    De dónde viene: la petición sale de `GET /health`.
    A dónde va: espera un 200 con el estado del servicio.
    Librerías externas: usa Flask a través del cliente de prueba.
    """
    res = client.get("/health")
    assert res.status_code == 200