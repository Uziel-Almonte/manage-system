from flask import Flask, render_template, request, flash, redirect, url_for
from sqlalchemy import text, or_
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
    critical_stock_count = Product.query.filter(Product.qty <= Product.min_stock * 0.2, Product.status == 'active').count()
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
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'id')
    sort_order = request.args.get('sort_order', 'desc')

    query = Product.query.filter_by(status='active')

    if search:
        query = query.filter(or_(
            Product.name.ilike(f'%{search}%'),
            Product.sku.ilike(f'%{search}%'),
            Product.category.ilike(f'%{search}%')
        ))

    if hasattr(Product, sort_by):
        column = getattr(Product, sort_by)
        if sort_order == 'desc':
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    if request.headers.get('HX-Request'):
        return render_template('products/partials/table.html', pagination=pagination, search=search, sort_by=sort_by, sort_order=sort_order)

    return render_template('products/index.html', pagination=pagination, search=search, sort_by=sort_by, sort_order=sort_order)

@app.route("/products/new")
@login_required
def new_product():
    return render_template('products/form.html', product=None)

@app.route("/products/<int:product_id>/edit")
@login_required
def edit_product(product_id):
    product = Product.query.get(product_id)
    if not product:
        flash('Producto no encontrado', 'error')
        return redirect(url_for('products_ui'))
    return render_template('products/form.html', product=product)

@app.route("/products", methods=['POST'])
@login_required
def create_product():
    name = request.form.get('name')
    sku = request.form.get('sku')
    price = request.form.get('price')
    description = request.form.get('description')
    category = request.form.get('category')
    qty = request.form.get('qty', 0)
    min_stock = request.form.get('min_stock', 0)
    status = request.form.get('status', 'active')

    if not name or not sku or not price:
        flash('Los campos nombre, SKU y precio son obligatorios', 'error')
        return redirect(url_for('new_product'))

    existing = Product.query.filter_by(sku=sku).first()
    if existing:
        flash('Ya existe un producto con este SKU', 'error')
        return redirect(url_for('new_product'))

    try:
        new_product_obj = Product(
            name=name,
            sku=sku,
            description=description,
            category=category,
            price=float(price),
            qty=int(qty) if qty else 0,
            min_stock=int(min_stock) if min_stock else 0,
            status=status
        )
        db.session.add(new_product_obj)
        db.session.commit()
        flash(f'Producto "{name}" creado exitosamente', 'success')
        return redirect(url_for('products_ui'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear el producto: {str(e)}', 'error')
        return redirect(url_for('new_product'))

@app.route("/products/<int:product_id>", methods=['PUT', 'POST'])
@login_required
def update_product(product_id):
    product = Product.query.get(product_id)
    if not product:
        flash('Producto no encontrado', 'error')
        return redirect(url_for('products_ui'))

    name = request.form.get('name')
    sku = request.form.get('sku')
    price = request.form.get('price')
    description = request.form.get('description')
    category = request.form.get('category')
    qty = request.form.get('qty')
    min_stock = request.form.get('min_stock')
    status = request.form.get('status')

    if not name or not sku or not price:
        flash('Los campos nombre, SKU y precio son obligatorios', 'error')
        return redirect(url_for('edit_product', product_id=product_id))

    # Check if SKU is being changed and if the new SKU already exists
    if sku != product.sku:
        existing = Product.query.filter_by(sku=sku).first()
        if existing:
            flash('Ya existe otro producto con este SKU', 'error')
            return redirect(url_for('edit_product', product_id=product_id))

    try:
        product.name = name
        product.sku = sku
        product.description = description
        product.category = category
        product.price = float(price)
        product.qty = int(qty) if qty else 0
        product.min_stock = int(min_stock) if min_stock else 0
        product.status = status

        db.session.commit()
        flash(f'Producto "{name}" actualizado exitosamente', 'success')
        return redirect(url_for('products_ui'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar el producto: {str(e)}', 'error')
        return redirect(url_for('edit_product', product_id=product_id))

@app.route("/products/<int:product_id>/delete", methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get(product_id)
    if not product:
        if request.headers.get('HX-Request'):
            return "", 404
        flash('Producto no encontrado', 'error')
        return redirect(url_for('products_ui'))

    try:
        product_name = product.name
        db.session.delete(product)
        db.session.commit()
        flash(f'Producto "{product_name}" eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el producto: {str(e)}', 'error')

    if request.headers.get('HX-Request'):
        # Return the updated table for HTMX
        page = request.args.get('page', 1, type=int)
        per_page = 10
        search = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'id')
        sort_order = request.args.get('sort_order', 'desc')

        query = Product.query.filter_by(status='active')
        if search:
            query = query.filter(or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%'),
                Product.category.ilike(f'%{search}%')
            ))
        
        if hasattr(Product, sort_by):
            column = getattr(Product, sort_by)
            if sort_order == 'desc':
                query = query.order_by(column.desc())
            else:
                query = query.order_by(column.asc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return render_template('products/partials/table.html', pagination=pagination, search=search, sort_by=sort_by, sort_order=sort_order)
    
    return redirect(url_for('products_ui'))

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
