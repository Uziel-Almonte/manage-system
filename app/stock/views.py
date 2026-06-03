from flask import request, jsonify
from flask_smorest import Blueprint
from app.database import db
from app.stock.models import StockMovement
from app.products.models import Product
from app.auth.middleware import require_scope
from marshmallow import Schema, fields
from datetime import datetime

class StockMovementSchema(Schema):
    product_id = fields.Integer(required=True)
    type = fields.String(required=True)
    qty_change = fields.Integer(required=True)
    notes = fields.String()
    user = fields.String()

stock_bp = Blueprint('stock', 'stock', url_prefix='/api/stock', description="Endpoints for stock operations")

@stock_bp.route('/movement', methods=['POST'])
@require_scope('stock:manage')
@stock_bp.arguments(StockMovementSchema)
def add_movement(data):
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

@stock_bp.route('/history', methods=['GET'])
@require_scope('stock:view')
def get_history():
    product_id = request.args.get('product_id', type=int)
    movement_type = request.args.get('type')
    user = request.args.get('user')

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    query = StockMovement.query

    if product_id:
        query = query.filter_by(product_id=product_id)
    if movement_type:
        query = query.filter_by(type=movement_type)
    if user:
        query = query.filter_by(user=user)
    if date_from:
        try:
            query = query.filter(StockMovement.date >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(StockMovement.date <= datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass

    movements = query.order_by(StockMovement.date.desc()).all()
    return jsonify([m.to_dict() for m in movements]), 200


@stock_bp.route('/alerts', methods=['GET'])
@require_scope('stock:view')
def get_alerts():

    alert_products = Product.query.filter(
        Product.qty <= Product.min_stock,
        Product.status == 'active'
    ).all()

    return jsonify([{
        "alert_count": len(alert_products),
        "products": [p.to_dict() for p in alert_products]
    }]), 200