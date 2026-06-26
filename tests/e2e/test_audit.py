"""
E2E: Audit page access is blocked for users without audit:view scope.
"""
import pytest
from playwright.sync_api import expect


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
