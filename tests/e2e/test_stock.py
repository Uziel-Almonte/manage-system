"""
E2E: Stock entry and exit flow through the UI.
 
QUÉ: Prueba E2E que valida el flujo completo de entradas y salidas de stock de un producto, simulando de la
     formas mas realista posiblem de como lo haria un usuario real.
CÓMO: Esto lo hace por medio de playwright, que abre un navegador real y simula la interacción de un usuario con la UI.
      Aqui se crea un producto, se registra un movimiento de entrada, se verifica el resultado en la tabla de movimientos, 
      se registra una salida y se vuelve a verificar. La funcion principal es test_stock_entry_and_exit_flow que es la que llama las demas funciones
      de este archivo. No se llama nada externo.
POR QUÉ: Para detectar regresiones en el flujo crítico de negocio
     (control de inventario) que pruebas unitarias no pueden cubrir,
     porque involucra la interacción real de la UI, el backend y la BD.
DE DÓNDE VIENE: Depende de fixtures externas (logged_in_manager, base_url)
     definidas en conftest.py, que ya dejan una sesión autenticada lista.
A DÓNDE VA: No retorna nada; su "salida" son las aserciones (expect) que
     hacen pasar o fallar el test, reportado por pytest.
"""

import uuid
import pytest
from playwright.sync_api import expect

"""
    Qué hace:
        Crea un producto mediante la interfaz de la aplicación.

    Cómo lo hace:
        Navega al formulario de creación de productos, completa los campos
        necesarios con los valores recibidos como parámetros, pulsa el botón
        "Crear Producto" y espera a que la aplicación redirija al listado
        de productos.

    Por qué lo hace:
        El flujo de movimientos de stock necesita un producto existente.
        Esta función permite crear uno específicamente para la prueba sin
        depender de datos previamente almacenados en la base de datos.

    De dónde viene:
        page es el objeto Page proporcionado por Playwright.
        base_url proviene del fixture de pytest.
        name, sku y qty son datos generados y proporcionados por el test
        principal.

    A dónde va:
        Los datos son enviados a la aplicación mediante el formulario de
        creación. Después de guardar el producto, el navegador termina en
        la página /products.
"""
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

"""
    Qué hace:
        Registra un movimiento de inventario para un producto existente.

    Cómo lo hace:
        Navega al formulario de actualización de stock, selecciona el producto,
        selecciona el tipo de movimiento, introduce la cantidad y, si se
        proporcionaron notas, las agrega. Finalmente envía el formulario y
        espera la redirección al listado de movimientos.

    Por qué lo hace:
        Encapsula los pasos comunes necesarios para registrar una entrada o
        salida de stock y permite que el test principal reutilice el mismo
        flujo para ambos tipos de movimiento.

    De dónde viene:
        page y base_url provienen del entorno de ejecución del test.
        product_name y product_sku identifican el producto creado previamente.
        movement_type y qty determinan el tipo y cantidad del movimiento.
        notes contiene información adicional opcional para el movimiento.

    A dónde va:
        El movimiento se envía a la aplicación mediante el formulario de
        actualización de stock. Al finalizar, el navegador queda en la
        página /stock, donde el test principal puede verificar el movimiento
        registrado.
"""
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

"""
    Qué hace:
        Verifica el flujo completo de inventario de un producto, comprobando
        que una entrada aumente correctamente el stock y que una salida lo
        reduzca correctamente.

    Cómo lo hace:
        Utiliza una sesión autenticada como manager, genera un producto único,
        lo crea mediante la interfaz, registra una entrada de 5 unidades y
        verifica que el stock pase de 10 a 15. Después registra una salida de
        3 unidades y verifica que el stock pase de 15 a 12.

    Por qué lo hace:
        El control de inventario es un flujo crítico del sistema. Este test
        permite verificar que las operaciones de entrada y salida funcionen
        correctamente cuando se ejecutan desde la interfaz y que el resultado
        almacenado y mostrado por la aplicación sea el esperado.

    De dónde viene:
        logged_in_manager y base_url son fixtures proporcionados por conftest.py.
        uuid se utiliza para generar identificadores únicos. Las funciones
        _create_product() y _register_movement() proporcionan las operaciones
        necesarias para crear el producto y registrar los movimientos.

    A dónde va:
        El navegador termina en la página de movimientos de stock con las dos
        operaciones registradas. El test confirma que la entrada de +5 dejó
        el stock en 15 y que la salida de -3 lo dejó en 12.
"""
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
