"""
Tests para la lógica de stock (movimientos y alertas)
"""
import json


class TestStockMovement:
    """Tests para movimientos de stock"""

    def test_create_stock_entry_movement(self, app_client):
        """Test: crear un movimiento de entrada (entry)"""
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
        """Test: crear un movimiento de salida (exit)"""
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
        """Test: no permitir salida que dejaría stock negativo"""
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
        """Test: intentar movimiento de producto que no existe"""
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
        """Test: movimiento sin campos requeridos"""
        payload = {'product_id': 1, 'type': 'entry'}
        response = app_client.post(
            '/api/stock/movement',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 422

    def test_movement_invalid_type(self, app_client):
        """Test: tipo de movimiento inválido"""
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
        assert response.status_code == 400


class TestStockHistory:
    """Tests para el historial de movimientos"""

    def test_get_stock_history(self, app_client):
        """Test: obtener historial de movimientos"""
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
        """Test: filtrar historial por producto"""
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
        """Test: filtrar historial por tipo de movimiento"""
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
        """Test: obtener alertas cuando no hay productos con stock bajo"""
        response = app_client.get('/api/stock/alerts')
        assert response.status_code == 200

    def test_get_stock_alerts_with_low_stock(self, app_client):
        """Test: obtener alertas cuando hay productos con stock bajo"""
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
        """Test: alertas no se disparan para productos inactivos"""
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
        """Test: verificar que el formato de la alerta es correcto"""
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
