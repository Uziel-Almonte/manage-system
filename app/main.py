from flask import Flask
from sqlalchemy import text
from dotenv import load_dotenv
import os
from app.database import db
from app.stock.views import stock_bp
# from app.reports.views import reports_bp
from app.products.views import products_bp
from app.auth.views import auth_bp
from flask_migrate import Migrate


load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

app.register_blueprint(stock_bp)
# app.register_blueprint(reports_bp)
app.register_blueprint(products_bp)
app.register_blueprint(auth_bp)

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
