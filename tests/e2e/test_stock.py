"""
E2E: Stock entry and exit flow through the UI.
"""
import uuid

import pytest
from playwright.sync_api import expect


def _create_product(page, base_url, name, sku, qty=10):
    """Helper: create a product via the UI and return (name, sku)."""
    page.goto(f"{base_url}/products/new")
    page.fill("#sku", sku)
    page.fill("#name", name)
    page.fill("#price", "25.00")
    page.fill("#qty", str(qty))
    page.fill("#min_stock", "2")
    page.get_by_role("button", name="Crear Producto").click()
    page.wait_for_url(f"{base_url}/products")


def _register_movement(page, base_url, product_name, product_sku, movement_type, qty, notes=""):
    """Helper: submit a stock movement for the given product."""
    page.goto(f"{base_url}/stock/update")
    page.select_option("#product_id", label=f"{product_name} ({product_sku})")
    page.locator(f'input[name="type"][value="{movement_type}"]').check()
    page.fill("#qty_change", str(qty))
    if notes:
        page.fill("#notes", notes)
    page.get_by_role("button", name="Registrar Movimiento").click()
    page.wait_for_url(f"{base_url}/stock")


@pytest.mark.e2e
def test_stock_entry_and_exit_flow(logged_in_manager, base_url):
    page = logged_in_manager

    suffix = uuid.uuid4().hex[:8]
    product_name = f"E2E Stock {suffix}"
    product_sku = f"STK-{suffix}"

    _create_product(page, base_url, product_name, product_sku, qty=10)

    # Entry: 10 -> 15
    _register_movement(
        page, base_url, product_name, product_sku,
        movement_type="entry", qty=5, notes="E2E entry test",
    )

    entry_row = page.locator("tr", has_text=product_name).filter(has_text="Entrada").first
    expect(entry_row.get_by_text("Entrada")).to_be_visible()
    expect(entry_row.locator("span.text-green-600")).to_have_text("+5")
    expect(entry_row.get_by_role("cell", name="15", exact=True)).to_be_visible()

    # Exit: 15 -> 12
    _register_movement(
        page, base_url, product_name, product_sku,
        movement_type="exit", qty=3, notes="E2E exit test",
    )

    exit_row = page.locator("tr", has_text=product_name).filter(has_text="Salida").first
    expect(exit_row.get_by_text("Salida")).to_be_visible()
    expect(exit_row.locator("span.text-red-600")).to_have_text("-3")
    expect(exit_row.get_by_role("cell", name="12", exact=True)).to_be_visible()
