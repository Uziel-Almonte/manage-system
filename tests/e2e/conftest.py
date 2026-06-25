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


@pytest.fixture(scope="session")
def base_url():
    return os.getenv("E2E_BASE_URL", BASE_URL)


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


@pytest.fixture
def logged_in_alice(page, base_url):
    login_via_keycloak(page, base_url, ALICE_USER, ALICE_PASSWORD)
    return page


@pytest.fixture
def logged_in_manager(page, base_url):
    login_via_keycloak(page, base_url, MANAGER_USER, MANAGER_PASSWORD)
    return page
