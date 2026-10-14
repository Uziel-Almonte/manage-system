from flask import request, jsonify
from flask_smorest import Blueprint

from app.auth.middleware import require_scope
from app.auth.keycloak_admin import (
    MANAGEABLE_ROLES,
    KeycloakAdminError,
    create_user,
    fetch_user_access_token,
    get_user,
    get_user_realm_roles,
    list_users,
    set_user_roles,
    user_summary,
)

users_bp = Blueprint('users', 'users', url_prefix='/api/users', description='User administration via Keycloak')


def _error_response(exc: KeycloakAdminError):
    """
    Qué hace: convierte un error de Keycloak en una respuesta JSON estándar para la API.
    Por qué lo hace: para unificar la forma en que la API devuelve fallos de autenticación o administración.
    Cómo lo hace: toma la excepción, extrae su mensaje y código de estado, y retorna un objeto JSON con Flask.
    De dónde viene: la excepción viene de los helpers de Keycloak ejecutados por cualquier vista de usuarios.
    A dónde va: la respuesta sale por la API hacia el cliente que hizo la petición.
    Librerías externas: usa Flask para construir la respuesta JSON.
    """
    return jsonify({'message': exc.message}), exc.status_code


@users_bp.route('', methods=['GET'])
@require_scope('user:manage')
def api_list_users():
    """
    Qué hace: lista usuarios del realm con sus roles administrables.
    Por qué lo hace: para que la interfaz o clientes API puedan ver y gestionar usuarios.
    Cómo lo hace: lee un parámetro de búsqueda opcional, consulta Keycloak y transforma cada usuario a un resumen controlado.
    De dónde viene: la petición llega desde la ruta `/api/users` con método GET.
    A dónde va: devuelve un JSON con `data` y `manageable_roles`.
    Librerías externas: usa Flask-Smorest para el blueprint y los helpers de Keycloak para obtener usuarios y roles.
    """
    search = request.args.get('search') or None
    try:
        users = list_users(search=search)
        data = []
        for u in users:
            roles = [
                r['name']
                for r in get_user_realm_roles(u['id'])
                if r.get('name') in MANAGEABLE_ROLES
            ]
            data.append(user_summary(u, roles))
        return jsonify({'data': data, 'manageable_roles': MANAGEABLE_ROLES}), 200
    except KeycloakAdminError as e:
        return _error_response(e)


@users_bp.route('', methods=['POST'])
@require_scope('user:manage')
def api_create_user():
    """
    Qué hace: crea un usuario en Keycloak y devuelve un payload con resumen y token.
    Por qué lo hace: para permitir el registro de cuentas desde la API.
    Cómo lo hace: extrae el body JSON, valida datos básicos, delega la creación al helper de Keycloak y luego solicita un token.
    De dónde viene: la petición llega desde un cliente externo que envía JSON por `POST /api/users`.
    A dónde va: responde con el usuario creado y su token, o un error si falló la operación.
    Librerías externas: usa Flask para leer el body y los helpers de Keycloak para crear el usuario y emitir JWT.
    """
    body = request.get_json(silent=True) or {}
    username = (body.get('username') or '').strip()
    email = (body.get('email') or '').strip()
    first_name = (body.get('firstName') or body.get('first_name') or '').strip()
    last_name = (body.get('lastName') or body.get('last_name') or '').strip()
    password = body.get('password') or ''
    roles = body.get('roles') or []

    if not username or not password:
        return jsonify({'message': 'username and password are required'}), 400

    try:
        user = create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password,
            enabled=bool(body.get('enabled', True)),
            roles=roles,
        )
        role_names = [
            r['name']
            for r in get_user_realm_roles(user['id'])
            if r.get('name') in MANAGEABLE_ROLES
        ]
        payload = {
            'user': user_summary(user, role_names),
            'token': fetch_user_access_token(username, password),
        }
        return jsonify(payload), 201
    except KeycloakAdminError as e:
        return _error_response(e)


@users_bp.route('/<user_id>', methods=['GET'])
@require_scope('user:manage')
def api_get_user(user_id):
    """
    Qué hace: devuelve la información detallada de un usuario.
    Por qué lo hace: para consultar datos y permisos de un usuario concreto.
    Cómo lo hace: obtiene el usuario desde Keycloak y le añade los roles administrables que aplica la app.
    De dónde viene: la petición viene de la ruta `/api/users/<user_id>`.
    A dónde va: responde con el resumen del usuario en formato JSON.
    Librerías externas: usa Flask y los helpers de Keycloak para recuperar la información.
    """
    try:
        user = get_user(user_id)
        roles = [
            r['name']
            for r in get_user_realm_roles(user_id)
            if r.get('name') in MANAGEABLE_ROLES
        ]
        return jsonify(user_summary(user, roles)), 200
    except KeycloakAdminError as e:
        return _error_response(e)


@users_bp.route('/<user_id>/roles', methods=['PUT'])
@require_scope('user:manage')
def api_set_roles(user_id):
    """
    Qué hace: actualiza los roles asignados a un usuario.
    Por qué lo hace: para modificar permisos desde la API.
    Cómo lo hace: valida que el body tenga una lista de roles y delega la actualización al helper de Keycloak.
    De dónde viene: la llamada llega desde un cliente que envía JSON por `PUT /api/users/<user_id>/roles`.
    A dónde va: responde con el usuario actualizado y sus roles finales.
    Librerías externas: usa Flask para leer el JSON y los helpers de Keycloak para aplicar los cambios.
    """
    body = request.get_json(silent=True) or {}
    roles = body.get('roles')
    if not isinstance(roles, list):
        return jsonify({'message': 'roles must be a list'}), 400
    try:
        updated = set_user_roles(user_id, roles)
        user = get_user(user_id)
        return jsonify(user_summary(user, updated)), 200
    except KeycloakAdminError as e:
        return _error_response(e)


@users_bp.route('/<user_id>/token', methods=['POST'])
@require_scope('user:manage')
def api_issue_token(user_id):
    """
    Qué hace: emite un token JWT para un usuario con una contraseña válida.
    Por qué lo hace: para permitir que la UI o un cliente verifiquen la autenticación del usuario.
    Cómo lo hace: valida la contraseña, obtiene el usuario desde Keycloak y solicita un access token al helper correspondiente.
    De dónde viene: la petición llega desde `POST /api/users/<user_id>/token` con un body JSON.
    A dónde va: responde con el usuario y el token emitido.
    Librerías externas: usa Flask para recibir el body y los helpers de Keycloak para solicitar el JWT.
    """
    body = request.get_json(silent=True) or {}
    password = body.get('password') or ''
    if not password:
        return jsonify({'message': 'password is required to issue a JWT'}), 400
    try:
        user = get_user(user_id)
        username = user.get('username')
        if not username:
            return jsonify({'message': 'User has no username'}), 400
        token = fetch_user_access_token(username, password)
        return jsonify({'user': user_summary(user), 'token': token}), 200
    except KeycloakAdminError as e:
        return _error_response(e)
