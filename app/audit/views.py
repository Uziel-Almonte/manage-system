from flask import request, jsonify
from flask_smorest import Blueprint
from app.database import db
from app.audit.models import AuditLog
from app.auth.middleware import require_scope

audit_bp = Blueprint('audit', 'audit', url_prefix='/api/audit', description="Endpoints for audit logs")

@audit_bp.route('', methods=['GET'])
@require_scope('audit:view')
def get_audit_logs():
    """
    GET /audit?table=products&record_id=1&action=UPDATE&limit=50&offset=0
    Obtiene logs de auditoría con filtros opcionales
    """
    table = request.args.get('table', None)
    record_id = request.args.get('record_id', None, type=int)
    action = request.args.get('action', None)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    query = AuditLog.query
    
    if table:
        query = query.filter_by(table_name=table)
    if record_id:
        query = query.filter_by(record_id=record_id)
    if action:
        query = query.filter_by(action=action)
    
    total = query.count()
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset).all()
    
    return jsonify({
        'total': total,
        'limit': limit,
        'offset': offset,
        'data': [log.to_dict() for log in logs]
    }), 200

@audit_bp.route('/product/<int:product_id>', methods=['GET'])
@require_scope('audit:view')
def get_product_audit(product_id):
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    try:
        query = AuditLog.query.filter_by(
            table_name='products',
            record_id=product_id
        )
        total = query.count()
        logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset).all()
    except OverflowError:
        return jsonify({'total': 0, 'limit': limit, 'offset': offset, 'data': []}), 200

    if total == 0:
        return jsonify({'error': 'No audit logs found for this product'}), 404

    return jsonify({
        'total': total,
        'limit': limit,
        'offset': offset,
        'data': [log.to_dict() for log in logs]
    }), 200

@audit_bp.route('/movement/<int:movement_id>', methods=['GET'])
@require_scope('audit:view')
def get_movement_audit(movement_id):
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    try:
        query = AuditLog.query.filter_by(
            table_name='stock_movements',
            record_id=movement_id
        )
        total = query.count()
        logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset).all()
    except OverflowError:
        return jsonify({'total': 0, 'limit': limit, 'offset': offset, 'data': []}), 200

    if total == 0:
        return jsonify({'error': 'No audit logs found for this movement'}), 404

    return jsonify({
        'total': total,
        'limit': limit,
        'offset': offset,
        'data': [log.to_dict() for log in logs]
    }), 200
