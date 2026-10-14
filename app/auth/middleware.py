import os
import json
import urllib.request
from flask import g
from functools import wraps
from flask import request, jsonify, current_app, session, redirect, url_for
import jwt
from jwt.algorithms import RSAAlgorithm
from app.telemetry import record_invalid_token

_public_keys = None

def get_keycloak_public_keys():
    """
    Qué hace: descarga y construye el conjunto de claves públicas de Keycloak.
    Por qué lo hace: para verificar JWT firmados por Keycloak sin depender de claves hardcodeadas.
    Cómo lo hace: resuelve la URL JWKS y transforma cada JWK en una clave RSA utilizable por PyJWT.
    De dónde viene: la URL se toma de `KEYCLOAK_JWKS_URL` o, como respaldo, de `KEYCLOAK_REALM_URL`.
    A dónde va: devuelve un diccionario indexado por `kid` para que `require_jwt` pueda validar tokens.
    Librerías externas: `urllib.request` obtiene el JWKS, `json` lo parsea y `PyJWT` reconstruye las claves.
    """
    # Prefer KEYCLOAK_JWKS_URL so browser-facing KEYCLOAK_REALM_URL can stay on
    # localhost while containers reach Keycloak via Docker DNS.
    certs_url = os.environ.get('KEYCLOAK_JWKS_URL')
    if not certs_url:
        realm_url = os.environ.get('KEYCLOAK_REALM_URL')
        if not realm_url:
            raise ValueError("KEYCLOAK_JWKS_URL or KEYCLOAK_REALM_URL must be set")
        certs_url = f"{realm_url}/protocol/openid-connect/certs"
    try:
        with urllib.request.urlopen(certs_url) as response:
            jwks = json.loads(response.read().decode())
    except Exception as e:
        current_app.logger.error(f"Failed to fetch JWKS from {certs_url}: {e}")
        return {}

    public_keys = {}
    for jwk in jwks.get('keys', []):
        kid = jwk.get('kid')
        # Use PyJWT's built-in capability to recreate the RSA public key from the JWKS JSON
        public_keys[kid] = RSAAlgorithm.from_jwk(json.dumps(jwk))
    return public_keys

def require_jwt(f):
    """
    Qué hace: protege una vista exigiendo un JWT Bearer válido.
    Por qué lo hace: para asegurar que las rutas de API solo respondan a solicitudes autenticadas.
    Cómo lo hace: lee el header Authorization, obtiene la clave pública por `kid` y decodifica el token.
    De dónde viene: el token llega en el encabezado HTTP de la solicitud entrante.
    A dónde va: las claims decodificadas se guardan en `request.user_claims` para el resto del flujo.
    Librerías externas: Flask expone `request` y `current_app`, PyJWT verifica la firma y la expiración.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        global _public_keys

        # Bypass for unit tests
        if current_app.config.get('TESTING'):
            request.user_claims = {
                "realm_access": {
                    "roles": ["product:view", "product:manage", "stock:view", "stock:manage", "report:view", "audit:view", "user:manage"]
                }
            }
            return f(*args, **kwargs)
        
        auth_header = request.headers.get("Authorization", None)
        if not auth_header or not auth_header.startswith("Bearer "):
            record_invalid_token()
            return jsonify({"message": "Missing or invalid authorization header"}), 401

        token = auth_header.split(" ")[1]

        try:
            if _public_keys is None:
                _public_keys = get_keycloak_public_keys()
            
            # Extract the unverified header to get the kid
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')
            
            if not kid or kid not in _public_keys:
                record_invalid_token()
                return jsonify({"message": "Invalid token header or key not found"}), 401

            public_key = _public_keys[kid]

            # Decode the payload securely
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False}
            )
            
            # Attach the decoded payload to the request context
            request.user_claims = payload
            
        except jwt.ExpiredSignatureError:
            record_invalid_token()
            return jsonify({"message": "Token has expired"}), 401
        except jwt.InvalidTokenError as e:
            record_invalid_token()
            return jsonify({"message": f"Invalid token: {str(e)}"}), 401
        except Exception as e:
            current_app.logger.error(f"JWT Verification failed: {e}")
            return jsonify({"message": "Authorization failed"}), 500

        return f(*args, **kwargs)
    return decorated

def require_scope(required_scope):
    """
    Qué hace: envuelve una vista para exigir un permiso específico en el JWT.
    Por qué lo hace: para separar la autenticación general de la autorización por capacidad.
    Cómo lo hace: reutiliza `require_jwt`, lee las roles del realm y compara contra `required_scope`.
    De dónde viene: `required_scope` se pasa al decorar rutas que necesitan un permiso concreto.
    A dónde va: si el permiso existe continúa la petición; si no, responde con 403.
    Librerías externas: depende de Flask para construir la respuesta JSON y de `require_jwt` para validar el token.
    """
    def decorator(f):
        @wraps(f)
        @require_jwt
        def decorated_function(*args, **kwargs):
            claims = getattr(request, 'user_claims', {})
            roles = claims.get('realm_access', {}).get('roles', [])
            if required_scope not in roles:
                return jsonify({"message": f"Missing required scope: {required_scope}"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def login_required(f):
    """
    Qué hace: protege vistas web que requieren una sesión Flask válida.
    Por qué lo hace: para evitar que usuarios anónimos entren a pantallas internas del sistema.
    Cómo lo hace: verifica si existe `user` en la sesión y, si no, redirige a la página de login.
    De dónde viene: el estado de autenticación vive en la sesión creada durante el callback OAuth.
    A dónde va: cuando la sesión es válida, expone el usuario en `g.user` y continúa con la vista.
    Librerías externas: Flask aporta `session`, `g`, `redirect` y `url_for`.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Bypass for unit tests
        if current_app.config.get('TESTING'):
            return f(*args, **kwargs)
        print(session.get('user'))
        # Check if user is in session
        if 'user' not in session:
            return redirect(url_for('auth.login_page'))
        
        user_data = session.get('user', {})
        g.user = user_data.get('preferred_username') or user_data.get('email') or 'unknown'
        
        return f(*args, **kwargs)
    return decorated_function


def require_ui_scope(required_scope):
    """
    Qué hace: protege rutas de la interfaz según permisos guardados en la sesión.
    Por qué lo hace: para controlar acciones sensibles desde la UI con una respuesta amigable.
    Cómo lo hace: lee `user_scopes` desde la sesión y compara el permiso requerido antes de continuar.
    De dónde viene: los scopes se almacenan en sesión durante el callback de autenticación.
    A dónde va: si falta el permiso, muestra un flash y redirige al inicio; si no, deja seguir la vista.
    Librerías externas: Flask aporta `flash`, `redirect` y `url_for` para la navegación de UI.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_app.config.get('TESTING'):
                return f(*args, **kwargs)

            user_scopes = session.get('user_scopes', [])
            if required_scope not in user_scopes:
                from flask import flash, abort
                flash(f'Acceso denegado: se requiere el permiso "{required_scope}".', 'error')
                return redirect(url_for('index')), 303
            return f(*args, **kwargs)
        return decorated_function
    return decorator
