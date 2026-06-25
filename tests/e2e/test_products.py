"""
E2E: Add a product through the UI and verify it appears in the list.
"""
import uuid

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
def test_add_product_appears_in_list(logged_in_manager, base_url):
    page = logged_in_manager

    unique_suffix = uuid.uuid4().hex[:8]
    product_name = f"E2E Product {unique_suffix}"
    product_sku = f"E2E-{unique_suffix}"

    page.goto(f"{base_url}/products/new")

    page.fill("#sku", product_sku)
    page.fill("#name", product_name)
    page.fill("#category", "E2E")
    page.fill("#description", "Created by Playwright E2E test")
    page.fill("#price", "49.99")
    page.fill("#qty", "10")
    page.fill("#min_stock", "2")

    page.get_by_role("button", name="Crear Producto").click()

    page.wait_for_url(f"{base_url}/products")
    expect(page.get_by_role("cell", name=product_name)).to_be_visible()
    expect(page.get_by_role("cell", name=product_sku)).to_be_visible()
