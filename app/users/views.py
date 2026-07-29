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
    return jsonify({'message': exc.message}), exc.status_code


@users_bp.route('', methods=['GET'])
@require_scope('user:manage')
def api_list_users():
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
