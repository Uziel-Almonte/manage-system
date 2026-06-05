import os
from flask import redirect, url_for, session, current_app, jsonify, request, render_template
from flask_smorest import Blueprint
from authlib.integrations.flask_client import OAuth

auth_bp = Blueprint('auth', 'auth', url_prefix='/auth', description="Authentication routes")

oauth = OAuth()

def init_oauth(app):
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
    """Render the login page"""
    return render_template('login.html')

@auth_bp.route('/login')
def login():
    redirect_uri = url_for('auth.callback', _external=True)
    return oauth.keycloak.authorize_redirect(redirect_uri)

@auth_bp.route('/callback')
def callback():
    try:
        token = oauth.keycloak.authorize_access_token()
    except Exception as e:
        current_app.logger.error(f"OAuth callback error: {e}")
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
    session.clear()
    # The external url where Keycloak should redirect the user after terminating Keycloak session
    redirect_uri = url_for('index', _external=True)
    
    # We must construct the logout URL using the external Keycloak URL, not the internal Docker one
    # so the user's browser can actually reach it.
    logout_url = f"http://localhost:8080/realms/inventory-realm/protocol/openid-connect/logout?client_id={os.getenv('KEYCLOAK_CLIENT_ID', 'flask-backend')}&post_logout_redirect_uri={redirect_uri}"
    return redirect(logout_url)
