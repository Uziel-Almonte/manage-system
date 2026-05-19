from flask_smorest import Blueprint

reports_bp = Blueprint('reports', 'reports', url_prefix='/reports', description="Endpoints for reports")

@reports_bp.route('/')
def reports_index():
    return {"message": "Reports endpoint"}