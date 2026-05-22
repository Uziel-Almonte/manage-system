import os
from flask import redirect, url_for, session, current_app, jsonify, request
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
            'scope': 'openid profile email'
        }
    )

@auth_bp.route('/login')
def login():
    redirect_uri = url_for('auth.callback', _external=True)
    return oauth.keycloak.authorize_redirect(redirect_uri)

@auth_bp.route('/callback')
def callback():
    token = oauth.keycloak.authorize_access_token()
    # Authlib automatically parses the id_token if 'openid' is in scope
    user_info = token.get('userinfo') 
    
    # Store token and user data in the secure flask session
    session['user'] = user_info
    session['token'] = token
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
