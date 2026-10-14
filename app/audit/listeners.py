from app.database import db
from app.audit.models import AuditLog
from sqlalchemy import event, inspect
from flask import g
from decimal import Decimal
from datetime import datetime

""" 
QUÉ HACE: Obtiene el usuario asociado a la petición actual de Flask. 
CÓMO LO HACE: Consulta el atributo 'user' dentro del objeto global 'g'. Si dicho atributo no existe, utiliza 'system' como usuario predeterminado. 
POR QUÉ LO HACE: La auditoría necesita identificar quién realizó cada operación sobre los registros auditados. En procesos ejecutados 
                fuera de una sesión de usuario, se utiliza 'system'. 
DE DÓNDE VIENE: El usuario normalmente es almacenado previamente en el contexto de Flask mediante 'g.user'. 
A DÓNDE VA: El usuario obtenido se utiliza posteriormente al crear un registro AuditLog y termina almacenado 
            en la columna 'user' de la tabla audit_logs. 
"""
def get_current_user():
    """Obtiene el usuario actual de Flask context"""
    return getattr(g, 'user', 'system')

""" 
QUÉ HACE: Convierte los valores de un diccionario a formatos compatibles con JSON. 
CÓMO LO HACE: Recorre todos los pares clave-valor del diccionario y transforma específicamente los objetos Decimal y 
            datetime a tipos que pueden ser almacenados en JSON. 
POR QUÉ LO HACE: Los campos old_values y new_values del modelo AuditLog son columnas JSON. 
            Tipos como Decimal y datetime no son serializables directamente por JSON, por lo que deben convertirse previamente. 
DE DÓNDE VIENE: Recibe un diccionario construido a partir de los atributos de los modelos auditados, principalmente Product y StockMovement. 
A DÓNDE VA: Devuelve un nuevo diccionario serializado que posteriormente se almacena en old_values o new_values del AuditLog. 
"""
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

"""
QUÉ HACE:
    Captura automáticamente las operaciones INSERT y UPDATE realizadas
    sobre las entidades que forman parte del sistema de auditoría.
CÓMO LO HACE:
    SQLAlchemy ejecuta esta función después de una operación INSERT o
    UPDATE gracias a los listeners registrados en
    register_audit_listeners().

    La función identifica la tabla afectada, inspecciona el estado
    del objeto y determina si se trata de una inserción o actualización.
    En una actualización compara los valores anteriores y actuales.
    Finalmente crea un objeto AuditLog y lo agrega a la sesión de
    SQLAlchemy.

POR QUÉ LO HACE:
    Permite mantener un historial automático de los cambios importantes
    realizados sobre productos y movimientos de inventario sin tener
    que escribir código de auditoría en cada operación CRUD.

DE DÓNDE VIENE:
    Es llamada automáticamente por SQLAlchemy como consecuencia de los
    eventos 'after_insert' y 'after_update' registrados para Product
    y StockMovement.

A DÓNDE VA:
    Genera un objeto AuditLog que posteriormente será persistido en
    la tabla audit_logs cuando la sesión de base de datos realice
    el commit correspondiente.
"""
def capture_changes(mapper, connection, target):
    """Captura cambios después de INSERT/UPDATE"""

    # Verifica que el objeto recibido tenga información de tabla. 
    # Esto evita intentar auditar objetos que no sean modelos SQLAlchemy 
    # con una tabla asociada.
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

"""
QUÉ HACE:
    Registra las eliminaciones realizadas sobre productos y movimientos
    de inventario.

CÓMO LO HACE:
    Obtiene el nombre de la tabla y todos los valores que tenía el
    registro antes de ser eliminado. Después crea un AuditLog con
    acción DELETE y guarda esos valores en old_values.

POR QUÉ LO HACE:
    Una vez eliminado un registro, sus datos dejan de estar disponibles
    en la tabla original. Guardar los valores anteriores permite conocer
    qué registro existía y qué información tenía antes de su eliminación.

DE DÓNDE VIENE:
    SQLAlchemy llama automáticamente a esta función mediante los eventos
    'after_delete' registrados para Product y StockMovement.

A DÓNDE VA:
    Genera un AuditLog que se almacena posteriormente en la tabla
    audit_logs.
"""
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

"""
    QUÉ HACE:
    Registra los listeners de auditoría que permiten detectar
    automáticamente INSERT, UPDATE y DELETE.

CÓMO LO HACE:
    Importa los modelos Product y StockMovement y utiliza
    event.listen() de SQLAlchemy para asociar cada evento de
    persistencia con la función encargada de capturarlo.

POR QUÉ LO HACE:
    Permite centralizar la auditoría en este módulo y evitar que
    cada operación CRUD tenga que crear manualmente un registro
    de auditoría.

DE DÓNDE VIENE:
    Esta función debe ser ejecutada durante la inicialización de
    la aplicación para configurar los listeners de SQLAlchemy.

A DÓNDE VA:
    Deja configurado SQLAlchemy para que, cuando Product o
    StockMovement sean insertados, actualizados o eliminados,
    se ejecuten automáticamente las funciones de auditoría
    correspondientes.
"""
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