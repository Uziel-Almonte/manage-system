"""
E2E: Add a product through the UI and verify it appears in the list.
"""
import uuid

import pytest
from playwright.sync_api import expect


"""
    Qué hace:
        Verifica que un usuario con permisos de manager pueda crear un producto
        mediante la interfaz web y que el producto creado aparezca posteriormente
        en el listado de productos.
    Cómo lo hace:
        Utiliza una sesión autenticada como manager, genera un nombre y SKU únicos
        para el producto, navega al formulario de creación, completa todos sus
        campos y envía el formulario. Después espera la redirección al listado
        de productos y comprueba que el nombre y SKU del producto creado sean
        visibles.
    Por qué lo hace:
        Comprueba de extremo a extremo que el flujo de creación de productos
        funcione correctamente desde la interfaz hasta la visualización del
        resultado. También evita depender de un producto previamente existente
        en la base de datos.
    De dónde viene:
        logged_in_manager es proporcionado por el fixture de autenticación y
        contiene una página de Playwright autenticada como manager.
        base_url proporciona la dirección base de la aplicación.
        uuid se utiliza para generar identificadores únicos para los datos
        creados durante la prueba.
    A dónde va:
        El producto es enviado a la aplicación mediante el formulario de creación
        y, después de guardarse, el navegador es redirigido al listado de productos.
        El test termina verificando que el producto recién creado esté presente
        en ese listado.
"""
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
