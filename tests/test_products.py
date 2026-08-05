"""
Tests para el servicio de productos (CRUD y validaciones)
"""
import json


class TestProductCRUD:
    """Tests para las operaciones CRUD de productos"""

    def test_get_products_empty(self, app_client):
        """
        Qué hace: verifica que el listado de productos vacío responda correctamente.
        Por qué lo hace: para confirmar el comportamiento base cuando no hay inventario.
        Cómo lo hace: hace un GET al endpoint y comprueba total y lista vacía.
        De dónde viene: la petición sale de `GET /api/products`.
        A dónde va: espera un JSON con `total` en cero y `products` vacío.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        response = app_client.get('/api/products')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['total'] == 0
        assert data['products'] == []

    def test_create_product_success(self, app_client):
        """
        Qué hace: valida que un producto se cree correctamente.
        Por qué lo hace: para asegurar que el endpoint de alta funciona con datos válidos.
        Cómo lo hace: envía un JSON completo y comprueba el 201 y los campos devueltos.
        De dónde viene: la petición sale de `POST /api/products`.
        A dónde va: espera el producto creado en la respuesta.
        Librerías externas: usa Flask y la validación del endpoint.
        """
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
        """
        Qué hace: valida que no se pueda crear un producto sin campos mínimos.
        Por qué lo hace: para proteger el esquema de entrada de la API.
        Cómo lo hace: envía un JSON incompleto y revisa el código HTTP.
        De dónde viene: la petición sale de `POST /api/products`.
        A dónde va: espera un error de validación.
        Librerías externas: usa Flask y Marshmallow vía el endpoint.
        """
        payload = {'sku': 'SKU-001', 'price': 100.00}
        response = app_client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 422

    def test_create_product_duplicate_sku(self, app_client):
        """
        Qué hace: comprueba que el SKU duplicado sea rechazado.
        Por qué lo hace: para mantener unicidad de identificadores de producto.
        Cómo lo hace: crea un producto y luego intenta crear otro con el mismo SKU.
        De dónde viene: ambas peticiones salen de `POST /api/products`.
        A dónde va: espera un error 400 en el segundo intento.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
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
        """
        Qué hace: verifica que un producto creado se pueda leer por ID.
        Por qué lo hace: para validar persistencia y recuperación del registro.
        Cómo lo hace: crea el producto, toma su ID y lo consulta con GET.
        De dónde viene: las peticiones salen de `/api/products` y `/api/products/<id>`.
        A dónde va: espera que el nombre leído coincida con el creado.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
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
        """
        Qué hace: comprueba el manejo de un producto inexistente.
        Por qué lo hace: para asegurar una respuesta clara ante IDs inválidos.
        Cómo lo hace: consulta un ID ficticio y revisa el estado HTTP.
        De dónde viene: la petición sale de `GET /api/products/9999`.
        A dónde va: espera un 404.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        response = app_client.get('/api/products/9999')
        assert response.status_code == 404

    def test_update_product_success(self, app_client):
        """
        Qué hace: valida que un producto se actualice correctamente.
        Por qué lo hace: para asegurar que el endpoint de edición modifica el registro.
        Cómo lo hace: crea un producto y luego envía un PUT con nuevos valores.
        De dónde viene: la petición sale de `PUT /api/products/<id>`.
        A dónde va: espera que el nombre y el precio cambien en la respuesta.
        Librerías externas: usa Flask y SQLAlchemy vía el endpoint.
        """
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
        """
        Qué hace: verifica que actualizar un producto inexistente falle.
        Por qué lo hace: para mantener consistencia en el manejo de IDs inválidos.
        Cómo lo hace: envía un PUT contra un ID ficticio y revisa el código.
        De dónde viene: la petición sale de `PUT /api/products/9999`.
        A dónde va: espera un 404.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        payload = {'name': 'Algo'}
        response = app_client.put(
            '/api/products/9999',
            data=json.dumps(payload),
            content_type='application/json'
        )
        assert response.status_code == 404

    def test_delete_product_success(self, app_client):
        """
        Qué hace: comprueba que un producto se pueda eliminar.
        Por qué lo hace: para validar el ciclo completo de borrado.
        Cómo lo hace: crea el producto, lo elimina y verifica que ya no se pueda leer.
        De dónde viene: la petición sale de `DELETE /api/products/<id>`.
        A dónde va: espera un 200 en el borrado y un 404 en la lectura posterior.
        Librerías externas: usa Flask y SQLAlchemy a través del endpoint.
        """
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
        """
        Qué hace: valida la respuesta al intentar borrar un producto inexistente.
        Por qué lo hace: para asegurar que el endpoint no falle de forma inesperada.
        Cómo lo hace: hace un DELETE sobre un ID ficticio.
        De dónde viene: la petición sale de `DELETE /api/products/9999`.
        A dónde va: espera un 404.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        response = app_client.delete('/api/products/9999')
        assert response.status_code == 404


class TestProductSearch:
    """Tests para búsqueda y filtrado de productos"""

    def test_search_by_name(self, app_client):
        """
        Qué hace: verifica la búsqueda de productos por nombre.
        Por qué lo hace: para confirmar que el filtro de texto funcione.
        Cómo lo hace: crea varios productos y consulta con un término de búsqueda.
        De dónde viene: la petición sale de `GET /api/products?search=...`.
        A dónde va: espera una lista filtrada por coincidencia.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        payload1 = {'name': 'Laptop Dell', 'sku': 'LAPTOP-001', 'price': 999.99}
        payload2 = {'name': 'Mouse Logitech', 'sku': 'MOUSE-001', 'price': 29.99}
        app_client.post('/api/products', data=json.dumps(payload1), content_type='application/json')
        app_client.post('/api/products', data=json.dumps(payload2), content_type='application/json')

        response = app_client.get('/api/products?search=Laptop')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['total'] >= 1

    def test_filter_by_category(self, app_client):
        """
        Qué hace: valida el filtro por categoría.
        Por qué lo hace: para permitir segmentar el inventario por área o tipo.
        Cómo lo hace: crea productos de categorías distintas y consulta una categoría concreta.
        De dónde viene: la petición sale de `GET /api/products?category=...`.
        A dónde va: espera una respuesta filtrada.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        payload1 = {'name': 'Electronics Item', 'sku': 'ELEC-1', 'price': 50.00, 'category': 'Electronics'}
        payload2 = {'name': 'Furniture Item', 'sku': 'FURN-1', 'price': 30.00, 'category': 'Furniture'}
        app_client.post('/api/products', data=json.dumps(payload1), content_type='application/json')
        app_client.post('/api/products', data=json.dumps(payload2), content_type='application/json')

        response = app_client.get('/api/products?category=Electronics')
        assert response.status_code == 200

    def test_pagination(self, app_client):
        """
        Qué hace: comprueba la paginación del listado de productos.
        Por qué lo hace: para garantizar que el endpoint entregue páginas manejables.
        Cómo lo hace: crea suficientes productos y consulta páginas distintas.
        De dónde viene: la petición sale de `GET /api/products?page=...&per_page=...`.
        A dónde va: espera un subconjunto de productos por página.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
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
        """
        Qué hace: verifica el ordenamiento por precio.
        Por qué lo hace: para confirmar que el endpoint respeta el criterio de sort.
        Cómo lo hace: crea productos con precios distintos y consulta en orden ascendente.
        De dónde viene: la petición sale de `GET /api/products?sort_by=price&sort_order=asc`.
        A dónde va: espera un arreglo ordenado por precio.
        Librerías externas: usa Flask a través del cliente de prueba.
        """
        payload1 = {'name': 'Caro', 'sku': 'CARO-001', 'price': 1000.00}
        payload2 = {'name': 'Barato', 'sku': 'BARATO-001', 'price': 10.00}
        app_client.post('/api/products', data=json.dumps(payload1), content_type='application/json')
        app_client.post('/api/products', data=json.dumps(payload2), content_type='application/json')

        response = app_client.get('/api/products?sort_by=price&sort_order=asc')
        assert response.status_code == 200
        data = json.loads(response.data)
        if len(data['products']) >= 2:
            assert data['products'][0]['price'] <= data['products'][1]['price']
