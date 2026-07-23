from app.database import db
from app.stock.models import StockMovement


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
