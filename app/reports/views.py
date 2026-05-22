from flask import jsonify, request
from flask_smorest import Blueprint
from sqlalchemy import func, desc
from app.database import db
from app.products.models import Product
from app.stock.models import StockMovement
from app.auth.middleware import require_scope

reports_bp = Blueprint('reports', 'reports', url_prefix='/reports', description="Endpoints for reports")

@reports_bp.route('/critical-stock', methods=['GET'])
@require_scope('report:view')
def get_critical_stock():
    """
    GET /reports/critical-stock
    Returns a list of products whose quantity is less than or equal to their min_stock.
    """
    critical_products = Product.query.filter(
        Product.qty <= Product.min_stock,
        Product.status == 'active'
    ).order_by(Product.qty.asc()).all()

    return jsonify({
        "count": len(critical_products),
        "products": [product.to_dict() for product in critical_products]
    }), 200

@reports_bp.route('/top-products', methods=['GET'])
@require_scope('report:view')
def get_top_products():
    """
    Returns the top products based on highest quantity in stock.
    (Alternatively: you could group by StockMovements to see most frequently moved)
    """
    limit = request.args.get('limit', 10, type=int)

    top_products = Product.query.filter_by(status='active').order_by(Product.qty.desc()).limit(limit).all()

    return jsonify({
        "products": [product.to_dict() for product in top_products]
    }), 200

@reports_bp.route('/recent-movements', methods=['GET'])
@require_scope('report:view')
def get_recent_movements():
    """
    GET /reports/recent-movements?limit=20
    Returns the most recent stock movements.
    """
    limit = request.args.get('limit', 20, type=int)

    recent_movements = StockMovement.query.order_by(StockMovement.date.desc()).limit(limit).all()

    return jsonify({
        "movements": [movement.to_dict() for movement in recent_movements]
    }), 200