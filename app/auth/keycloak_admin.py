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
    """Error controlado para operaciones fallidas contra la API de Keycloak."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _admin_base_url() -> str:
    """
    Qué hace: resuelve la URL base del API de administración de Keycloak.
    Por qué lo hace: para centralizar la dirección del servidor y evitar repetirla.
    Cómo lo hace: lee variables de entorno y aplica un valor por defecto seguro para el entorno local.
    De dónde viene: el valor proviene de `KEYCLOAK_ADMIN_API_URL` o, si no existe, de `KEYCLOAK_INTERNAL_URL`.
    A dónde va: se usa como base para construir las rutas de administración.
    Librerías externas: aquí no interviene una librería externa; solo `os.getenv`.
    """
    return os.getenv(
        'KEYCLOAK_ADMIN_API_URL',
        os.getenv('KEYCLOAK_INTERNAL_URL', 'http://keycloak_auth:8080') + '/admin',
    ).rstrip('/')


def _realm() -> str:
    """
    Qué hace: obtiene el nombre del realm configurado.
    Por qué lo hace: para dirigir las operaciones al realm correcto de Keycloak.
    Cómo lo hace: lee una variable de entorno con valor por defecto.
    De dónde viene: el realm viene de `KEYCLOAK_REALM` o del valor `inventory-realm`.
    A dónde va: se inserta en todas las URLs de administración del realm.
    Librerías externas: no usa librerías externas; solo configuración del entorno.
    """
    return os.getenv('KEYCLOAK_REALM', 'inventory-realm')


def _token_url() -> str:
    """
    Qué hace: construye la URL para pedir el token de administrador de Keycloak.
    Por qué lo hace: para autenticar llamadas al API de administración.
    Cómo lo hace: prioriza una URL explícita y, si no existe, transforma la URL del realm hacia el realm `master`.
    De dónde viene: la dirección sale de `KEYCLOAK_ADMIN_TOKEN_URL` o de `KEYCLOAK_TOKEN_URL`.
    A dónde va: se usa en `get_admin_access_token()` para solicitar el token.
    Librerías externas: no hay librerías externas aquí; solo string handling y `os.getenv`.
    """
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
    """
    Qué hace: obtiene la URL del endpoint de token usado por la aplicación.
    Por qué lo hace: para pedir JWTs del cliente de frontend/backend sin mezclarlo con el token de admin.
    Cómo lo hace: lee una variable de entorno o aplica un valor por defecto.
    De dónde viene: el valor viene de `KEYCLOAK_TOKEN_URL`.
    A dónde va: se consume en `fetch_user_access_token()`.
    Librerías externas: no usa librerías externas; solo configuración.
    """
    return os.getenv(
        'KEYCLOAK_TOKEN_URL',
        'http://keycloak_auth:8080/realms/inventory-realm/protocol/openid-connect/token',
    )


def get_admin_access_token() -> str:
    """
    Qué hace: solicita un access token de administración para Keycloak.
    Por qué lo hace: porque la API admin requiere autenticación Bearer.
    Cómo lo hace: hace un `POST` con `requests` al endpoint de token usando credenciales del entorno.
    De dónde viene: las credenciales provienen de variables como `KEYCLOAK_USER` y `KEYCLOAK_PASSWORD`.
    A dónde va: el token resultante se reutiliza en `_headers()` para llamadas posteriores.
    Librerías externas: sí, usa `requests` para la petición HTTP.
    """
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
    """
    Qué hace: arma los encabezados HTTP estándar para el API de Keycloak.
    Por qué lo hace: para reutilizar autenticación y tipo de contenido en todas las llamadas.
    Cómo lo hace: inserta el Bearer token de administración y `Content-Type: application/json`.
    De dónde viene: el token viene de `get_admin_access_token()`.
    A dónde va: se pasa a `requests.get/post/delete` en el resto de funciones.
    Librerías externas: el header se usa para peticiones con `requests`, pero aquí no se llama directamente a una librería externa.
    """
    return {
        'Authorization': f'Bearer {get_admin_access_token()}',
        'Content-Type': 'application/json',
    }


def _realm_url(path: str = '') -> str:
    """
    Qué hace: construye una URL completa del realm de administración.
    Por qué lo hace: para evitar repetir concatenación de rutas en cada función.
    Cómo lo hace: combina la base admin, el realm configurado y el sufijo recibido.
    De dónde viene: el sufijo viene del llamado concreto y la base del entorno.
    A dónde va: se usa en casi todas las operaciones contra Keycloak.
    Librerías externas: no usa librerías externas; solo composición de strings.
    """
    return f"{_admin_base_url()}/realms/{_realm()}{path}"


def list_users(search: str | None = None, max_results: int = 50) -> list[dict[str, Any]]:
    """
    Qué hace: lista usuarios del realm con soporte opcional de búsqueda.
    Por qué lo hace: para alimentar pantallas de administración de usuarios.
    Cómo lo hace: ejecuta un `GET` al endpoint `/users` de Keycloak con parámetros de consulta.
    De dónde viene: los criterios de búsqueda vienen de la UI o del código que llama a este helper.
    A dónde va: devuelve una lista de diccionarios listos para ser renderizados o procesados.
    Librerías externas: sí, usa `requests` para hablar con Keycloak.
    """
    params: dict[str, Any] = {'max': max_results}
    if search:
        params['search'] = search
    res = requests.get(_realm_url('/users'), headers=_headers(), params=params, timeout=20)
    if res.status_code != 200:
        raise KeycloakAdminError(f'List users failed ({res.status_code}): {res.text}', status_code=502)
    return res.json()


def get_user(user_id: str) -> dict[str, Any]:
    """
    Qué hace: obtiene los detalles de un usuario por su ID.
    Por qué lo hace: para mostrar o actualizar información concreta de la cuenta.
    Cómo lo hace: llama al endpoint individual `/users/{id}` de Keycloak.
    De dónde viene: el ID viene de la ruta o de otra operación que ya identificó al usuario.
    A dónde va: retorna el JSON del usuario o un error controlado si no existe.
    Librerías externas: sí, usa `requests`.
    """
    res = requests.get(_realm_url(f'/users/{user_id}'), headers=_headers(), timeout=20)
    if res.status_code == 404:
        raise KeycloakAdminError('User not found', status_code=404)
    if res.status_code != 200:
        raise KeycloakAdminError(f'Get user failed ({res.status_code}): {res.text}', status_code=502)
    return res.json()


def find_user_id_by_username(username: str) -> str | None:
    """
    Qué hace: busca el ID de un usuario por nombre de usuario exacto.
    Por qué lo hace: porque varias operaciones de Keycloak necesitan el ID interno y no el username.
    Cómo lo hace: consulta `/users` con `username` y `exact=true`, luego toma el primer resultado.
    De dónde viene: el username viene del formulario o del flujo que creó/consultó al usuario.
    A dónde va: devuelve el ID o `None` si no se encuentra.
    Librerías externas: sí, usa `requests` para consultar Keycloak.
    """
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
    """
    Qué hace: crea un usuario nuevo en Keycloak y opcionalmente le asigna roles.
    Por qué lo hace: para registrar cuentas administrables desde la aplicación.
    Cómo lo hace: envía un `POST` con el payload del usuario, busca el ID resultante y llama a `set_user_roles()` si aplica.
    De dónde viene: los datos vienen del formulario y del flujo UI que llama a este helper.
    A dónde va: devuelve el usuario recién creado como diccionario de Keycloak.
    Librerías externas: sí, usa `requests` para crear y `Keycloak` para persistir el usuario.
    """
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
    """
    Qué hace: lista todos los roles del realm.
    Por qué lo hace: para validar y traducir nombres de roles antes de asignarlos.
    Cómo lo hace: realiza un `GET` al endpoint `/roles` de Keycloak.
    De dónde viene: la consulta viene de flujos que necesitan validar permisos o mapear roles.
    A dónde va: devuelve la lista completa de roles disponibles.
    Librerías externas: sí, usa `requests`.
    """
    res = requests.get(_realm_url('/roles'), headers=_headers(), timeout=20)
    if res.status_code != 200:
        raise KeycloakAdminError(f'List roles failed ({res.status_code}): {res.text}', status_code=502)
    return res.json()


def get_user_realm_roles(user_id: str) -> list[dict[str, Any]]:
    """
    Qué hace: obtiene los roles de realm asignados a un usuario.
    Por qué lo hace: para mostrar permisos actuales o calcular cambios.
    Cómo lo hace: consulta el endpoint de role mappings del usuario por su ID.
    De dónde viene: el `user_id` viene del detalle de usuario o de operaciones de roles.
    A dónde va: retorna los roles asignados al usuario.
    Librerías externas: sí, usa `requests`.
    """
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
    """
    Qué hace: convierte nombres de roles en representaciones completas de Keycloak.
    Por qué lo hace: porque la API de asignación espera objetos con `id` y `name`.
    Cómo lo hace: cruza los nombres solicitados contra todos los roles del realm y valida que existan.
    De dónde viene: la lista de nombres viene del formulario o del código que administra permisos.
    A dónde va: devuelve una lista lista para enviarse al endpoint de asignación.
    Librerías externas: la consulta de roles usa `requests` indirectamente a través de `get_realm_roles()`.
    """
    wanted = set(role_names)
    all_roles = get_realm_roles()
    found = [r for r in all_roles if r.get('name') in wanted]
    missing = wanted - {r['name'] for r in found}
    if missing:
        raise KeycloakAdminError(f'Unknown roles: {", ".join(sorted(missing))}', status_code=400)
    return [{'id': r['id'], 'name': r['name']} for r in found]


def set_user_roles(user_id: str, role_names: list[str]) -> list[str]:
    """
    Qué hace: reemplaza los roles administrables de un usuario por un nuevo conjunto.
    Por qué lo hace: para mantener permisos consistentes sin tocar roles externos a la app.
    Cómo lo hace: calcula roles a quitar y añadir, llama a los endpoints de mapeo y fuerza logout de sesiones.
    De dónde viene: la solicitud viene del formulario de edición de roles en la UI.
    A dónde va: devuelve la lista final de roles administrables activos para ese usuario.
    Librerías externas: sí, usa `requests` para modificar roles y `current_app` para registrar fallos de logout.
    """
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
    """
    Qué hace: solicita un JWT de usuario mediante password grant y devuelve metadatos del token.
    Por qué lo hace: para mostrar o verificar la autenticación del usuario en la interfaz.
    Cómo lo hace: hace un `POST` al endpoint de token, decodifica el JWT sin verificar firma y extrae claims relevantes.
    De dónde viene: las credenciales vienen del formulario o del flujo de emisión de token desde la UI.
    A dónde va: retorna un diccionario con el token, tiempos y claims resumidos.
    Librerías externas: sí, usa `requests` para pedir el token y `PyJWT` para decodificarlo.
    """
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
    """
    Qué hace: normaliza la estructura de un usuario para la interfaz.
    Por qué lo hace: para unificar el formato que consumen las plantillas.
    Cómo lo hace: extrae campos clave del diccionario original y asegura una lista de roles.
    De dónde viene: el dato viene de respuestas de Keycloak o de helpers que ya consultaron el usuario.
    A dónde va: devuelve un diccionario compacto listo para renderizar.
    Librerías externas: no usa librerías externas; solo transforma datos ya obtenidos.
    """
    return {
        'id': user.get('id'),
        'username': user.get('username'),
        'email': user.get('email'),
        'firstName': user.get('firstName'),
        'lastName': user.get('lastName'),
        'enabled': user.get('enabled', True),
        'roles': roles if roles is not None else [],
    }
