from flask import Blueprint, request, jsonify
from app.database import db
from app.products.models import Product

products_bp = Blueprint('products', __name__, url_prefix='/products')

@products_bp.route('', methods=['GET'])
def get_products():
    search = request.args.get('search')
    category = request.args.get('category')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    query = Product.query
    if search:
        search_pattern = f"%{search}%"
        query = query.filter((Product.name.ilike(search_pattern)) | (Product.sku.ilike(search_pattern)))

    if category:
        query = query.filter_by(category=category)

    paginated_products = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "total": paginated_products.total,
        "pages": paginated_products.pages,
        "current_page": paginated_products.page,
        "products": [product.to_dict() for product in paginated_products.items]
    }), 200

@products_bp.route('', methods=['POST'])
def create_product():
    data = request.get_json()

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
def update_product(product_id):
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found, try another ID'}), 404

    data = request.get_json()

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


@products_bp.route('/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found, try another ID'}), 404

    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': f'Product {product_id} deleted successfully'}), 200