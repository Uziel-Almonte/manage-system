from flask import request, jsonify
from flask_smorest import Blueprint
from app.database import db
from app.audit.models import AuditLog
from app.auth.middleware import require_scope

audit_bp = Blueprint('audit', 'audit', url_prefix='/api/audit', description="Endpoints for audit logs")

"""
QUÉ HACE:
    Obtiene registros de auditoría mediante una petición GET.

CÓMO LO HACE:
    Recibe filtros opcionales desde los parámetros de consulta de la URL,
    construye una consulta sobre AuditLog, aplica los filtros recibidos,
    cuenta los registros encontrados y finalmente obtiene los resultados
    utilizando paginación mediante limit y offset.

POR QUÉ LO HACE:
    Permite consultar el historial general de auditoría sin necesidad
    de acceder directamente a la base de datos. Los filtros permiten
    localizar operaciones específicas sobre determinadas tablas,
    registros o tipos de acción.

DE DÓNDE VIENE:
    Se ejecuta cuando un cliente realiza una petición GET a
    /api/audit. Los filtros vienen desde request.args.

A DÓNDE VA:
    Devuelve una respuesta HTTP 200 con los registros de auditoría
    convertidos a diccionarios JSON mediante AuditLog.to_dict().
"""
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

"""
QUÉ HACE:
    Obtiene exclusivamente el historial de auditoría de un producto.

CÓMO LO HACE:
    Recibe el ID del producto directamente desde la URL y consulta
    AuditLog buscando registros cuya tabla sea 'products' y cuyo
    record_id coincida con el producto solicitado. También permite
    utilizar limit y offset para paginar los resultados.

POR QUÉ LO HACE:
    Permite consultar rápidamente todo el historial de modificaciones,
    inserciones y eliminaciones relacionadas con un producto específico.

DE DÓNDE VIENE:
    Se ejecuta mediante una petición GET a
    /api/audit/product/<product_id>.
    El product_id proviene directamente de la URL.

A DÓNDE VA:
    Devuelve los registros de auditoría del producto en formato JSON.
    Si no existen registros, devuelve un error 404.
"""
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

"""
QUÉ HACE:
    Obtiene exclusivamente el historial de auditoría de un movimiento
    de inventario.

CÓMO LO HACE:
    Recibe el ID del movimiento desde la URL y consulta AuditLog
    filtrando por la tabla 'stock_movements' y por el ID recibido.
    También utiliza limit y offset para controlar la paginación.

POR QUÉ LO HACE:
    Permite consultar el historial de operaciones asociadas a un
    movimiento específico de inventario, facilitando el seguimiento
    de sus modificaciones y eliminación.

DE DÓNDE VIENE:
    Se ejecuta mediante una petición GET a
    /api/audit/movement/<movement_id>.
    El movement_id proviene de la URL.

A DÓNDE VA:
    Devuelve los registros de auditoría del movimiento en formato JSON.
    Si no existen registros asociados, devuelve una respuesta 404.
"""
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
