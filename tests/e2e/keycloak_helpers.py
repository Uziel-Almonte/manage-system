"""Keycloak login helpers for E2E tests."""
import os

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:5000")
ALICE_USER = os.getenv("E2E_ALICE_USER", "alice_worker")
ALICE_PASSWORD = os.getenv("E2E_ALICE_PASSWORD", "password123")
MANAGER_USER = os.getenv("E2E_MANAGER_USER", "kratos_boss")
MANAGER_PASSWORD = os.getenv("E2E_MANAGER_PASSWORD", "password123")


def login_via_keycloak(page, base_url, username, password):
    """Complete OAuth2 login: app login page -> Keycloak -> dashboard."""
    page.goto(f"{base_url}/auth/login-page")
    page.get_by_role("link", name="Continuar con Keycloak").click()

    page.wait_for_selector("#username", timeout=15000)
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#kc-login")

    page.wait_for_url(
        lambda url: url.startswith(base_url) and "/realms/" not in url,
        timeout=30000,
    )
