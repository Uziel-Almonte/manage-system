from flask import Blueprint

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

@reports_bp.route('/')
def reports_index():
    return {"message": "Reports endpoint"}