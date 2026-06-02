from flask import Flask, render_template
from sqlalchemy import text
from dotenv import load_dotenv
import os
from app.database import db
from app.stock.views import stock_bp
from app.reports.views import reports_bp
from app.products.views import products_bp
from app.auth.views import auth_bp
from app.auth.middleware import require_jwt, login_required
from app.audit.views import audit_bp
from app.audit.listeners import register_audit_listeners
from flask_migrate import Migrate
from flask_smorest import Api


from flask_cors import CORS

load_dotenv()

app = Flask(__name__, template_folder='templates')
# Enable CORS for the application
CORS(app, resources={r"/*": {"origins": "*"}})

app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['API_TITLE'] = 'Inventory Management API'
app.config['API_VERSION'] = 'v1'
app.config['OPENAPI_VERSION'] = '3.0.3'
app.config['OPENAPI_URL_PREFIX'] = '/'
app.config['OPENAPI_SWAGGER_UI_PATH'] = '/docs'
app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"


from app.auth.views import init_oauth
init_oauth(app)

db.init_app(app)
migrate = Migrate(app, db)

api = Api(app)

# Registrar los event listeners de auditoría
register_audit_listeners()

from app.products.models import Product
from app.stock.models import StockMovement

api.register_blueprint(stock_bp)
api.register_blueprint(reports_bp)
api.register_blueprint(products_bp)
api.register_blueprint(auth_bp)
api.register_blueprint(audit_bp)

@app.route("/")
@login_required
def index():
    total_products = Product.query.filter_by(status='active').count()
    low_stock_count = Product.query.filter(Product.qty <= Product.min_stock, Product.qty > 0, Product.status == 'active').count()
    critical_stock_count = Product.query.filter(Product.qty == 0, Product.status == 'active').count()
    total_movements = StockMovement.query.count()
    
    recent_movements = StockMovement.query.order_by(StockMovement.date.desc()).limit(5).all()

    return render_template('index.html',
                           total_products=total_products,
                           low_stock_count=low_stock_count,
                           critical_stock_count=critical_stock_count,
                           total_movements=total_movements,
                           recent_movements=recent_movements)

@app.route("/products")
@login_required
def products_ui():
    return "Products UI coming soon!"

@app.route("/stock")
@login_required
def stock_ui():
    return "Stock UI coming soon!"

@app.route("/reports")
@login_required
def reports_ui():
    return "Reports UI coming soon!"

@app.route("/audit")
@login_required
def audit_ui():
    return "Audit UI coming soon!"

@app.route("/health")
@require_jwt
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500
