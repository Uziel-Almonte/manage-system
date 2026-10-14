from app.database import db
from app.stock.models import StockMovement

"""
QUÉ:
    Registra un movimiento de stock en la base de datos, almacenando la
    información necesaria para mantener un historial de los cambios
    realizados sobre el inventario de un producto.

CÓMO:
    Crea una instancia de StockMovement utilizando el producto recibido,
    el tipo de movimiento, las cantidades anterior y nueva, el usuario
    responsable y las notas asociadas. Luego agrega el nuevo movimiento
    a la sesión de SQLAlchemy mediante db.session.add(). La función no
    realiza directamente el commit, por lo que la persistencia definitiva
    queda a cargo de la transacción que inició el proceso que la invocó.

POR QUÉ:
    Se utiliza para centralizar el registro de los movimientos de stock
    y evitar que cada proceso que modifica el inventario tenga que crear
    manualmente un registro de StockMovement. De esta manera, cada cambio
    puede quedar asociado con la cantidad anterior, la cantidad nueva,
    el tipo de movimiento y el usuario que lo realizó.

DE DÓNDE VIENE:
    Recibe como parámetros el producto afectado, el tipo de movimiento,
    la cantidad anterior y nueva, y opcionalmente el usuario y las notas.
    Normalmente es llamada por otras funciones del servicio de stock que
    necesitan registrar un cambio en el inventario.

A DÓNDE VA:
    Crea un objeto StockMovement y lo agrega a db.session para que forme
    parte de la transacción actual de la base de datos. Finalmente,
    devuelve el objeto movement creado para que el proceso que llamó a
    esta función pueda seguir utilizándolo o dejar que la transacción
    lo persista mediante commit().
"""
def register_stock_movement(product, movement_type, previous_qty, new_qty, user='system', notes=''):
    movement = StockMovement(
        product_id=product.id,
        user=user,
        type=movement_type,
        prev_qty=previous_qty,
        new_qty=new_qty,
        notes=notes,
    )
    db.session.add(movement)
    return movement

"""
QUÉ:
    Registra un movimiento producido específicamente por un cambio en la
    cantidad de stock de un producto.

CÓMO:
    Compara la cantidad anterior con la nueva cantidad. Si la nueva
    cantidad es mayor, determina que se trata de una entrada de stock
    ('entry'). Si la nueva cantidad es menor o igual, determina que se
    trata de una salida ('exit'). Después delega el registro real del
    movimiento a register_stock_movement(), enviándole los datos ya
    preparados.

POR QUÉ:
    Su propósito es evitar que los procesos que realizan actualizaciones
    manuales de cantidad tengan que determinar y construir por separado
    el tipo de movimiento. La función encapsula esta regla de negocio y
    reutiliza register_stock_movement() para mantener un único punto
    responsable de crear los registros de StockMovement.

DE DÓNDE VIENE:
    Recibe el producto cuyo stock fue modificado, la cantidad que tenía
    anteriormente y la nueva cantidad. También puede recibir el usuario
    responsable y una descripción del cambio. Normalmente es llamada por
    procesos que actualizan directamente la cantidad disponible de un
    producto.

A DÓNDE VA:
    Determina el tipo de movimiento y envía la información a
    register_stock_movement(). Esta función crea y agrega el registro
    StockMovement a la sesión de SQLAlchemy y devuelve dicho objeto.
    Al igual que la función anterior, no ejecuta commit() por sí misma.
"""
def register_qty_change_movement(product, previous_qty, new_qty, user='system', notes='Actualización manual de stock'):
    movement_type = 'entry' if new_qty > previous_qty else 'exit'
    return register_stock_movement(
        product,
        movement_type,
        previous_qty,
        new_qty,
        user=user,
        notes=notes,
    )
