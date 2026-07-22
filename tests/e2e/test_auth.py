"""
E2E: Login via Keycloak and land on the dashboard.
"""
import pytest
from playwright.sync_api import expect

from tests.e2e.keycloak_helpers import ALICE_PASSWORD, ALICE_USER, login_via_keycloak


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
