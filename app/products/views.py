from flask import request, jsonify
from app.database import db
from app.products.models import Product
from app.auth.middleware import require_scope, require_jwt
from flask_smorest import Blueprint
from marshmallow import Schema, fields, validate

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
@require_jwt
@require_scope('product:view')
def get_products():
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
@require_jwt
@require_scope('product:manage')
@products_bp.arguments(ProductSchema)
def create_product(data):
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
    return jsonify(new_product.to_dict()), 201

@products_bp.route('/<int:product_id>', methods=['PUT'])
@require_jwt
@require_scope('product:manage')
@products_bp.arguments(ProductUpdateSchema)
def update_product(data, product_id):
    try:
        product = Product.query.get(product_id)
    except OverflowError:
        return jsonify({'error': 'Product not found, try another ID'}), 404
    if not product:
        return jsonify({'error': 'Product not found, try another ID'}), 404

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

    db.session.commit()
    return jsonify(product.to_dict()), 200


@products_bp.route('/<int:product_id>', methods=['GET'])
@require_jwt
@require_scope('product:view')
def get_single_product(product_id):
    try:
        product = Product.query.get(product_id)
    except OverflowError:
        return jsonify({'error': 'Product not found, try another ID'}), 404
    if not product:
        return jsonify({'error': 'Product not found, try another ID'}), 404
    return jsonify(product.to_dict()), 200

@products_bp.route('/<int:product_id>', methods=['DELETE'])
@require_jwt
@require_scope('product:manage')
def delete_product(product_id):
    try:
        product = Product.query.get(product_id)
    except OverflowError:
        return jsonify({'error': 'Product not found, try another ID'}), 404
    if not product:
        return jsonify({'error': 'Product not found, try another ID'}), 404

    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': f'Product {product_id} deleted successfully'}), 200