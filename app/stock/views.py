from flask import Blueprint

stock_bp = Blueprint('stock', __name__, url_prefix='/stock')

@stock_bp.route('/')
def stock_index():
    return {"message": "Gotta love the stock market!, not those type of stocks bro."}