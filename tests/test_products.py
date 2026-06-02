"""
Tests para el servicio de productos (CRUD y validaciones)
"""
import json


class TestProductCRUD:
    """Tests para las operaciones CRUD de productos"""

    def test_get_products_empty(self, app_client):
        """Test: obtener lista de productos cuando está vacía"""
        response = app_client.get('/api/products')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['total'] == 0
        assert data['products'] == []

    def test_create_product_success(self, app_client):
        """Test: crear un producto correctamente"""
        payload = {
            'name': 'Nuevo Producto',
            'sku': 'SKU-NEW-001',
            'price': 99.99,
            'description': 'Descripción test',
            'category': 'Electronics',
            'qty': 100,
            'min_stock': 20
        }
        response = app_client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['name'] == 'Nuevo Producto'
        assert data['sku'] == 'SKU-NEW-001'
        assert data['price'] == 99.99

    def test_create_product_missing_required_fields(self, app_client):
        """Test: crear producto sin campos requeridos"""
        payload = {'sku': 'SKU-001', 'price': 100.00}
        response = app_client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 422

    def test_create_product_duplicate_sku(self, app_client):
        """Test: crear producto con SKU duplicado (debe fallar)"""
        payload1 = {'name': 'Producto 1', 'sku': 'SKU-DUP-001', 'price': 50.00}
        payload2 = {'name': 'Producto 2', 'sku': 'SKU-DUP-001', 'price': 75.00}
        app_client.post('/api/products', data=json.dumps(payload1), content_type='application/json')
        response = app_client.post(
            '/api/products',
            data=json.dumps(payload2),
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_create_and_get_product(self, app_client):
        """Test: crear un producto y luego obtenerlo"""
        payload = {'name': 'Producto Test', 'sku': 'SKU-TEST-001', 'price': 75.00, 'qty': 100}
        create_response = app_client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert create_response.status_code == 201
        product_id = json.loads(create_response.data)['id']

        get_response = app_client.get(f'/api/products/{product_id}')
        assert get_response.status_code == 200
        data = json.loads(get_response.data)
        assert data['name'] == 'Producto Test'

    def test_get_nonexistent_product(self, app_client):
        """Test: obtener un producto que no existe"""
        response = app_client.get('/api/products/9999')
        assert response.status_code == 404

    def test_update_product_success(self, app_client):
        """Test: actualizar un producto correctamente"""
        # Crear
        payload = {'name': 'Original', 'sku': 'SKU-UPDATE-001', 'price': 100.00}
        create_response = app_client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json'
        )
        product_id = json.loads(create_response.data)['id']

        # Actualizar
        update_payload = {'name': 'Actualizado', 'price': 150.00}
        response = app_client.put(
            f'/api/products/{product_id}',
            data=json.dumps(update_payload),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['name'] == 'Actualizado'
        assert data['price'] == 150.00

    def test_update_nonexistent_product(self, app_client):
        """Test: actualizar un producto que no existe"""
        payload = {'name': 'Algo'}
        response = app_client.put(
            '/api/products/9999',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 404

    def test_delete_product_success(self, app_client):
        """Test: eliminar un producto correctamente"""
        # Crear
        payload = {'name': 'Para Eliminar', 'sku': 'SKU-DELETE-001', 'price': 50.00}
        create_response = app_client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json'
        )
        product_id = json.loads(create_response.data)['id']

        # Eliminar
        response = app_client.delete(f'/api/products/{product_id}')
        assert response.status_code == 200

        # Verificar que fue eliminado
        response = app_client.get(f'/api/products/{product_id}')
        assert response.status_code == 404

    def test_delete_nonexistent_product(self, app_client):
        """Test: eliminar un producto que no existe"""
        response = app_client.delete('/api/products/9999')
        assert response.status_code == 404


class TestProductSearch:
    """Tests para búsqueda y filtrado de productos"""

    def test_search_by_name(self, app_client):
        """Test: buscar productos por nombre"""
        payload1 = {'name': 'Laptop Dell', 'sku': 'LAPTOP-001', 'price': 999.99}
        payload2 = {'name': 'Mouse Logitech', 'sku': 'MOUSE-001', 'price': 29.99}
        app_client.post('/api/products', data=json.dumps(payload1), content_type='application/json')
        app_client.post('/api/products', data=json.dumps(payload2), content_type='application/json')

        response = app_client.get('/api/products?search=Laptop')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['total'] >= 1

    def test_filter_by_category(self, app_client):
        """Test: filtrar productos por categoría"""
        payload1 = {'name': 'Electronics Item', 'sku': 'ELEC-1', 'price': 50.00, 'category': 'Electronics'}
        payload2 = {'name': 'Furniture Item', 'sku': 'FURN-1', 'price': 30.00, 'category': 'Furniture'}
        app_client.post('/api/products', data=json.dumps(payload1), content_type='application/json')
        app_client.post('/api/products', data=json.dumps(payload2), content_type='application/json')

        response = app_client.get('/api/products?category=Electronics')
        assert response.status_code == 200

    def test_pagination(self, app_client):
        """Test: paginación de productos"""
        for i in range(15):
            payload = {'name': f'Producto {i}', 'sku': f'SKU-PAGE-{i}', 'price': 50.00 + i}
            app_client.post('/api/products', data=json.dumps(payload), content_type='application/json')

        response = app_client.get('/api/products?page=1&per_page=10')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['products']) == 10

        response = app_client.get('/api/products?page=2&per_page=10')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['products']) >= 1

    def test_sort_by_price(self, app_client):
        """Test: ordenar productos por precio"""
        payload1 = {'name': 'Caro', 'sku': 'CARO-001', 'price': 1000.00}
        payload2 = {'name': 'Barato', 'sku': 'BARATO-001', 'price': 10.00}
        app_client.post('/api/products', data=json.dumps(payload1), content_type='application/json')
        app_client.post('/api/products', data=json.dumps(payload2), content_type='application/json')

        response = app_client.get('/api/products?sort_by=price&sort_order=asc')
        assert response.status_code == 200
        data = json.loads(response.data)
        if len(data['products']) >= 2:
            assert data['products'][0]['price'] <= data['products'][1]['price']
