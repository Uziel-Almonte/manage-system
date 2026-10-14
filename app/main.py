from flask import Flask, render_template, request, flash, redirect, url_for
from sqlalchemy import text, or_
from dotenv import load_dotenv
import os
from werkzeug.middleware.proxy_fix import ProxyFix
from app.database import db
from app.stock.views import stock_bp
from app.reports.views import reports_bp
from app.products.views import products_bp
from app.auth.views import auth_bp
from app.auth.middleware import require_jwt, login_required, require_ui_scope
from app.audit.views import audit_bp
from app.users.views import users_bp
from app.audit.listeners import register_audit_listeners
from flask_migrate import Migrate
from flask_smorest import Api
from app.telemetry import record_product_created, sync_active_products_total, record_stock_movement
from app.stock.services import register_qty_change_movement


from flask_cors import CORS

load_dotenv()

app = Flask(__name__, template_folder='templates')
# Trust reverse-proxy headers (e.g. Cloudflare Tunnel) so url_for(_external=True)
# produces the correct public scheme/host instead of the internal one.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
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

from app.telemetry import init_metrics, init_telemetry
init_telemetry(app, db)
init_metrics(app)

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
api.register_blueprint(users_bp)

@app.route("/")
@login_required
def index():
    """
    Qué hace: construye el panel principal con métricas resumidas del inventario.
    Por qué lo hace: para que el usuario vea de inmediato el estado general del sistema.
    Cómo lo hace: consulta modelos de SQLAlchemy para contar productos y movimientos recientes.
    De dónde viene: la ejecución viene de la ruta raíz `/` cuando el usuario entra al panel.
    A dónde va: los datos se envían a la plantilla `index.html` con `render_template` de Flask.
    Librerías externas: Flask renderiza la vista y SQLAlchemy ejecuta las consultas ORM.
    """
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
    """
    Qué hace: muestra el listado paginado de productos con búsqueda y ordenamiento.
    Por qué lo hace: para navegar y filtrar productos sin salir de la interfaz web.
    Cómo lo hace: lee parámetros de la URL, arma una consulta ORM y pagina el resultado.
    De dónde viene: la vista se dispara desde la ruta `/products` y sus parámetros `page`, `search`, `sort_by` y `sort_order`.
    A dónde va: renderiza `products/index.html` o la tabla parcial de HTMX según la petición.
    Librerías externas: Flask procesa request/render_template, SQLAlchemy filtra y pagina, HTMX pide el parcial.
    """
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
@require_ui_scope('product:manage')
def new_product():
    """
    Qué hace: muestra el formulario para crear un producto nuevo.
    Por qué lo hace: para separar la captura de datos del guardado en base de datos.
    Cómo lo hace: devuelve la plantilla del formulario con un producto vacío.
    De dónde viene: la navegación llega desde `/products/new` protegida por el permiso `product:manage`.
    A dónde va: la vista `products/form.html` recibe `product=None`.
    Librerías externas: Flask renderiza la plantilla y los decoradores controlan acceso.
    """
    return render_template('products/form.html', product=None)

@app.route("/products/<int:product_id>/edit")
@login_required
@require_ui_scope('product:manage')
def edit_product(product_id):
    """
    Qué hace: carga el formulario de edición para un producto específico.
    Por qué lo hace: para permitir modificar un registro existente desde la UI.
    Cómo lo hace: busca el producto por ID y redirige si no existe.
    De dónde viene: la petición llega desde `/products/<product_id>/edit` con el identificador en la URL.
    A dónde va: la plantilla `products/form.html` recibe el objeto `product`.
    Librerías externas: Flask maneja la navegación, SQLAlchemy obtiene el registro.
    """
    product = Product.query.get(product_id)
    if not product:
        flash('Producto no encontrado', 'error')
        return redirect(url_for('products_ui'))
    return render_template('products/form.html', product=product)

@app.route("/products", methods=['POST'])
@login_required
@require_ui_scope('product:manage')
def create_product():
    """
    Qué hace: crea un producto nuevo a partir del formulario enviado.
    Por qué lo hace: para persistir en la base de datos la información capturada en la UI.
    Cómo lo hace: valida campos obligatorios, evita SKU duplicado, guarda con SQLAlchemy y actualiza métricas.
    De dónde viene: los datos vienen del formulario `products/form.html` enviado por `POST /products`.
    A dónde va: tras guardar, redirige a `products_ui`; si falla, vuelve al formulario.
    Librerías externas: Flask lee `request` y `flash`, SQLAlchemy persiste, las funciones de telemetría actualizan métricas.
    """
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
        record_product_created()
        sync_active_products_total()
        flash(f'Producto "{name}" creado exitosamente', 'success')
        return redirect(url_for('products_ui'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear el producto: {str(e)}', 'error')
        return redirect(url_for('new_product'))

@app.route("/products/<int:product_id>", methods=['PUT', 'POST'])
@login_required
@require_ui_scope('product:manage')
def update_product(product_id):
    """
    Qué hace: actualiza los datos de un producto existente.
    Por qué lo hace: para mantener sincronizada la ficha del producto con el formulario editado.
    Cómo lo hace: carga el registro, valida SKU, aplica cambios y registra movimientos de inventario si cambia la cantidad.
    De dónde viene: la actualización llega desde `/products/<product_id>` mediante `PUT` o `POST`.
    A dónde va: vuelve al listado o al formulario de edición según el resultado de este.
    Librerías externas: Flask procesa la petición, SQLAlchemy guarda cambios y la capa de telemetría registra eventos.
    """
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

    previous_qty = product.qty

    try:
        qty_value = int(qty) if qty else None
        product.name = name
        product.sku = sku
        product.description = description
        product.category = category
        product.price = float(price)
        if qty_value is not None:
            product.qty = qty_value
        if min_stock:
            product.min_stock = int(min_stock)
        product.status = status

        if qty_value is not None and qty_value != previous_qty:
            register_qty_change_movement(product, previous_qty, qty_value, user='system')

        db.session.commit()
        if qty_value is not None and qty_value != previous_qty:
            record_stock_movement('entry' if qty_value > previous_qty else 'exit', product.sku)
        sync_active_products_total()
        flash(f'Producto "{name}" actualizado exitosamente', 'success')
        return redirect(url_for('products_ui'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar el producto: {str(e)}', 'error')
        return redirect(url_for('edit_product', product_id=product_id))

@app.route("/products/<int:product_id>/delete", methods=['POST'])
@login_required
@require_ui_scope('product:manage')
def delete_product(product_id):
    """
    Qué hace: elimina un producto del sistema.
    Por qué lo hace: para retirar registros que ya no deben aparecer en el inventario activo.
    Cómo lo hace: localiza el producto, lo borra con SQLAlchemy y recompone la tabla si la petición viene de HTMX.
    De dónde viene: la acción se dispara desde `/products/<product_id>/delete` con `POST`.
    A dónde va: redirige al listado o devuelve el parcial actualizado para la interfaz dinámica.
    Librerías externas: Flask controla la respuesta, SQLAlchemy ejecuta el borrado y HTMX consume el parcial.
    """
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
        sync_active_products_total()
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
    """
    Qué hace: muestra el historial de movimientos de stock con filtros.
    Por qué lo hace: para auditar entradas y salidas del inventario desde la web.
    Cómo lo hace: lee filtros de la URL, consulta movimientos y pagina el resultado.
    De dónde viene: la consulta viene de la ruta `/stock` y de los filtros enviados por query string.
    A dónde va: renderiza `stock/history.html` o el parcial `stock/partials/history_table.html`.
    Librerías externas: Flask lee la request, SQLAlchemy filtra y pagina, HTMX solicita el fragmento parcial.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 20
    movement_type = request.args.get('type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    product_id = request.args.get('product_id', type=int)

    query = StockMovement.query

    if movement_type:
        query = query.filter_by(type=movement_type)
    if product_id:
        query = query.filter_by(product_id=product_id)
    if date_from:
        try:
            from datetime import datetime as dt
            query = query.filter(StockMovement.date >= dt.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime as dt
            query = query.filter(StockMovement.date <= dt.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            pass

    pagination = query.order_by(StockMovement.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    products = Product.query.filter_by(status='active').order_by(Product.name).all()

    if request.headers.get('HX-Request'):
        return render_template('stock/partials/history_table.html',
                               pagination=pagination,
                               movement_type=movement_type,
                               date_from=date_from,
                               date_to=date_to,
                               product_id=product_id)

    return render_template('stock/history.html',
                           pagination=pagination,
                           products=products,
                           movement_type=movement_type,
                           date_from=date_from,
                           date_to=date_to,
                           product_id=product_id)

@app.route("/stock/update", methods=['GET', 'POST'])
@login_required
@require_ui_scope('stock:manage')
def stock_update_ui():
    """
    Qué hace: permite registrar manualmente una entrada o salida de inventario.
    Por qué lo hace: para ajustar stock cuando ocurre un movimiento operativo real.
    Cómo lo hace: valida datos del formulario, modifica la cantidad, crea un movimiento y confirma con commit.
    De dónde viene: el flujo viene de `/stock/update`, ya sea para mostrar el formulario o procesar un `POST`.
    A dónde va: devuelve el formulario, redirige al historial o entrega el parcial de información del producto.
    Librerías externas: Flask gestiona request/flash/redirect/render_template y SQLAlchemy guarda el movimiento.
    """
    products = Product.query.filter_by(status='active').order_by(Product.name).all()

    if request.method == 'POST':
        from flask import flash, redirect, url_for
        product_id = request.form.get('product_id', type=int)
        movement_type = request.form.get('type')
        qty_change = request.form.get('qty_change', type=int)
        notes = request.form.get('notes', '')
        user = request.form.get('user', 'system')

        product = Product.query.get(product_id) if product_id else None
        if not product:
            from flask import flash
            flash('Producto no encontrado.', 'error')
            return render_template('stock/update.html', products=products)

        if not movement_type or movement_type not in ('entry', 'exit'):
            from flask import flash
            flash('Tipo de movimiento inválido. Debe ser entrada o salida.', 'error')
            return render_template('stock/update.html', products=products)

        if not qty_change or qty_change <= 0:
            from flask import flash
            flash('La cantidad debe ser un número positivo.', 'error')
            return render_template('stock/update.html', products=products)

        if movement_type == 'exit' and product.qty < qty_change:
            from flask import flash
            flash(f'Stock insuficiente. Stock actual: {product.qty}', 'error')
            return render_template('stock/update.html', products=products, selected_product=product)

        prev_qty = product.qty
        if movement_type == 'exit':
            product.qty -= qty_change
        else:
            product.qty += qty_change

        movement = StockMovement(
            product_id=product.id,
            user=user,
            type=movement_type,
            prev_qty=prev_qty,
            new_qty=product.qty,
            notes=notes
        )
        db.session.add(movement)
        db.session.commit()

        from flask import flash, redirect
        flash(f'Movimiento registrado correctamente. Nuevo stock de {product.name}: {product.qty}', 'success')
        record_stock_movement(movement_type, product.sku)
        return redirect('/stock')

    selected_product_id = request.args.get('product_id', type=int)
    selected_product = Product.query.get(selected_product_id) if selected_product_id else None

    if request.headers.get('HX-Request') and selected_product_id:
        return render_template('stock/partials/product_info.html', selected_product=selected_product)

    return render_template('stock/update.html', products=products, selected_product=selected_product)

@app.route("/reports")
@login_required
@require_ui_scope('report:view')
def reports_ui():
    """
    Qué hace: construye la pantalla de reportes de inventario.
    Por qué lo hace: para ofrecer una vista ejecutiva del estado del catálogo y los movimientos.
    Cómo lo hace: consulta productos críticos, top productos y movimientos recientes con SQLAlchemy.
    De dónde viene: la navegación proviene de la ruta `/reports` protegida por `report:view`.
    A dónde va: envía los datos a `reports/index.html`.
    Librerías externas: Flask renderiza la plantilla y SQLAlchemy resuelve las consultas ORM.
    """
    critical_products = Product.query.filter(
        Product.qty <= Product.min_stock,
        Product.status == 'active'
    ).order_by(Product.qty.asc()).all()

    top_products = Product.query.filter_by(status='active').order_by(Product.qty.desc()).limit(10).all()

    recent_movements = StockMovement.query.order_by(StockMovement.date.desc()).limit(20).all()

    return render_template('reports/index.html',
                           critical_products=critical_products,
                           top_products=top_products,
                           recent_movements=recent_movements)

@app.route("/audit")
@login_required
@require_ui_scope('audit:view')
def audit_ui():
    """
    Qué hace: muestra el historial de auditoría del sistema.
    Por qué lo hace: para revisar qué cambios ocurrieron y sobre qué registros.
    Cómo lo hace: consulta `AuditLog` con filtros opcionales y pagina por fecha descendente.
    De dónde viene: la pantalla se solicita desde `/audit` con filtros opcionales por query string.
    A dónde va: renderiza `audit/index.html` o el parcial `audit/partials/audit_table.html`.
    Librerías externas: Flask maneja la petición y SQLAlchemy obtiene el histórico.
    """
    from app.audit.models import AuditLog

    page = request.args.get('page', 1, type=int)
    per_page = 25
    filter_table = request.args.get('table', '')
    filter_action = request.args.get('action', '')
    filter_record_id = request.args.get('record_id', None, type=int)

    query = AuditLog.query
    if filter_table:
        query = query.filter_by(table_name=filter_table)
    if filter_action:
        query = query.filter_by(action=filter_action)
    if filter_record_id:
        query = query.filter_by(record_id=filter_record_id)

    total = query.count()
    pagination = query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)

    if request.headers.get('HX-Request'):
        return render_template('audit/partials/audit_table.html',
                               pagination=pagination,
                               filter_table=filter_table,
                               filter_action=filter_action,
                               filter_record_id=filter_record_id)

    return render_template('audit/index.html',
                           pagination=pagination,
                           total=total,
                           filter_table=filter_table,
                           filter_action=filter_action,
                           filter_record_id=filter_record_id)


@app.route("/users")
@login_required
@require_ui_scope('user:manage')
def users_ui():
    """
    Qué hace: lista usuarios administrables desde Keycloak.
    Por qué lo hace: para permitir gestión de cuentas y roles desde la interfaz.
    Cómo lo hace: llama utilidades de Keycloak, filtra roles gestionables y prepara un resumen por usuario.
    De dónde viene: la vista se origina en la ruta `/users` con permiso `user:manage`.
    A dónde va: renderiza `users/index.html` con la lista y sin token emitido.
    Librerías externas: las operaciones reales de usuarios las hace Keycloak mediante el cliente auxiliar del proyecto.
    """
    from app.auth.keycloak_admin import (
        MANAGEABLE_ROLES,
        KeycloakAdminError,
        get_user_realm_roles,
        list_users,
        user_summary,
    )

    try:
        raw_users = list_users(max_results=100)
        users = []
        for u in raw_users:
            roles = [
                r['name']
                for r in get_user_realm_roles(u['id'])
                if r.get('name') in MANAGEABLE_ROLES
            ]
            users.append(user_summary(u, roles))
    except KeycloakAdminError as e:
        flash(f'Error al listar usuarios: {e.message}', 'error')
        users = []

    return render_template(
        'users/index.html',
        users=users,
        issued_token=None,
        issued_username=None,
    )


@app.route("/users/new")
@login_required
@require_ui_scope('user:manage')
def users_new_ui():
    """
    Qué hace: muestra el formulario para crear un usuario en Keycloak.
    Por qué lo hace: para capturar datos y roles antes de llamar al administrador externo.
    Cómo lo hace: carga la lista de roles administrables y la pasa a la plantilla.
    De dónde viene: la navegación entra desde `/users/new`.
    A dónde va: renderiza `users/form.html`.
    Librerías externas: Keycloak define los roles disponibles y Flask renderiza la vista.
    """
    from app.auth.keycloak_admin import MANAGEABLE_ROLES
    return render_template('users/form.html', manageable_roles=MANAGEABLE_ROLES)


@app.route("/users", methods=['POST'])
@login_required
@require_ui_scope('user:manage')
def users_create_ui():
    """
    Qué hace: crea un usuario en Keycloak y luego refresca el listado.
    Por qué lo hace: para registrar nuevas cuentas y devolver retroalimentación inmediata.
    Cómo lo hace: valida datos, llama al cliente de Keycloak, opcionalmente emite un token y reconstruye el listado.
    De dónde viene: el envío llega desde el formulario `users/form.html` por `POST /users`.
    A dónde va: termina en `users/index.html` o redirige al formulario si hay error.
    Librerías externas: Keycloak realiza la creación y emisión del token; Flask maneja formularios, flashes y renderizado.
    """
    from app.auth.keycloak_admin import (
        MANAGEABLE_ROLES,
        KeycloakAdminError,
        create_user,
        fetch_user_access_token,
        get_user_realm_roles,
        list_users,
        user_summary,
    )

    username = (request.form.get('username') or '').strip()
    email = (request.form.get('email') or '').strip()
    first_name = (request.form.get('firstName') or '').strip()
    last_name = (request.form.get('lastName') or '').strip()
    password = request.form.get('password') or ''
    roles = request.form.getlist('roles')

    if not username or not password:
        flash('Usuario y contraseña son obligatorios.', 'error')
        return redirect(url_for('users_new_ui'))

    try:
        create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
            roles=roles,
        )
        # Do not put JWTs in the session cookie (browser 4KB limit). Render them
        # on this response instead.
        issued_token = fetch_user_access_token(username, password)
        flash(f'Usuario "{username}" creado en Keycloak.', 'success')
    except KeycloakAdminError as e:
        flash(f'No se pudo crear el usuario: {e.message}', 'error')
        return redirect(url_for('users_new_ui'))
    except Exception as e:
        flash(f'Error inesperado al crear el usuario: {e}', 'error')
        return redirect(url_for('users_new_ui'))

    try:
        raw_users = list_users(max_results=100)
        users = []
        for u in raw_users:
            user_roles = [
                r['name']
                for r in get_user_realm_roles(u['id'])
                if r.get('name') in MANAGEABLE_ROLES
            ]
            users.append(user_summary(u, user_roles))
    except KeycloakAdminError:
        users = []

    return render_template(
        'users/index.html',
        users=users,
        issued_token=issued_token,
        issued_username=username,
    )


@app.route("/users/<user_id>")
@login_required
@require_ui_scope('user:manage')
def users_detail_ui(user_id):
    """
    Qué hace: muestra el detalle de un usuario de Keycloak.
    Por qué lo hace: para revisar información, roles y posibles acciones sobre la cuenta.
    Cómo lo hace: obtiene el usuario, extrae roles administrables y prepara el resumen para la vista.
    De dónde viene: la consulta proviene de la ruta `/users/<user_id>`.
    A dónde va: renderiza `users/detail.html`.
    Librerías externas: el acceso a usuarios y roles se resuelve mediante el cliente de Keycloak.
    """
    from app.auth.keycloak_admin import (
        MANAGEABLE_ROLES,
        KeycloakAdminError,
        get_user,
        get_user_realm_roles,
        user_summary,
    )

    try:
        user = get_user(user_id)
        roles = [
            r['name']
            for r in get_user_realm_roles(user_id)
            if r.get('name') in MANAGEABLE_ROLES
        ]
    except KeycloakAdminError as e:
        flash(f'Usuario no disponible: {e.message}', 'error')
        return redirect(url_for('users_ui'))

    return render_template(
        'users/detail.html',
        user=user_summary(user, roles),
        manageable_roles=MANAGEABLE_ROLES,
        issued_token=None,
    )


@app.route("/users/<user_id>/roles", methods=['POST'])
@login_required
@require_ui_scope('user:manage')
def users_roles_ui(user_id):
    """
    Qué hace: actualiza los roles asignados a un usuario en Keycloak.
    Por qué lo hace: para administrar permisos desde la interfaz interna.
    Cómo lo hace: lee el formulario y delega la actualización al helper de Keycloak.
    De dónde viene: la acción llega desde `/users/<user_id>/roles` con `POST`.
    A dónde va: vuelve al detalle del usuario.
    Librerías externas: Keycloak ejecuta el cambio real de roles; Flask solo controla la petición y la redirección.
    """
    from app.auth.keycloak_admin import KeycloakAdminError, set_user_roles

    roles = request.form.getlist('roles')
    try:
        set_user_roles(user_id, roles)
        flash('Permisos actualizados en Keycloak.', 'success')
    except KeycloakAdminError as e:
        flash(f'No se pudieron actualizar permisos: {e.message}', 'error')
    return redirect(url_for('users_detail_ui', user_id=user_id))


@app.route("/users/<user_id>/token", methods=['POST'])
@login_required
@require_ui_scope('user:manage')
def users_token_ui(user_id):
    """
    Qué hace: emite un JWT de un usuario para mostrarlo en la interfaz.
    Por qué lo hace: para facilitar pruebas y verificación de autenticación.
    Cómo lo hace: solicita la contraseña, obtiene el usuario, pide el token a Keycloak y re-renderiza el detalle.
    De dónde viene: el disparador es `/users/<user_id>/token` con una contraseña enviada por formulario.
    A dónde va: retorna `users/detail.html` con `issued_token` o redirige si hay error.
    Librerías externas: Keycloak firma y entrega el token; Flask muestra la respuesta y maneja errores.
    """
    from app.auth.keycloak_admin import (
        MANAGEABLE_ROLES,
        KeycloakAdminError,
        fetch_user_access_token,
        get_user,
        get_user_realm_roles,
        user_summary,
    )

    password = request.form.get('password') or ''
    if not password:
        flash('La contraseña es obligatoria para emitir el JWT.', 'error')
        return redirect(url_for('users_detail_ui', user_id=user_id))

    try:
        user = get_user(user_id)
        issued_token = fetch_user_access_token(user['username'], password)
        roles = [
            r['name']
            for r in get_user_realm_roles(user_id)
            if r.get('name') in MANAGEABLE_ROLES
        ]
        flash('JWT generado correctamente.', 'success')
        return render_template(
            'users/detail.html',
            user=user_summary(user, roles),
            manageable_roles=MANAGEABLE_ROLES,
            issued_token=issued_token,
        )
    except KeycloakAdminError as e:
        flash(f'No se pudo emitir JWT: {e.message}', 'error')
        return redirect(url_for('users_detail_ui', user_id=user_id))


@app.route("/health")
@require_jwt
def health():
    """
    Qué hace: expone un endpoint simple de salud de la aplicación.
    Por qué lo hace: para que sistemas externos verifiquen disponibilidad y conexión a base de datos.
    Cómo lo hace: ejecuta una consulta mínima con SQLAlchemy y devuelve estado HTTP según el resultado.
    De dónde viene: la llamada viene desde monitores, balanceadores o scripts que consultan `/health`.
    A dónde va: responde JSON directamente al cliente que hizo la verificación.
    Librerías externas: Flask construye la respuesta y SQLAlchemy ejecuta la consulta de prueba.
    """
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500
