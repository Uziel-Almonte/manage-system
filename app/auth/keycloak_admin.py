"""Keycloak Admin API helpers for user management."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
import jwt as pyjwt
import requests
from flask import current_app

MANAGEABLE_ROLES = [
    'group:employee',
    'group:manager',
    'product:view',
    'product:manage',
    'stock:view',
    'stock:manage',
    'report:view',
    'audit:view',
    'user:manage',
]


class KeycloakAdminError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _admin_base_url() -> str:
    return os.getenv(
        'KEYCLOAK_ADMIN_API_URL',
        os.getenv('KEYCLOAK_INTERNAL_URL', 'http://keycloak_auth:8080') + '/admin',
    ).rstrip('/')


def _realm() -> str:
    return os.getenv('KEYCLOAK_REALM', 'inventory-realm')


def _token_url() -> str:
    # Prefer dedicated admin token URL; fall back to realm token host's master realm.
    explicit = os.getenv('KEYCLOAK_ADMIN_TOKEN_URL')
    if explicit:
        return explicit
    realm_token = os.getenv(
        'KEYCLOAK_TOKEN_URL',
        'http://keycloak_auth:8080/realms/inventory-realm/protocol/openid-connect/token',
    )
    # .../realms/<realm>/protocol/... → .../realms/master/protocol/...
    if '/realms/' in realm_token:
        prefix, rest = realm_token.split('/realms/', 1)
        return f"{prefix}/realms/master/protocol/openid-connect/token"
    return 'http://keycloak_auth:8080/realms/master/protocol/openid-connect/token'


def _app_token_url() -> str:
    return os.getenv(
        'KEYCLOAK_TOKEN_URL',
        'http://keycloak_auth:8080/realms/inventory-realm/protocol/openid-connect/token',
    )


def get_admin_access_token() -> str:
    username = os.getenv('KEYCLOAK_USER') or os.getenv('KEYCLOAK_ADMIN', 'admin')
    password = os.getenv('KEYCLOAK_PASSWORD') or os.getenv('KEYCLOAK_ADMIN_PASSWORD', 'admin')
    client_id = os.getenv('KEYCLOAK_ADMIN_CLIENT_ID', 'admin-cli')

    try:
        res = requests.post(
            _token_url(),
            data={
                'grant_type': 'password',
                'client_id': client_id,
                'username': username,
                'password': password,
            },
            timeout=20,
        )
    except requests.RequestException as e:
        raise KeycloakAdminError(f'Failed to reach Keycloak admin token endpoint: {e}') from e

    if res.status_code != 200:
        raise KeycloakAdminError(
            f'Keycloak admin login failed ({res.status_code}): {res.text}',
            status_code=502,
        )
    token = res.json().get('access_token')
    if not token:
        raise KeycloakAdminError('Keycloak admin token response missing access_token', status_code=502)
    return token


def _headers() -> dict[str, str]:
    return {
        'Authorization': f'Bearer {get_admin_access_token()}',
        'Content-Type': 'application/json',
    }


def _realm_url(path: str = '') -> str:
    return f"{_admin_base_url()}/realms/{_realm()}{path}"


def list_users(search: str | None = None, max_results: int = 50) -> list[dict[str, Any]]:
    params: dict[str, Any] = {'max': max_results}
    if search:
        params['search'] = search
    res = requests.get(_realm_url('/users'), headers=_headers(), params=params, timeout=20)
    if res.status_code != 200:
        raise KeycloakAdminError(f'List users failed ({res.status_code}): {res.text}', status_code=502)
    return res.json()


def get_user(user_id: str) -> dict[str, Any]:
    res = requests.get(_realm_url(f'/users/{user_id}'), headers=_headers(), timeout=20)
    if res.status_code == 404:
        raise KeycloakAdminError('User not found', status_code=404)
    if res.status_code != 200:
        raise KeycloakAdminError(f'Get user failed ({res.status_code}): {res.text}', status_code=502)
    return res.json()


def find_user_id_by_username(username: str) -> str | None:
    res = requests.get(
        _realm_url('/users'),
        headers=_headers(),
        params={'username': username, 'exact': 'true'},
        timeout=20,
    )
    if res.status_code != 200:
        raise KeycloakAdminError(f'Lookup user failed ({res.status_code}): {res.text}', status_code=502)
    users = res.json()
    return users[0]['id'] if users else None


def create_user(
    *,
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    enabled: bool = True,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        'username': username,
        'email': email,
        'firstName': first_name,
        'lastName': last_name,
        'enabled': enabled,
        'emailVerified': True,
        'credentials': [
            {
                'type': 'password',
                'value': password,
                'temporary': False,
            }
        ],
    }
    res = requests.post(_realm_url('/users'), headers=_headers(), json=payload, timeout=20)
    if res.status_code == 409:
        raise KeycloakAdminError('User already exists', status_code=409)
    if res.status_code not in (201, 204):
        raise KeycloakAdminError(f'Create user failed ({res.status_code}): {res.text}', status_code=502)

    user_id = find_user_id_by_username(username)
    if not user_id:
        raise KeycloakAdminError('User created but could not be looked up', status_code=502)

    if roles:
        set_user_roles(user_id, roles)

    return get_user(user_id)


def get_realm_roles() -> list[dict[str, Any]]:
    res = requests.get(_realm_url('/roles'), headers=_headers(), timeout=20)
    if res.status_code != 200:
        raise KeycloakAdminError(f'List roles failed ({res.status_code}): {res.text}', status_code=502)
    return res.json()


def get_user_realm_roles(user_id: str) -> list[dict[str, Any]]:
    res = requests.get(
        _realm_url(f'/users/{user_id}/role-mappings/realm'),
        headers=_headers(),
        timeout=20,
    )
    if res.status_code == 404:
        raise KeycloakAdminError('User not found', status_code=404)
    if res.status_code != 200:
        raise KeycloakAdminError(f'Get user roles failed ({res.status_code}): {res.text}', status_code=502)
    return res.json()


def _role_reps(role_names: list[str]) -> list[dict[str, Any]]:
    wanted = set(role_names)
    all_roles = get_realm_roles()
    found = [r for r in all_roles if r.get('name') in wanted]
    missing = wanted - {r['name'] for r in found}
    if missing:
        raise KeycloakAdminError(f'Unknown roles: {", ".join(sorted(missing))}', status_code=400)
    return [{'id': r['id'], 'name': r['name']} for r in found]


def set_user_roles(user_id: str, role_names: list[str]) -> list[str]:
    """Replace manageable realm roles; leave other realm roles untouched."""
    current = get_user_realm_roles(user_id)
    manageable_current = [r for r in current if r.get('name') in MANAGEABLE_ROLES]
    desired_names = [n for n in role_names if n in MANAGEABLE_ROLES]

    to_remove = [r for r in manageable_current if r['name'] not in desired_names]
    to_add_names = [
        n for n in desired_names
        if n not in {r['name'] for r in manageable_current}
    ]

    if to_remove:
        res = requests.delete(
            _realm_url(f'/users/{user_id}/role-mappings/realm'),
            headers=_headers(),
            json=[{'id': r['id'], 'name': r['name']} for r in to_remove],
            timeout=20,
        )
        if res.status_code not in (204, 200):
            raise KeycloakAdminError(
                f'Remove roles failed ({res.status_code}): {res.text}',
                status_code=502,
            )

    if to_add_names:
        reps = _role_reps(to_add_names)
        res = requests.post(
            _realm_url(f'/users/{user_id}/role-mappings/realm'),
            headers=_headers(),
            json=reps,
            timeout=20,
        )
        if res.status_code not in (204, 200):
            raise KeycloakAdminError(
                f'Assign roles failed ({res.status_code}): {res.text}',
                status_code=502,
            )

    # Best-effort: logout sessions so permission changes apply on next login.
    try:
        requests.post(
            _realm_url(f'/users/{user_id}/logout'),
            headers=_headers(),
            timeout=20,
        )
    except requests.RequestException as e:
        current_app.logger.warning('Failed to logout user sessions after role change: %s', e)

    updated = get_user_realm_roles(user_id)
    return [r['name'] for r in updated if r.get('name') in MANAGEABLE_ROLES]


def fetch_user_access_token(username: str, password: str) -> dict[str, Any]:
    """Password-grant against the app client; returns token payload + decoded claims."""
    client_id = os.getenv('KEYCLOAK_TOKEN_CLIENT_ID') or os.getenv('KEYCLOAK_CLIENT_ID', 'flask-backend')
    # Public clients (flask-backend) must not send a secret. Only use an explicit token-client secret.
    client_secret = os.getenv('KEYCLOAK_TOKEN_CLIENT_SECRET', '')

    data = {
        'grant_type': 'password',
        'client_id': client_id,
        'username': username,
        'password': password,
        'scope': 'openid profile email',
    }
    if client_secret:
        data['client_secret'] = client_secret

    try:
        res = requests.post(_app_token_url(), data=data, timeout=20)
    except requests.RequestException as e:
        raise KeycloakAdminError(f'Token request failed: {e}', status_code=502) from e

    if res.status_code != 200:
        raise KeycloakAdminError(
            f'Token request failed ({res.status_code}): {res.text}',
            status_code=400,
        )

    body = res.json()
    access_token = body.get('access_token')
    if not access_token:
        raise KeycloakAdminError('Token response missing access_token', status_code=502)

    claims = pyjwt.decode(access_token, options={'verify_signature': False})
    exp = claims.get('exp')
    iat = claims.get('iat')
    exp_iso = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
        if isinstance(exp, int)
        else None
    )
    iat_iso = (
        datetime.fromtimestamp(iat, tz=timezone.utc).isoformat()
        if isinstance(iat, int)
        else None
    )
    roles = [
        r for r in claims.get('realm_access', {}).get('roles', [])
        if r in MANAGEABLE_ROLES or ':' in r
    ]

    return {
        'access_token': access_token,
        'token_type': body.get('token_type', 'Bearer'),
        'expires_in': body.get('expires_in'),
        'refresh_expires_in': body.get('refresh_expires_in'),
        # Omit refresh_token from UI payloads (large; not needed for the demo panel).
        'scope': body.get('scope'),
        'claims': {
            'sub': claims.get('sub'),
            'preferred_username': claims.get('preferred_username'),
            'email': claims.get('email'),
            'roles': roles,
            'iat': iat,
            'iat_iso': iat_iso,
            'exp': exp,
            'exp_iso': exp_iso,
        },
    }


def user_summary(user: dict[str, Any], roles: list[str] | None = None) -> dict[str, Any]:
    return {
        'id': user.get('id'),
        'username': user.get('username'),
        'email': user.get('email'),
        'firstName': user.get('firstName'),
        'lastName': user.get('lastName'),
        'enabled': user.get('enabled', True),
        'roles': roles if roles is not None else [],
    }
