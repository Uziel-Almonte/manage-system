from flask import Blueprint, request, jsonify
from app.database import db
from app.products.models import Product

products_bp = Blueprint('products', __name__, url_prefix='/products')

@products_bp.route('', methods=['GET'])
def get_products():
    products = Product.query.all()
    return jsonify([product.to_dict() for product in products]), 200

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