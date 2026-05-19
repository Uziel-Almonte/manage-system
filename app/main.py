from flask import Flask
from sqlalchemy import text
from dotenv import load_dotenv
import os
from app.database import db
from app.stock.views import stock_bp
from app.reports.views import reports_bp
from app.products.views import products_bp
from app.auth.views import auth_bp
from app.audit.views import audit_bp
from app.audit.listeners import register_audit_listeners
from flask_migrate import Migrate
from flask_smorest import Api


load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['API_TITLE'] = 'Inventory Management API'
app.config['API_VERSION'] = 'v1'
app.config['OPENAPI_VERSION'] = '3.0.3'
app.config['OPENAPI_URL_PREFIX'] = '/'
app.config['OPENAPI_SWAGGER_UI_PATH'] = '/docs'
app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"


db.init_app(app)
migrate = Migrate(app, db)

api = Api(app)

# Registrar los event listeners de auditoría
register_audit_listeners()

api.register_blueprint(stock_bp)
api.register_blueprint(reports_bp)
api.register_blueprint(products_bp)
api.register_blueprint(auth_bp)
api.register_blueprint(audit_bp)

@app.route("/")
def index():
    return {"message": "Welcome to the Flask app!"}

@app.route("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500
