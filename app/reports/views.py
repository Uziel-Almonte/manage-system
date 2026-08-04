from flask import jsonify, request
from flask_smorest import Blueprint
from sqlalchemy import func, desc
from app.database import db
from app.products.models import Product
from app.stock.models import StockMovement
from app.auth.middleware import require_scope

reports_bp = Blueprint('reports', 'reports', url_prefix='/api/reports', description="Endpoints for reports")


"""
QUÉ:
    Obtiene un reporte de los productos activos cuyo nivel actual de stock
    se encuentra en el mínimo establecido o por debajo de este.

CÓMO:
    Consulta los productos mediante Product.query y aplica dos condiciones:
    el stock actual (qty) debe ser menor o igual al stock mínimo (min_stock)
    y el producto debe encontrarse en estado 'active'.

    Después ordena los resultados de menor a mayor cantidad disponible,
    haciendo que los productos con menos stock aparezcan primero.

    Finalmente, convierte cada producto a un diccionario mediante
    to_dict() y construye una respuesta JSON que incluye la cantidad
    total de productos críticos y la información de cada uno.

POR QUÉ:
    Permite identificar rápidamente los productos que necesitan atención
    o reposición. El orden ascendente ayuda a priorizar aquellos que tienen
    una cantidad de stock más baja.

    El endpoint está protegido con el permiso 'report:view' para evitar
    que usuarios sin autorización puedan consultar los reportes.

DE DÓNDE VIENE:
    Recibe una petición HTTP GET dirigida a /api/reports/critical-stock.
    No requiere parámetros adicionales, ya que los criterios del reporte
    se determinan directamente a partir de los datos almacenados en los
    productos.

A DÓNDE VA:
    Consulta los productos en la base de datos y devuelve un objeto JSON
    con el número de productos encontrados y la lista de productos
    críticos. La respuesta utiliza el código HTTP 200.
"""
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


"""
QUÉ:
    Obtiene los productos activos que actualmente poseen las cantidades
    más altas de stock.

CÓMO:
    Obtiene el parámetro opcional 'limit' desde la URL. Si no se
    proporciona, utiliza 10 como valor predeterminado.

    Después consulta únicamente los productos cuyo estado es 'active',
    los ordena de mayor a menor cantidad disponible mediante Product.qty
    y limita el resultado al número indicado por el parámetro limit.

    Finalmente, convierte cada producto a un diccionario mediante
    to_dict() y devuelve la información en formato JSON.

POR QUÉ:
    Permite conocer cuáles son los productos que tienen mayor cantidad
    disponible actualmente. Este tipo de información puede ser útil para
    análisis generales del inventario y para generar reportes resumidos.

    Es importante destacar que este endpoint mide el stock actual, no la
    frecuencia de movimientos. Un producto con mucho stock aparecerá
    aquí aunque tenga pocos movimientos registrados.

DE DÓNDE VIENE:
    Recibe una petición HTTP GET dirigida a /api/reports/top-products.
    Opcionalmente puede recibir el parámetro 'limit' en la URL, por
    ejemplo: /api/reports/top-products?limit=20.

    El acceso está protegido por el permiso 'report:view'.

A DÓNDE VA:
    Consulta los productos activos en la base de datos y devuelve una
    respuesta JSON con los productos que ocupan las primeras posiciones
    según su cantidad de stock. La respuesta utiliza el código HTTP 200.
"""
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

"""
QUÉ:
    Obtiene los movimientos de stock registrados más recientemente en
    el sistema.

CÓMO:
    Obtiene el parámetro opcional 'limit' desde la URL. Si no se
    proporciona, utiliza 20 como cantidad predeterminada.

    Después consulta los registros StockMovement y los ordena por fecha
    de forma descendente mediante StockMovement.date.desc(), colocando
    primero los movimientos más recientes.

    Finalmente limita la cantidad de registros devueltos según el valor
    de limit y convierte cada movimiento a un diccionario mediante
    to_dict().

POR QUÉ:
    Permite consultar rápidamente las últimas operaciones realizadas sobre
    el inventario sin tener que recuperar todo el historial de movimientos.
    Esto resulta útil para supervisar las actividades recientes del stock.

    El permiso 'report:view' protege el acceso a la información del
    reporte.
    
DE DÓNDE VIENE:
    Recibe una petición HTTP GET dirigida a
    /api/reports/recent-movements.

    Puede recibir opcionalmente el parámetro 'limit', por ejemplo:
    /api/reports/recent-movements?limit=50.

A DÓNDE VA:
    Consulta los registros StockMovement almacenados en la base de datos,
    selecciona los más recientes según el límite solicitado y devuelve
    una respuesta JSON con la lista de movimientos. La respuesta utiliza
    el código HTTP 200.
"""
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