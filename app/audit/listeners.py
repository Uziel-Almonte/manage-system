from app.database import db
from app.audit.models import AuditLog
from sqlalchemy import event, inspect
from flask import g
from decimal import Decimal
from datetime import datetime

def get_current_user():
    """Obtiene el usuario actual de Flask context"""
    return getattr(g, 'user', 'system')

def json_serialize(data):
    """Convierte valores no JSON-serializables"""
    result = {}
    for key, value in data.items():
        if isinstance(value, Decimal):
            result[key] = float(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif value is None:
            result[key] = None
        else:
            result[key] = value
    return result

def capture_changes(mapper, connection, target):
    """Captura cambios después de INSERT/UPDATE"""
    
    if not hasattr(target, '__tablename__'):
        return
    
    table_name = target.__tablename__
    if table_name not in ['products', 'stock_movements']:
        return
    
    # Obtén el estado actual del objeto
    state = inspect(target)
    
    # Determina si es INSERT o UPDATE
    if state.persistent:
        action = 'UPDATE'
        # Obtén los cambios
        old_values = {}
        new_values = {}
        
        for attr in state.attrs:
            if attr.history.has_changes():
                old_val = attr.history.deleted[0] if attr.history.deleted else None
                new_val = attr.value
                old_values[attr.key] = old_val
                new_values[attr.key] = new_val
        
        if not new_values:  # Sin cambios registrados
            return
        
        new_values = json_serialize(new_values)
        old_values = json_serialize(old_values)
    else:
        action = 'INSERT'
        old_values = None
        # Obtén valores nuevos
        new_values = {col.name: getattr(target, col.name) for col in mapper.columns}
        new_values = json_serialize(new_values)
    
    audit = AuditLog(
        table_name=table_name,
        record_id=target.id,
        action=action,
        old_values=old_values if action == 'UPDATE' else None,
        new_values=new_values,
        user=get_current_user(),
    )
    db.session.add(audit)

def capture_deletion(mapper, connection, target):
    """Captura eliminaciones"""
    table_name = target.__tablename__
    if table_name not in ['products', 'stock_movements']:
        return
    
    old_values = {col.name: getattr(target, col.name) for col in mapper.columns}
    old_values = json_serialize(old_values)
    
    audit = AuditLog(
        table_name=table_name,
        record_id=target.id,
        action='DELETE',
        old_values=old_values,
        new_values=None,
        user=get_current_user(),
    )
    db.session.add(audit)

def register_audit_listeners():
    """Registra los listeners en SQLAlchemy"""
    from app.products.models import Product
    from app.stock.models import StockMovement
    
    event.listen(Product, 'after_insert', capture_changes, propagate=True)
    event.listen(Product, 'after_update', capture_changes, propagate=True)
    event.listen(Product, 'after_delete', capture_deletion, propagate=True)
    
    event.listen(StockMovement, 'after_insert', capture_changes, propagate=True)
    event.listen(StockMovement, 'after_update', capture_changes, propagate=True)
    event.listen(StockMovement, 'after_delete', capture_deletion, propagate=True)