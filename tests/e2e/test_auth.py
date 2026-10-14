"""
E2E: Login via Keycloak and land on the dashboard.
"""
import pytest
from playwright.sync_api import expect

from tests.e2e.keycloak_helpers import ALICE_PASSWORD, ALICE_USER, login_via_keycloak

"""
    Qué hace:
        Verifica que Alice pueda autenticarse correctamente mediante Keycloak
        y que, después del login, sea redirigida al dashboard de la aplicación.
        También comprueba que la interfaz muestre únicamente las opciones de
        navegación correspondientes a sus permisos.

    Cómo lo hace:
        Utiliza login_via_keycloak() de keycloak_helpers.py para realizar el flujo completo de
        autenticación. Después utiliza las aserciones de Playwright para
        comprobar la URL final, elementos visibles del dashboard y enlaces
        de navegación que Alice puede o no puede utilizar.

    Por qué lo hace:
        Comprueba de extremo a extremo que la integración entre la aplicación,
        Keycloak y la interfaz principal funcione correctamente. También
        verifica que los permisos del usuario se reflejen correctamente en
        la navegación.

    De dónde viene:
        page es proporcionado por el fixture de Playwright.
        base_url proviene del fixture base_url definido en conftest.py.
        ALICE_USER y ALICE_PASSWORD contienen las credenciales de Alice y
        login_via_keycloak() implementa el proceso de autenticación contra
        Keycloak.

    A dónde va:
        El navegador termina en el dashboard de la aplicación con Alice
        autenticada. El test confirma que pueda ver los productos y movimientos
        recientes, pero que no tenga disponibles los enlaces de auditoría
        y reportes.
"""
@pytest.mark.e2e
def test_login_via_keycloak_lands_on_dashboard(page, base_url):
    login_via_keycloak(page, base_url, ALICE_USER, ALICE_PASSWORD)

    expect(page).to_have_url(f"{base_url}/")
    expect(page.get_by_text("Bienvenido", exact=False)).to_be_visible()
    expect(page.get_by_text("Productos Activos")).to_be_visible()
    expect(page.get_by_role("heading", name="Movimientos Recientes")).to_be_visible()

    # alice_worker should see stock but not audit/report nav links
    expect(page.locator('nav a[href="/products"]').first).to_be_visible()
    expect(page.locator('a[href="/audit"]')).to_have_count(0)
    expect(page.locator('a[href="/reports"]')).to_have_count(0)
