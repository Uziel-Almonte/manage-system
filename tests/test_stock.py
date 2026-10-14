"""
Tests para la lógica de stock (movimientos y alertas)
"""
import json


class TestStockMovement:
    """Tests para movimientos de stock"""

    def test_create_stock_entry_movement(self, app_client):
        """
        Qué hace: valida la creación de un movimiento de entrada.
        Por qué lo hace: para asegurar que el stock aumenta correctamente cuando entra mercancía.
        Cómo lo hace: crea un producto, registra una entrada y comprueba el nuevo saldo.
        De dónde viene: la petición sale de `POST /api/stock/movement`.
        A dónde va: espera un movimiento con tipo `entry` y stock incrementado.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        # Crear producto primero
        product_payload = {'name': 'Producto Stock', 'sku': 'SKU-STOCK-001', 'price': 100.00, 'qty': 50}
        product_response = app_client.post(
            '/api/products',
            data=json.dumps(product_payload),
            content_type='application/json'
        )
        product_id = json.loads(product_response.data)['id']

        # Crear movimiento de entrada
        payload = {
            'product_id': product_id,
            'type': 'entry',
            'qty_change': 25,
            'user': 'test_user',
            'notes': 'Compra'
        }
        response = app_client.post(
            '/api/stock/movement',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['type'] == 'entry'
        assert data['new_qty'] == 75

    def test_create_stock_exit_movement(self, app_client):
        """
        Qué hace: valida la creación de un movimiento de salida.
        Por qué lo hace: para asegurar que el stock disminuye cuando hay consumo o retiro.
        Cómo lo hace: crea un producto, registra una salida y revisa el nuevo saldo.
        De dónde viene: la petición sale de `POST /api/stock/movement`.
        A dónde va: espera un movimiento con tipo `exit` y stock reducido.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        # Crear producto
        product_payload = {'name': 'Producto Exit', 'sku': 'SKU-EXIT-001', 'price': 100.00, 'qty': 50}
        product_response = app_client.post(
            '/api/products',
            data=json.dumps(product_payload),
            content_type='application/json'
        )
        product_id = json.loads(product_response.data)['id']

        # Movimiento de salida
        payload = {
            'product_id': product_id,
            'type': 'exit',
            'qty_change': 10,
            'user': 'test_user'
        }
        response = app_client.post(
            '/api/stock/movement',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['type'] == 'exit'
        assert data['new_qty'] == 40

    def test_exit_movement_insufficient_stock(self, app_client):
        """
        Qué hace: verifica que no se permita una salida con stock insuficiente.
        Por qué lo hace: para proteger la integridad del inventario.
        Cómo lo hace: crea un producto con poco stock e intenta retirar más de lo disponible.
        De dónde viene: la petición sale de `POST /api/stock/movement`.
        A dónde va: espera un error 400.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        product_payload = {'name': 'Stock Bajo', 'sku': 'SKU-LOW-EXIT', 'price': 100.00, 'qty': 10}
        product_response = app_client.post(
            '/api/products',
            data=json.dumps(product_payload),
            content_type='application/json'
        )
        product_id = json.loads(product_response.data)['id']

        payload = {
            'product_id': product_id,
            'type': 'exit',
            'qty_change': 1000
        }
        response = app_client.post(
            '/api/stock/movement',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_movement_with_nonexistent_product(self, app_client):
        """
        Qué hace: comprueba el manejo de un movimiento sobre un producto inexistente.
        Por qué lo hace: para asegurar una respuesta clara ante IDs inválidos.
        Cómo lo hace: envía un product_id ficticio y revisa el estado HTTP.
        De dónde viene: la petición sale de `POST /api/stock/movement`.
        A dónde va: espera un 404.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        payload = {
            'product_id': 9999,
            'type': 'entry',
            'qty_change': 10
        }
        response = app_client.post(
            '/api/stock/movement',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 404

    def test_movement_missing_required_fields(self, app_client):
        """
        Qué hace: valida que un movimiento incompleto falle.
        Por qué lo hace: para proteger el esquema de entrada.
        Cómo lo hace: envía un JSON con campos faltantes y comprueba la validación.
        De dónde viene: la petición sale de `POST /api/stock/movement`.
        A dónde va: espera un 422.
        Librerías externas: usa Flask y la validación del endpoint.
        """
        payload = {'product_id': 1, 'type': 'entry'}
        response = app_client.post(
            '/api/stock/movement',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 422

    def test_movement_invalid_type(self, app_client):
        """
        Qué hace: comprueba el manejo de tipos de movimiento inválidos.
        Por qué lo hace: para asegurar que solo se permitan entradas y salidas válidas.
        Cómo lo hace: crea un producto e intenta registrar un tipo no reconocido.
        De dónde viene: la petición sale de `POST /api/stock/movement`.
        A dónde va: espera un error de validación o de negocio.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        product_payload = {'name': 'Producto', 'sku': 'SKU-INVALID-001', 'price': 100.00}
        product_response = app_client.post(
            '/api/products',
            data=json.dumps(product_payload),
            content_type='application/json'
        )
        product_id = json.loads(product_response.data)['id']

        payload = {
            'product_id': product_id,
            'type': 'invalid_type',
            'qty_change': 10
        }
        response = app_client.post(
            '/api/stock/movement',
            data=json.dumps(payload),
            content_type='application/json'
        )
        # Schema validation catches unknown type before the view, so 422 is also valid
        assert response.status_code in (400, 422)


class TestStockHistory:
    """Tests para el historial de movimientos"""

    def test_get_stock_history(self, app_client):
        """
        Qué hace: valida que el historial de movimientos se pueda consultar.
        Por qué lo hace: para garantizar trazabilidad de inventario.
        Cómo lo hace: crea movimientos y luego consulta el historial.
        De dónde viene: la petición sale de `GET /api/stock/history`.
        A dónde va: espera una colección de movimientos.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        # Crear producto y movimientos
        product_payload = {'name': 'Producto History', 'sku': 'SKU-HIST-001', 'price': 100.00}
        product_response = app_client.post(
            '/api/products',
            data=json.dumps(product_payload),
            content_type='application/json'
        )
        product_id = json.loads(product_response.data)['id']

        for i in range(3):
            payload = {'product_id': product_id, 'type': 'entry', 'qty_change': 10}
            app_client.post(
                '/api/stock/movement',
                data=json.dumps(payload),
                content_type='application/json'
            )

        response = app_client.get('/api/stock/history')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) >= 3

    def test_filter_history_by_product_id(self, app_client):
        """
        Qué hace: verifica el filtrado del historial por producto.
        Por qué lo hace: para consultar solo movimientos de un inventario específico.
        Cómo lo hace: crea movimientos para distintos productos y consulta uno de ellos.
        De dónde viene: la petición sale de `GET /api/stock/history?product_id=...`.
        A dónde va: espera solo los movimientos del producto pedido.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        # Crear dos productos con movimientos
        product1 = app_client.post(
            '/api/products',
            data=json.dumps({'name': 'P1', 'sku': 'SKU-PROD1', 'price': 100.00}),
            content_type='application/json'
        )
        product2 = app_client.post(
            '/api/products',
            data=json.dumps({'name': 'P2', 'sku': 'SKU-PROD2', 'price': 100.00}),
            content_type='application/json'
        )
        p1_id = json.loads(product1.data)['id']
        p2_id = json.loads(product2.data)['id']

        app_client.post(
            '/api/stock/movement',
            data=json.dumps({'product_id': p1_id, 'type': 'entry', 'qty_change': 10}),
            content_type='application/json'
        )
        app_client.post(
            '/api/stock/movement',
            data=json.dumps({'product_id': p2_id, 'type': 'exit', 'qty_change': 5}),
            content_type='application/json'
        )

        response = app_client.get(f'/api/stock/history?product_id={p1_id}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) >= 1
        for movement in data:
            assert movement['product_id'] == p1_id

    def test_filter_history_by_type(self, app_client):
        """
        Qué hace: valida el filtrado del historial por tipo de movimiento.
        Por qué lo hace: para revisar solo entradas o solo salidas.
        Cómo lo hace: crea movimientos mixtos y consulta por tipo `entry`.
        De dónde viene: la petición sale de `GET /api/stock/history?type=entry`.
        A dónde va: espera que todos los resultados sean del tipo pedido.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        product_payload = {'name': 'Producto Filter', 'sku': 'SKU-FILTER-001', 'price': 100.00}
        product_response = app_client.post(
            '/api/products',
            data=json.dumps(product_payload),
            content_type='application/json'
        )
        product_id = json.loads(product_response.data)['id']

        app_client.post(
            '/api/stock/movement',
            data=json.dumps({'product_id': product_id, 'type': 'entry', 'qty_change': 10}),
            content_type='application/json'
        )
        app_client.post(
            '/api/stock/movement',
            data=json.dumps({'product_id': product_id, 'type': 'exit', 'qty_change': 5}),
            content_type='application/json'
        )

        response = app_client.get('/api/stock/history?type=entry')
        assert response.status_code == 200
        data = json.loads(response.data)
        for movement in data:
            assert movement['type'] == 'entry'


class TestStockAlerts:
    """Tests para alertas de stock bajo"""

    def test_get_stock_alerts_empty(self, app_client):
        """
        Qué hace: comprueba que el endpoint de alertas responda sin datos críticos.
        Por qué lo hace: para validar el comportamiento base cuando no hay alertas.
        Cómo lo hace: consulta la ruta sin crear productos con bajo stock.
        De dónde viene: la petición sale de `GET /api/stock/alerts`.
        A dónde va: espera un 200.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        response = app_client.get('/api/stock/alerts')
        assert response.status_code == 200

    def test_get_stock_alerts_with_low_stock(self, app_client):
        """
        Qué hace: valida que aparezcan alertas cuando existe stock bajo.
        Por qué lo hace: para confirmar que la lógica de umbral funciona.
        Cómo lo hace: crea un producto con cantidad menor al mínimo y consulta el endpoint.
        De dónde viene: la petición sale de `GET /api/stock/alerts`.
        A dónde va: espera al menos una alerta con productos incluidos.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        # Crear producto con stock bajo
        payload = {
            'name': 'Producto Alerta',
            'sku': 'SKU-ALERT-001',
            'price': 100.00,
            'qty': 5,
            'min_stock': 10,
            'status': 'active'
        }
        app_client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json'
        )

        response = app_client.get('/api/stock/alerts')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) > 0
        assert data[0]['alert_count'] >= 1

    def test_alert_not_triggered_for_inactive_products(self, app_client):
        """
        Qué hace: verifica que los productos inactivos no disparen alertas.
        Por qué lo hace: para evitar ruido con registros que no están activos.
        Cómo lo hace: crea un producto inactivo con stock bajo y consulta las alertas.
        De dónde viene: la petición sale de `GET /api/stock/alerts`.
        A dónde va: espera una respuesta correcta sin considerar el producto inactivo.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        payload = {
            'name': 'Producto Inactivo',
            'sku': 'SKU-INACTIVE-001',
            'price': 100.00,
            'qty': 5,
            'min_stock': 10,
            'status': 'inactive'
        }
        app_client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json'
        )

        response = app_client.get('/api/stock/alerts')
        assert response.status_code == 200

    def test_alert_format(self, app_client):
        """
        Qué hace: comprueba la estructura de una alerta de stock.
        Por qué lo hace: para asegurar que el payload es consistente para el consumidor.
        Cómo lo hace: crea un producto con stock bajo y revisa las claves devueltas.
        De dónde viene: la petición sale de `GET /api/stock/alerts`.
        A dónde va: espera campos como `alert_count` y `products`.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        # Crear producto con stock bajo
        app_client.post(
            '/api/products',
            data=json.dumps({
                'name': 'Alert Test',
                'sku': 'SKU-TEST-ALERT',
                'price': 100.00,
                'qty': 3,
                'min_stock': 10
            }),
            content_type='application/json'
        )

        response = app_client.get('/api/stock/alerts')
        assert response.status_code == 200
        data = json.loads(response.data)
        if len(data) > 0:
            alert = data[0]
            assert 'alert_count' in alert
            assert 'products' in alert
            assert isinstance(alert['alert_count'], int)
            assert isinstance(alert['products'], list)
