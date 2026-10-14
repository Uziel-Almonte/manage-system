from flask import request, jsonify
from flask_smorest import Blueprint
from app.database import db
from app.stock.models import StockMovement
from app.products.models import Product
from app.auth.middleware import require_scope
from marshmallow import Schema, fields, validate
from datetime import datetime
from app.stock.services import register_stock_movement
from app.telemetry import record_stock_movement

"""
QUÉ:
    Define y valida la estructura de los datos que puede recibir el
    endpoint encargado de registrar movimientos de stock.

CÓMO:
    Utiliza Marshmallow para declarar los campos esperados, sus tipos,
    si son obligatorios y las restricciones que deben cumplir. El campo
    product_id debe ser un entero positivo, type solo puede ser 'entry'
    o 'exit', y qty_change debe ser un entero positivo. Los campos
    notes y user tienen valores predeterminados.

POR QUÉ:
    Centraliza la validación de los datos de entrada antes de que lleguen
    a la lógica del endpoint. Esto evita procesar valores inválidos y
    ayuda a mantener la integridad de las operaciones de stock.

DE DÓNDE VIENE:
    Es utilizado por Flask-Smorest mediante el decorador
    @stock_bp.arguments(StockMovementSchema) en el endpoint
    add_movement(). Los datos provienen del cuerpo JSON de una petición
    HTTP POST.

A DÓNDE VA:
    Si los datos cumplen las validaciones, Marshmallow los transforma y
    los entrega a add_movement() mediante el parámetro data. Si no
    cumplen, la petición es rechazada antes de ejecutar la función.
"""
class StockMovementSchema(Schema):
    product_id = fields.Integer(required=True, validate=validate.Range(min=1, max=2_147_483_647))
    type = fields.String(required=True, validate=validate.OneOf(['entry', 'exit']))
    qty_change = fields.Integer(required=True, validate=validate.Range(min=1, max=2_147_483_647))
    notes = fields.String(load_default='')
    user = fields.String(load_default='system')

stock_bp = Blueprint('stock', 'stock', url_prefix='/api/stock', description="Endpoints for stock operations")


"""
QUÉ:
    Registra una entrada o salida de stock para un producto y crea el
    registro correspondiente en el historial de movimientos.

CÓMO:
    Primero valida que los datos necesarios estén presentes y obtiene el
    producto mediante su product_id. Después determina la nueva cantidad
    de stock según el tipo de movimiento.

    Para una salida ('exit'), comprueba que exista suficiente stock antes
    de descontar la cantidad solicitada. Para una entrada ('entry'),
    incrementa directamente la cantidad disponible.

    Una vez calculada la nueva cantidad, actualiza product.qty y utiliza
    register_stock_movement() para crear el registro histórico. Luego
    confirma ambas modificaciones mediante db.session.commit() y registra
    el movimiento en el sistema de telemetría mediante
    record_stock_movement().

POR QUÉ:
    Es el punto de entrada de la API para modificar el inventario de un
    producto. Centraliza las reglas necesarias para evitar salidas de
    stock superiores a la cantidad disponible y garantiza que cada
    modificación quede registrada en el historial.

    Además, el uso de @require_scope('stock:manage') limita esta operación
    a usuarios que poseen el permiso necesario para administrar el stock.

DE DÓNDE VIENE:
    Recibe una petición HTTP POST dirigida a /api/stock/movement.
    Los datos llegan en formato JSON y son validados previamente por
    StockMovementSchema. El acceso también pasa por el middleware
    require_scope(), que verifica el permiso 'stock:manage'.

A DÓNDE VA:
    Si la operación es válida, modifica el stock del producto y crea un
    StockMovement asociado. Ambos cambios se confirman en la base de datos.
    Después se registra el evento en telemetría y se devuelve el movimiento
    creado en formato JSON con código HTTP 201.

    Si ocurre un error de validación o no existe el producto, se devuelve
    una respuesta HTTP 400 o 404 según corresponda.
"""
@stock_bp.route('/movement', methods=['POST'])
@require_scope('stock:manage')
@stock_bp.arguments(StockMovementSchema)
def add_movement(data):
    if not data or not data.get('product_id') or not data.get('type') or 'qty_change' not in data:
        return jsonify({"error": "product_id, type, and qty_change are required"}), 400

    try:
        product = Product.query.get(data['product_id'])
    except OverflowError:
        return jsonify({"error": "Product not found"}), 404

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

    previous_qty = product.qty
    product.qty = new_qty

    movement = register_stock_movement(
        product,
        movement_type,
        previous_qty=previous_qty,
        new_qty=new_qty,
        user=data.get('user', 'system'),
        notes=data.get('notes', ''),
    )

    db.session.commit()
    record_stock_movement(movement_type, product.sku)

    return jsonify(movement.to_dict()), 201

"""
QUÉ:
    Obtiene el historial de movimientos de stock registrados en el sistema,
    permitiendo consultar todos los movimientos o filtrarlos según
    diferentes criterios.

CÓMO:
    Obtiene los parámetros opcionales de la URL mediante request.args:
    product_id, type, user, date_from y date_to.

    A partir de StockMovement.query construye dinámicamente una consulta.
    Cada filtro se agrega únicamente cuando el usuario lo proporciona.

    Las fechas se convierten desde texto con formato YYYY-MM-DD a objetos
    datetime. Si una fecha no tiene el formato esperado, el filtro se
    ignora.

    Finalmente, los movimientos se ordenan de forma descendente por fecha,
    de manera que los registros más recientes aparezcan primero. Cada
    movimiento se transforma a un diccionario mediante to_dict() antes
    de enviarse como JSON.

POR QUÉ:
    Permite consultar y auditar los cambios realizados sobre el inventario
    sin necesidad de acceder directamente a la base de datos. Los filtros
    permiten localizar movimientos específicos por producto, tipo de
    operación, usuario o período de tiempo.

    El permiso 'stock:view' evita que cualquier usuario pueda consultar
    información del historial sin la autorización correspondiente.

DE DÓNDE VIENE:
    Recibe una petición HTTP GET dirigida a /api/stock/history.
    Los criterios de búsqueda, si existen, llegan como parámetros de
    consulta en la URL.

A DÓNDE VA:
    Consulta los registros StockMovement almacenados en la base de datos,
    los convierte a diccionarios mediante to_dict() y devuelve una lista
    JSON con código HTTP 200.
"""
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

"""
QUÉ:
    Obtiene los productos activos cuyo stock actual se encuentra en el
    nivel mínimo establecido o por debajo de este, generando así una
    consulta de productos que requieren atención.

CÓMO:
    Consulta la tabla de productos utilizando dos condiciones:
    la cantidad actual debe ser menor o igual al stock mínimo configurado
    para el producto y el estado del producto debe ser 'active'.

    Después construye una respuesta que contiene la cantidad total de
    productos encontrados y la información de cada producto mediante
    su método to_dict().

POR QUÉ:
    Permite detectar productos que tienen un nivel de inventario bajo y
    facilita que el sistema pueda informar al usuario que necesitan
    reposición. Solo se consideran productos activos, evitando generar
    alertas para productos que ya no forman parte del inventario operativo.

    El acceso está protegido por el permiso 'stock:view' porque consultar
    esta información forma parte de las operaciones de visualización del
    inventario.

DE DÓNDE VIENE:
    Recibe una petición HTTP GET dirigida a /api/stock/alerts. No necesita
    parámetros adicionales porque las condiciones de alerta se obtienen
    directamente de los valores almacenados en cada producto.

A DÓNDE VA:
    Consulta los productos que cumplen las condiciones de alerta y devuelve
    una respuesta JSON con el número de productos encontrados y la lista
    de productos afectados, utilizando código HTTP 200.
"""
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