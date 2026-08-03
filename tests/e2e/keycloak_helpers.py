"""Keycloak login helpers for E2E tests."""
import os

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:5000")
ALICE_USER = os.getenv("E2E_ALICE_USER", "alice_worker")
ALICE_PASSWORD = os.getenv("E2E_ALICE_PASSWORD", "password123")
MANAGER_USER = os.getenv("E2E_MANAGER_USER", "kratos_boss")
MANAGER_PASSWORD = os.getenv("E2E_MANAGER_PASSWORD", "password123")

"""
    Qué hace:
        Realiza el proceso completo de autenticación de un usuario mediante
        Keycloak y deja la página de Playwright autenticada en la aplicación.

    Cómo lo hace:
        Primero navega a la página de login de la aplicación. Después pulsa
        el enlace que inicia el login con Keycloak, espera a que aparezca el
        formulario de autenticación, introduce el usuario y la contraseña y
        finalmente pulsa el botón de login.

        Después del login espera a que Keycloak redirija nuevamente hacia la
        aplicación. Si la redirección falla, intenta obtener el mensaje de
        error mostrado por Keycloak para generar un error más descriptivo.

    Por qué lo hace:
        Los tests E2E necesitan simular el comportamiento real de un usuario
        que inicia sesión mediante OAuth2/Keycloak. Centralizar este proceso
        evita repetir los mismos pasos de autenticación en cada test.

    De dónde viene:
        page es el objeto Page proporcionado por Playwright.
        base_url corresponde a la URL de la aplicación.
        username y password son las credenciales del usuario que realizará
        la autenticación y provienen de los fixtures o configuraciones E2E.

    A dónde va:
        Después de autenticarse, Keycloak redirige el navegador nuevamente
        hacia la aplicación. La función deja el objeto page en ese estado
        autenticado para que el test pueda continuar interactuando con la
        aplicación.
"""
def login_via_keycloak(page, base_url, username, password):
    """Complete OAuth2 login: app login page -> Keycloak -> dashboard."""
    page.goto(f"{base_url}/auth/login-page")
    page.get_by_role("link", name="Continuar con Keycloak").click()

    page.wait_for_selector("#username", timeout=30000)
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#kc-login")

    # Keycloak may briefly stay on login-actions; wait for redirect back to the app.
    try:
        page.wait_for_url(
            lambda url: url.startswith(base_url) and "/realms/" not in url,
            timeout=60000,
        )
    except Exception as exc:
        error = page.locator("#input-error, .kc-feedback-text, .alert-error").first
        if error.count() > 0:
            raise AssertionError(
                f"Keycloak login failed for {username}: {error.inner_text().strip()}"
            ) from exc
        raise AssertionError(
            f"Keycloak login timed out for {username}; current URL: {page.url}"
        ) from exc
    page.wait_for_load_state("domcontentloaded")
