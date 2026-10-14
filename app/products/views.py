from flask import request, jsonify
from app.database import db
from app.products.models import Product
from app.auth.middleware import require_scope
from flask_smorest import Blueprint
from marshmallow import Schema, fields, validate
from app.telemetry import record_product_created, sync_active_products_total, record_stock_movement
from app.stock.services import register_qty_change_movement

_INT_RANGE = validate.Range(min=0, max=2_147_483_647)
_PRICE_RANGE = validate.Range(min=0, max=999_999_999.99)

class ProductSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=1, max=100))
    sku = fields.String(required=True, validate=validate.Length(min=1, max=50))
    price = fields.Float(required=True, validate=_PRICE_RANGE)
    description = fields.String(load_default=None)
    category = fields.String(load_default=None, validate=validate.Length(max=50))
    qty = fields.Integer(load_default=0, validate=_INT_RANGE)
    min_stock = fields.Integer(load_default=0, validate=_INT_RANGE)
    status = fields.String(load_default='active', validate=validate.OneOf(['active', 'inactive']))

class ProductUpdateSchema(Schema):
    name = fields.String(validate=validate.Length(min=1, max=100))
    sku = fields.String(validate=validate.Length(min=1, max=50))
    price = fields.Float(validate=_PRICE_RANGE)
    description = fields.String()
    category = fields.String(validate=validate.Length(max=50))
    qty = fields.Integer(validate=_INT_RANGE)
    min_stock = fields.Integer(validate=_INT_RANGE)
    status = fields.String(validate=validate.OneOf(['active', 'inactive']))

products_bp = Blueprint('products', 'products', url_prefix='/api/products', description="Endpoints for managing products in the inventory")

@products_bp.route('', methods=['GET'])
@require_scope('product:view')
def get_products():
    """
    Qué hace: devuelve una lista paginada de productos con búsqueda, filtro y ordenamiento.
    Por qué lo hace: para exponer el inventario a clientes o pantallas que lo necesiten consumir.
    Cómo lo hace: lee query params, construye una consulta SQLAlchemy, aplica filtros y paginación, y serializa cada producto.
    De dónde viene: la petición llega desde `GET /api/products` con parámetros opcionales en la URL.
    A dónde va: responde con un JSON que contiene total de páginas, página actual y la lista de productos.
    Librerías externas: usa Flask para leer la request y SQLAlchemy/Marshmallow para la consulta y serialización.
    """
    search = request.args.get('search')
    category = request.args.get('category')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    sort_by = request.args.get('sort_by', 'id')
    sort_order = request.args.get('sort_order', 'asc')

    query = Product.query
    if search:
        search_pattern = f"%{search}%"
        query = query.filter((Product.name.ilike(search_pattern)) | (Product.sku.ilike(search_pattern)))

    if category:
        query = query.filter_by(category=category)

    valid_sort_columns = ['id', 'name', 'sku', 'price', 'qty', 'min_stock']
    if sort_by in valid_sort_columns:
        column = getattr(Product, sort_by)
        if sort_order.lower() == 'desc':
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())

    paginated_products = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "total": paginated_products.total,
        "pages": paginated_products.pages,
        "current_page": paginated_products.page,
        "products": [product.to_dict() for product in paginated_products.items]
    }), 200

@products_bp.route('', methods=['POST'])
@require_scope('product:manage')
@products_bp.arguments(ProductSchema)
def create_product(data):
    """
    Qué hace: crea un producto nuevo a partir de datos validados por Marshmallow.
    Por qué lo hace: para persistir productos desde la API y mantener el inventario actualizado.
    Cómo lo hace: valida el payload, evita SKU duplicado, guarda el registro en la base de datos y actualiza métricas de telemetría.
    De dónde viene: los datos llegan de un cliente que hace `POST /api/products` con JSON.
    A dónde va: responde con el producto creado o un error si la validación o la base de datos fallan.
    Librerías externas: usa Flask, Flask-Smorest/Marshmallow para validar el body, SQLAlchemy para persistir y telemetría para métricas.
    """
    if not data or not data.get('name') or not data.get('sku') or not data.get('price'):
        return jsonify({'error': 'Name, SKU, and price are required fields'}), 400
    
    existing_product = Product.query.filter_by(sku=data['sku']).first()
    if existing_product:
        return jsonify({'error': 'A product with this SKU already exists'}), 400

    new_product = Product(
        name=data['name'],
        sku=data['sku'],
        description=data.get('description'),
        category=data.get('category'),
        price=data['price'],
        qty=data.get('qty', 0),
        min_stock=data.get('min_stock', 0),
        status=data.get('status', 'active')
    )

    db.session.add(new_product)
    db.session.commit()

    record_product_created()
    sync_active_products_total()

    return jsonify(new_product.to_dict()), 201

@products_bp.route('/<int:product_id>', methods=['PUT'])
@require_scope('product:manage')
@products_bp.arguments(ProductUpdateSchema)
def update_product(data, product_id):
    """
    Qué hace: actualiza un producto existente con los campos enviados.
    Por qué lo hace: para mantener la información del inventario sincronizada con la API.
    Cómo lo hace: carga el producto, aplica cambios parciales, valida SKU duplicado y registra movimientos si cambió la cantidad.
    De dónde viene: la orden llega desde `PUT /api/products/<product_id>` con un payload JSON.
    A dónde va: responde con el producto actualizado o un error si el ID no existe o la validación falla.
    Librerías externas: usa Flask, SQLAlchemy y la capa de stock/telemetría para crear el movimiento y actualizar métricas.
    """
    try:
        product = Product.query.get(product_id)
    except OverflowError:
        return jsonify({'error': 'Product not found, try another ID'}), 404
    if not product:
        return jsonify({'error': 'Product not found, try another ID'}), 404

    previous_qty = product.qty

    if 'name' in data:
        product.name = data['name']
    if 'sku' in data:
        existing = Product.query.filter_by(sku=data['sku']).first()
        if existing and existing.id != product.id:
            return jsonify({'error': 'Another product with this SKU already exists my dear friend'}), 400
        product.sku = data['sku']
    if 'description' in data:
        product.description = data['description']
    if 'category' in data:
        product.category = data['category']
    if 'price' in data:
        product.price = data['price']
    if 'qty' in data:
        product.qty = data['qty']
    if 'min_stock' in data:
        product.min_stock = data['min_stock']
    if 'status' in data:
        product.status = data['status']

    if 'qty' in data and data['qty'] != previous_qty:
        register_qty_change_movement(product, previous_qty, data['qty'])

    db.session.commit()
    if 'qty' in data and data['qty'] != previous_qty:
        record_stock_movement('entry' if data['qty'] > previous_qty else 'exit', product.sku)
    sync_active_products_total()
    return jsonify(product.to_dict()), 200


@products_bp.route('/<int:product_id>', methods=['GET'])
@require_scope('product:view')
def get_single_product(product_id):
    """
    Qué hace: devuelve un producto específico por su identificador.
    Por qué lo hace: para consultar el detalle de un elemento del inventario.
    Cómo lo hace: busca el registro por ID y lo serializa a JSON.
    De dónde viene: la petición llega desde `GET /api/products/<product_id>`.
    A dónde va: responde con el producto encontrado o un error si no existe.
    Librerías externas: usa Flask y SQLAlchemy para obtener el registro.
    """
    try:
        product = Product.query.get(product_id)
    except OverflowError:
        return jsonify({'error': 'Product not found, try another ID'}), 404
    if not product:
        return jsonify({'error': 'Product not found, try another ID'}), 404
    return jsonify(product.to_dict()), 200

@products_bp.route('/<int:product_id>', methods=['DELETE'])
@require_scope('product:manage')
def delete_product(product_id):
    """
    Qué hace: elimina un producto del sistema.
    Por qué lo hace: para retirar registros que ya no deben permanecer activos.
    Cómo lo hace: busca el producto por ID, lo borra de la base de datos y actualiza métricas de inventario.
    De dónde viene: la petición llega desde `DELETE /api/products/<product_id>`.
    A dónde va: responde con un mensaje de éxito o un error si el producto no existe.
    Librerías externas: usa Flask y SQLAlchemy para borrar el registro, y telemetría para recalcular métricas.
    """
    try:
        product = Product.query.get(product_id)
    except OverflowError:
        return jsonify({'error': 'Product not found, try another ID'}), 404
    if not product:
        return jsonify({'error': 'Product not found, try another ID'}), 404

    db.session.delete(product)
    db.session.commit()

    sync_active_products_total()
    
    return jsonify({'message': f'Product {product_id} deleted successfully'}), 200