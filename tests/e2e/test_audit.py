"""
E2E: Audit page access is blocked for users without audit:view scope.
"""
import pytest
from playwright.sync_api import expect

"""
    Qué hace:
        Verifica que un usuario autenticado que no posee el scope audit:view
        no pueda acceder a la página de auditoría.
    Cómo lo hace:
        Utiliza el fixture logged_in_alice para iniciar sesión como Alice.
        Primero comprueba que el enlace hacia /audit no aparezca en la navegación.
        Después intenta acceder directamente a /audit y verifica que la aplicación
        redirija al usuario al dashboard mostrando un mensaje de acceso denegado
        y especificando el scope que falta.
    Por qué lo hace:
        Comprueba que el control de autorización funcione correctamente.
        No basta con ocultar el enlace de auditoría de la interfaz, porque un
        usuario podría intentar acceder directamente escribiendo la URL.
        El test verifica ambas capas de protección.
    De dónde viene:
        logged_in_alice es proporcionado por el fixture de autenticación definido
        en conftest.py y deja al navegador con una sesión autenticada como Alice.
        base_url proporciona la URL base de la aplicación.
    A dónde va:
        El test termina verificando que Alice permanezca fuera de la página de
        auditoría y sea redirigida al dashboard con un mensaje indicando que
        necesita el permiso audit:view.
"""
@pytest.mark.e2e
def test_user_without_audit_scope_cannot_access_audit_page(logged_in_alice, base_url):
    page = logged_in_alice

    # Nav should not expose the audit link
    expect(page.locator('a[href="/audit"]')).to_have_count(0)

    # Direct URL access is blocked and redirects to dashboard
    page.goto(f"{base_url}/audit")
    expect(page).to_have_url(f"{base_url}/")
    expect(page.get_by_text("Acceso denegado", exact=False)).to_be_visible()
    expect(page.get_by_text("audit:view", exact=False)).to_be_visible()
