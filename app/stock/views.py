from flask import Blueprint, request, jsonify
from app.database import db
from app.stock.models import StockMovement
from app.products.models import Product

stock_bp = Blueprint('stock', __name__, url_prefix='/stock')

@stock_bp.route('/movement', methods=['POST'])
def add_movement():
    data =request.get_json()

    if not data or not data.get('product_id') or not data.get('type') or 'qty_change' not in data:
        return jsonify({"error": "product_id, type, and qty_change are required"}), 400
    
    product = Product.query.get(data['product_id'])
    if not product:
        return jsonify({"error": "Product not found"}), 404

    try:
        qty_change = int(data['qty_change'])
    except ValueError:
        return jsonify({"error": "qty_change must be an integer"}), 400

    movement_type = data['type']

    if movement_type == 'exit':
        if product.qty < qty_change:
            return jsonify({"error": "Not enough stock for this exit movement. Current stock: " + str(product.qty)}), 400
        new_qty = product.qty - qty_change
    elif movement_type == 'entry':
        new_qty = product.qty + qty_change
    else:
        return jsonify({"error": "Invalid movement type. Must be 'entry' or 'exit'."}), 400

    movement = StockMovement(
        product_id=product.id,
        user=data.get('user', 'system'),
        type=movement_type,
        prev_qty=product.qty,
        new_qty=new_qty,
        notes=data.get('notes', '')
    )

    product.qty = new_qty

    db.session.add(movement)
    db.session.commit()

    return jsonify(movement.to_dict()), 201