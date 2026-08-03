"""
Shared fixtures for Playwright end-to-end tests.

Requires the full stack running:
    docker compose up -d

Run E2E tests (Playwright + host network for OAuth):
    docker compose --profile e2e run --rm e2e

Unit/contract tests (inside flask container, E2E excluded):
    docker exec flask_app pytest tests/ -m "not e2e" -v
"""
import os
from pathlib import Path

import pytest
import requests

from tests.e2e.keycloak_helpers import (
    ALICE_PASSWORD,
    ALICE_USER,
    BASE_URL,
    MANAGER_PASSWORD,
    MANAGER_USER,
    login_via_keycloak,
)

SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"

"""
    Qué hace:
        Aqui se obtiene la URL que se utilizara en las pruebas E2E para pode acceder a la aplicacion.
    Cómo lo hace:
        Lo primero que hace es buscar la variable de entorno E2E_BASE_URL. Si no existe, utiliza BASE_URL como valor predeterminado.
        Ambar varibales se encuentran en keycloak_helpers.py.
    Por qué lo hace:
        Permite ejecutar el mismo entorno en diferentes pruebas sin tener que estar repitiendo codigo.
    De dónde viene:
        E2E_BASE_URL viene de las variables de entorno. 
        Y BASE_URL viene de keycloak_helpers.py.
    A dónde va:
        Retorna la URL base a los tests y fixtures que necesiten acceder a la aplicación.
"""
@pytest.fixture(scope="session")
def base_url():
    return os.getenv("E2E_BASE_URL", BASE_URL)


"""
    Qué hace:
        Aqui se valida si la apliacion Flask y Keycloak estan disponibles antes de ejecutar las pruebas E2E.
        Verifica que la aplicación Flask y Keycloak estén disponibles antes de ejecutar las pruebas E2E.
    Cómo lo hace:
        Comienza realizando una peticion HTTP a la página de login de Flask y otra al endpoint de configuración OpenID de Keycloak.
        En caso que algunas de las dos no responda correctamente, pytest omite las pruebas E2E mediante pytest.skip().
    Por qué lo hace:
        Se necesita comprobar que toda la infraestructura este arriba antes de poder ejecutar las pruebas E2E
        para poder evitar fallor a la hora de correr las pruebas.
    De dónde viene:
        base_url viene de keycloak_helpers.py y es la URL de la aplicación Flask.\
    A dónde va:
        Si ambos servicios están disponibles, la ejecución continúa hacia los tests E2E.
        Si alguno no está disponible, pytest marca las pruebas como omitidas.
"""
@pytest.fixture(scope="session", autouse=True)
def require_running_stack(base_url):
    """Skip E2E tests when the app or Keycloak is not reachable."""
    try:
        app_response = requests.get(f"{base_url}/auth/login-page", timeout=5)
        if app_response.status_code != 200:
            pytest.skip(f"Flask app not ready at {base_url} (status {app_response.status_code})")
    except requests.RequestException as exc:
        pytest.skip(f"E2E stack not available at {base_url}: {exc}")

    try:
        keycloak_response = requests.get(
            "http://localhost:8080/realms/inventory-realm/.well-known/openid-configuration",
            timeout=5,
        )
        if keycloak_response.status_code != 200:
            pytest.skip("Keycloak is not ready on http://localhost:8080")
    except requests.RequestException as exc:
        pytest.skip(f"Keycloak not available: {exc}")


"""
    Qué hace:
        Aqui se proporciona un inicio de seccion con una auteticacion valida de empleado normal (Alice) para los tests E2E.
    Cómo lo hace:
        Utiliza la función login_via_keycloak() de keycloak_helpers para realizar el proceso de autenticación
        contra Keycloak utilizando las credenciales de Alice que viene de la variables de entorno.
    Por qué lo hace:
        Permite que los tests que necesitan un usuario normal comiencen directamente
        con una sesión autenticada, evitando repetir el proceso de login en cada test.
    De dónde viene:
        page es proporcionado automáticamente por el fixture de Playwright.
        base_url proviene del fixture base_url.
        ALICE_USER y ALICE_PASSWORD provienen de keycloak_helpers.
    A dónde va:
        Retorna el objeto page ya autenticado para que los tests puedan interactuar
        con la aplicación como Alice.
"""
@pytest.fixture
def logged_in_alice(page, base_url):
    login_via_keycloak(page, base_url, ALICE_USER, ALICE_PASSWORD)
    return page

"""
    Qué hace:
        Aqui se proporciona un inicio de seccion con una auteticacion valida de manager para los tests E2E.
    Cómo lo hace:
        Utiliza login_via_keycloak() con las credenciales específicas del usuario
        manager.
    Por qué lo hace:
        Permite ejecutar pruebas sobre funcionalidades que requieren permisos o
        privilegios asociados al rol de manager sin repetir el proceso de autenticación.
    De dónde viene:
        page es proporcionado por Playwright.
        base_url proviene del fixture base_url.
        MANAGER_USER y MANAGER_PASSWORD provienen de keycloak_helpers.
    A dónde va:
        Retorna el objeto page autenticado para que los tests puedan interactuar
        con la aplicación utilizando los permisos del manager.
"""
@pytest.fixture
def logged_in_manager(page, base_url):
    login_via_keycloak(page, base_url, MANAGER_USER, MANAGER_PASSWORD)
    return page

"""
    Qué hace:
        Busca y obtiene el objeto Page de Playwright asociado al test que se está ejecutando.
    Cómo lo hace:
        Revisa los fixtures page, logged_in_alice y logged_in_manager dentro de
        item.funcargs este es un objeto proporcionado por pytest que contiene los argumentos de la función de test actual.
    Por qué lo hace:
        El hook de pytest necesita acceder a la página del navegador para poder
        tomar una captura de pantalla cuando un test E2E falla, independientemente
        del fixture de autenticación utilizado.
    De dónde viene:
        item es proporcionado por pytest y contiene información sobre el test actual
        y sus fixtures. Los objetos page, logged_in_alice y logged_in_manager son
        proporcionados por Playwright o por este archivo.
    A dónde va:
        Retorna el objeto Page encontrado al hook pytest_runtest_makereport().
        Si no encuentra ninguna página, retorna None.
"""
def _get_page_from_item(item):
    """Resolve the Playwright page from test fixtures."""
    for name in ("page", "logged_in_alice", "logged_in_manager"):
        page = item.funcargs.get(name)
        if page is not None:
            return page
    return None

"""
    Qué hace:
        Captura automáticamente una captura de pantalla cuando un test E2E falla.
    Cómo lo hace:
        Utiliza un hook de pytest para obtener el resultado del test. Si el test
        pertenece a la fase de ejecución (call), está marcado como fallido y es
        un test E2E, obtiene la página de Playwright y guarda una captura completa
        de la página.
    Por qué lo hace:
        Una captura del estado del navegador en el momento del fallo facilita
        diagnosticar problemas de interfaz, navegación, autenticación o datos
        mostrados por la aplicación.
    De dónde viene:
        item y call son proporcionados por pytest. La página de Playwright se obtiene
        mediante _get_page_from_item(). SCREENSHOTS_DIR define dónde se almacenarán
        las capturas.
    A dónde va:
        La captura se guarda como un archivo PNG dentro del directorio screenshots,
        utilizando como nombre el identificador del test que falló.
"""
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture a screenshot when an E2E test fails."""
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return

    if "e2e" not in item.keywords:
        return

    page = _get_page_from_item(item)
    if page is None:
        return

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = item.nodeid.replace("::", "_").replace("/", "_")
    screenshot_path = SCREENSHOTS_DIR / f"{safe_name}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)

