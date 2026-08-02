import os
from urllib.parse import quote
from flask import redirect, url_for, session, current_app, jsonify, request, render_template
from flask_smorest import Blueprint
from authlib.integrations.flask_client import OAuth
from app.telemetry import record_auth_failure

auth_bp = Blueprint('auth', 'auth', url_prefix='/auth', description="Authentication routes")

oauth = OAuth()

def init_oauth(app):
    """
    Qué hace: configura el cliente OAuth de Keycloak para la aplicación Flask.
    Por qué lo hace: para centralizar la autenticación externa y reutilizar la misma configuración en toda la app.
    Cómo lo hace: inicializa `oauth` y registra el proveedor con URLs, credenciales y scopes esperados.
    De dónde viene: la configuración se toma de variables de entorno con valores por defecto para desarrollo local.
    A dónde va: deja listo `oauth.keycloak` para las rutas de login, callback y logout.
    Librerías externas: `Authlib` gestiona el cliente OAuth y Flask recibe la app que se va a configurar.
    """
    oauth.init_app(app)
    
    oauth.register(
        name='keycloak',
        client_id=os.getenv('KEYCLOAK_CLIENT_ID', 'flask-app'),
        client_secret=os.getenv('KEYCLOAK_CLIENT_SECRET', ''),
        # The URL the user's browser is redirected to (must be accessible from the outside)
        authorize_url=os.getenv('KEYCLOAK_AUTHORIZE_URL', "http://localhost:8080/realms/inventory-realm/protocol/openid-connect/auth"),
        # The internal URLs the Flask backend uses to communicate with Keycloak
        access_token_url=os.getenv('KEYCLOAK_TOKEN_URL', "http://keycloak_auth:8080/realms/inventory-realm/protocol/openid-connect/token"),
        userinfo_endpoint=os.getenv('KEYCLOAK_USERINFO_URL', "http://keycloak_auth:8080/realms/inventory-realm/protocol/openid-connect/userinfo"),
        jwks_uri=os.getenv('KEYCLOAK_JWKS_URL', "http://keycloak_auth:8080/realms/inventory-realm/protocol/openid-connect/certs"),
        client_kwargs={
            'scope': 'openid profile email',
            # Specify the expected issuer explicitly to handle localhost vs keycloak_auth mismatch
            'issuer': os.getenv('KEYCLOAK_ISSUER', 'http://localhost:8080/realms/inventory-realm'),
        }
    )

@auth_bp.route('/login-page')
def login_page():
    """
    Qué hace: renderiza la pantalla de inicio de sesión.
    Por qué lo hace: para ofrecer una vista simple desde la cual el usuario puede iniciar el flujo OAuth.
    Cómo lo hace: devuelve la plantilla `login.html` sin lógica adicional.
    De dónde viene: la navegación entra por la ruta `/auth/login-page`.
    A dónde va: la respuesta HTML se entrega al navegador del usuario.
    Librerías externas: Flask renderiza la plantilla con `render_template`.
    """
    return render_template('login.html')

@auth_bp.route('/login')
def login():
    """
    Qué hace: inicia el flujo de autenticación con Keycloak.
    Por qué lo hace: para redirigir al usuario al proveedor de identidad antes de volver a la aplicación.
    Cómo lo hace: construye la URL de callback y usa `authorize_redirect` de Authlib.
    De dónde viene: la petición llega desde la ruta `/auth/login`.
    A dónde va: el navegador termina en la pantalla de login de Keycloak.
    Librerías externas: Flask genera la URL de callback y Authlib maneja la redirección OAuth.
    """
    redirect_uri = url_for('auth.callback', _external=True)
    return oauth.keycloak.authorize_redirect(redirect_uri)

@auth_bp.route('/callback')
def callback():
    """
    Qué hace: procesa la respuesta que Keycloak devuelve después del login.
    Por qué lo hace: para intercambiar el código por tokens y guardar la sesión del usuario.
    Cómo lo hace: obtiene el token, extrae `userinfo`, decodifica permisos y guarda todo en `session`.
    De dónde viene: Keycloak redirige aquí tras completar la autenticación OAuth.
    A dónde va: una sesión válida queda persistida y el usuario vuelve a la página principal.
    Librerías externas: Authlib realiza el intercambio de tokens, PyJWT decodifica el access token y Flask maneja la sesión.
    """
    try:
        token = oauth.keycloak.authorize_access_token()
    except Exception as e:
        current_app.logger.error(f"OAuth callback error: {e}")
        record_auth_failure(request.remote_addr)
        return jsonify({"error": str(e)}), 500
    
    # Authlib automatically parses the id_token if 'openid' is in scope
    user_info = token.get('userinfo') 
    
    # Extract permissions from the access token.
    # Keycloak puts custom realm roles (product:view, audit:view, etc.) in
    # realm_access.roles — NOT in the OAuth2 "scope" string which only ever
    # contains the standard OpenID scopes (openid, profile, email).
    access_token = token.get('access_token', '')
    user_scopes = []
    if access_token:
        try:
            import jwt as pyjwt
            unverified = pyjwt.decode(access_token, options={"verify_signature": False})
            realm_roles = unverified.get('realm_access', {}).get('roles', [])
            # Keep only the application-level permission roles (those containing ':')
            user_scopes = [r for r in realm_roles if ':' in r]
        except Exception:
            user_scopes = []

    # Store token and user data in the secure flask session
    session['user'] = user_info
    session['token'] = token
    session['user_scopes'] = user_scopes
    # Redirect to home page instead of returning JSON so refreshing doesn't cause CSRF errors
    return redirect('/')

@auth_bp.route('/logout')
def logout():
    """
    Qué hace: cierra la sesión local y prepara el cierre de sesión en Keycloak.
    Por qué lo hace: para sacar al usuario de la aplicación y evitar sesiones colgadas.
    Cómo lo hace: limpia la sesión de Flask, construye la URL de logout del proveedor y redirige allí.
    De dónde viene: la acción se dispara desde la ruta `/auth/logout`.
    A dónde va: el navegador termina en el endpoint de logout de Keycloak con retorno a la aplicación.
    Librerías externas: Flask limpia la sesión y `urllib.parse.quote` codifica la URL de retorno.
    """
    session.clear()
    # The external url where Keycloak should redirect the user after terminating Keycloak session
    redirect_uri = url_for('index', _external=True)

    # External Keycloak logout URL (override with KEYCLOAK_LOGOUT_BASE when running
    # behind a tunnel/proxy so this doesn't hardcode localhost).
    logout_base = os.getenv(
        'KEYCLOAK_LOGOUT_BASE',
        'http://localhost:8080/realms/inventory-realm/protocol/openid-connect/logout',
    )
    client_id = os.getenv('KEYCLOAK_CLIENT_ID', 'flask-backend')
    logout_url = (
        f"{logout_base}?client_id={client_id}"
        f"&post_logout_redirect_uri={quote(redirect_uri, safe='')}"
    )
    return redirect(logout_url)
