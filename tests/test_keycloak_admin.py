"""Unit tests for app/auth/keycloak_admin.py. No real Keycloak: `requests` is mocked."""
import time
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
import requests

from app.auth import keycloak_admin as kc

MOD = 'app.auth.keycloak_admin'
# Keep the real function; the autouse fixture below patches the module attribute.
REAL_ADMIN_TOKEN = kc.get_admin_access_token


def resp(status=200, json_data=None, text=''):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else {}
    r.text = text
    return r


@pytest.fixture(autouse=True)
def fake_admin_token():
    with patch(f'{MOD}.get_admin_access_token', return_value='admintok'):
        yield


@pytest.fixture
def clean_env(monkeypatch):
    for name in (
        'KEYCLOAK_ADMIN_API_URL', 'KEYCLOAK_INTERNAL_URL', 'KEYCLOAK_REALM',
        'KEYCLOAK_ADMIN_TOKEN_URL', 'KEYCLOAK_TOKEN_URL', 'KEYCLOAK_USER', 'KEYCLOAK_ADMIN',
        'KEYCLOAK_PASSWORD', 'KEYCLOAK_ADMIN_PASSWORD', 'KEYCLOAK_ADMIN_CLIENT_ID',
        'KEYCLOAK_TOKEN_CLIENT_ID', 'KEYCLOAK_CLIENT_ID', 'KEYCLOAK_TOKEN_CLIENT_SECRET',
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# ------------------------------- config helpers -------------------------------

def test_error_has_message_and_status():
    e = kc.KeycloakAdminError('boom', 418)
    assert e.message == 'boom' and e.status_code == 418 and str(e) == 'boom'


def test_admin_base_url_default_and_override(clean_env):
    assert kc._admin_base_url() == 'http://keycloak_auth:8080/admin'
    clean_env.setenv('KEYCLOAK_INTERNAL_URL', 'http://kc:1')
    assert kc._admin_base_url() == 'http://kc:1/admin'
    clean_env.setenv('KEYCLOAK_ADMIN_API_URL', 'http://x/admin/')
    assert kc._admin_base_url() == 'http://x/admin'


def test_realm_default_and_override(clean_env):
    assert kc._realm() == 'inventory-realm'
    clean_env.setenv('KEYCLOAK_REALM', 'other')
    assert kc._realm() == 'other'


def test_token_url_variants(clean_env):
    clean_env.setenv('KEYCLOAK_ADMIN_TOKEN_URL', 'http://explicit/token')
    assert kc._token_url() == 'http://explicit/token'
    clean_env.delenv('KEYCLOAK_ADMIN_TOKEN_URL')
    assert kc._token_url() == 'http://keycloak_auth:8080/realms/master/protocol/openid-connect/token'
    clean_env.setenv('KEYCLOAK_TOKEN_URL', 'http://h:1/realms/inv/protocol/openid-connect/token')
    assert kc._token_url() == 'http://h:1/realms/master/protocol/openid-connect/token'
    clean_env.setenv('KEYCLOAK_TOKEN_URL', 'http://h:1/token')
    assert kc._token_url() == 'http://keycloak_auth:8080/realms/master/protocol/openid-connect/token'


def test_app_token_url(clean_env):
    assert kc._app_token_url().endswith('/realms/inventory-realm/protocol/openid-connect/token')
    clean_env.setenv('KEYCLOAK_TOKEN_URL', 'http://t')
    assert kc._app_token_url() == 'http://t'


def test_realm_url_and_headers(clean_env):
    assert kc._realm_url('/users') == 'http://keycloak_auth:8080/admin/realms/inventory-realm/users'
    h = kc._headers()
    assert h['Authorization'] == 'Bearer admintok'
    assert h['Content-Type'] == 'application/json'


# ----------------------------- get_admin_access_token -----------------------------

class TestAdminToken:
    def test_ok(self, clean_env):
        with patch(f'{MOD}.requests.post', return_value=resp(200, {'access_token': 'abc'})) as post:
            assert REAL_ADMIN_TOKEN() == 'abc'
        data = post.call_args.kwargs['data']
        assert data['username'] == 'admin' and data['client_id'] == 'admin-cli'

    def test_uses_env_credentials(self, clean_env):
        clean_env.setenv('KEYCLOAK_USER', 'root')
        clean_env.setenv('KEYCLOAK_PASSWORD', 'pw')
        with patch(f'{MOD}.requests.post', return_value=resp(200, {'access_token': 'abc'})) as post:
            REAL_ADMIN_TOKEN()
        assert post.call_args.kwargs['data']['username'] == 'root'
        assert post.call_args.kwargs['data']['password'] == 'pw'

    def test_network_error(self, clean_env):
        with patch(f'{MOD}.requests.post', side_effect=requests.ConnectionError('down')):
            with pytest.raises(kc.KeycloakAdminError) as ei:
                REAL_ADMIN_TOKEN()
        assert ei.value.status_code == 500

    def test_non_200(self, clean_env):
        with patch(f'{MOD}.requests.post', return_value=resp(401, text='nope')):
            with pytest.raises(kc.KeycloakAdminError) as ei:
                REAL_ADMIN_TOKEN()
        assert ei.value.status_code == 502

    def test_missing_token(self, clean_env):
        with patch(f'{MOD}.requests.post', return_value=resp(200, {})):
            with pytest.raises(kc.KeycloakAdminError) as ei:
                REAL_ADMIN_TOKEN()
        assert 'missing access_token' in ei.value.message


# ------------------------------- users CRUD -------------------------------

def test_list_users_ok_and_search():
    with patch(f'{MOD}.requests.get', return_value=resp(200, [{'id': '1'}])) as get:
        assert kc.list_users(search='al', max_results=5) == [{'id': '1'}]
    assert get.call_args.kwargs['params'] == {'max': 5, 'search': 'al'}
    with patch(f'{MOD}.requests.get', return_value=resp(200, [])) as get:
        kc.list_users()
    assert 'search' not in get.call_args.kwargs['params']


def test_list_users_error():
    with patch(f'{MOD}.requests.get', return_value=resp(500, text='x')):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.list_users()
    assert ei.value.status_code == 502


def test_get_user_variants():
    with patch(f'{MOD}.requests.get', return_value=resp(200, {'id': '1'})):
        assert kc.get_user('1') == {'id': '1'}
    with patch(f'{MOD}.requests.get', return_value=resp(404)):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.get_user('1')
    assert ei.value.status_code == 404
    with patch(f'{MOD}.requests.get', return_value=resp(500, text='e')):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.get_user('1')
    assert ei.value.status_code == 502


def test_find_user_id_by_username():
    with patch(f'{MOD}.requests.get', return_value=resp(200, [{'id': 'abc'}])):
        assert kc.find_user_id_by_username('a') == 'abc'
    with patch(f'{MOD}.requests.get', return_value=resp(200, [])):
        assert kc.find_user_id_by_username('a') is None
    with patch(f'{MOD}.requests.get', return_value=resp(500, text='e')):
        with pytest.raises(kc.KeycloakAdminError):
            kc.find_user_id_by_username('a')


def _create(**over):
    args = dict(username='u', email='e@x.com', first_name='F', last_name='L', password='pw')
    args.update(over)
    return kc.create_user(**args)


def test_create_user_ok_with_roles():
    with patch(f'{MOD}.requests.post', return_value=resp(201)), \
            patch(f'{MOD}.find_user_id_by_username', return_value='id1'), \
            patch(f'{MOD}.set_user_roles') as set_roles, \
            patch(f'{MOD}.get_user', return_value={'id': 'id1'}):
        assert _create(roles=['group:employee']) == {'id': 'id1'}
    set_roles.assert_called_once_with('id1', ['group:employee'])


def test_create_user_ok_without_roles():
    with patch(f'{MOD}.requests.post', return_value=resp(204)), \
            patch(f'{MOD}.find_user_id_by_username', return_value='id1'), \
            patch(f'{MOD}.set_user_roles') as set_roles, \
            patch(f'{MOD}.get_user', return_value={'id': 'id1'}):
        _create()
    set_roles.assert_not_called()


def test_create_user_conflict():
    with patch(f'{MOD}.requests.post', return_value=resp(409)):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            _create()
    assert ei.value.status_code == 409


def test_create_user_failure():
    with patch(f'{MOD}.requests.post', return_value=resp(500, text='e')):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            _create()
    assert ei.value.status_code == 502


def test_create_user_cannot_lookup():
    with patch(f'{MOD}.requests.post', return_value=resp(201)), \
            patch(f'{MOD}.find_user_id_by_username', return_value=None):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            _create()
    assert 'could not be looked up' in ei.value.message


# ------------------------------- roles -------------------------------

def test_get_realm_roles():
    with patch(f'{MOD}.requests.get', return_value=resp(200, [{'name': 'r'}])):
        assert kc.get_realm_roles() == [{'name': 'r'}]
    with patch(f'{MOD}.requests.get', return_value=resp(500, text='e')):
        with pytest.raises(kc.KeycloakAdminError):
            kc.get_realm_roles()


def test_get_user_realm_roles():
    with patch(f'{MOD}.requests.get', return_value=resp(200, [{'name': 'r'}])):
        assert kc.get_user_realm_roles('1') == [{'name': 'r'}]
    with patch(f'{MOD}.requests.get', return_value=resp(404)):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.get_user_realm_roles('1')
    assert ei.value.status_code == 404
    with patch(f'{MOD}.requests.get', return_value=resp(500, text='e')):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.get_user_realm_roles('1')
    assert ei.value.status_code == 502


def test_role_reps_ok_and_unknown():
    all_roles = [{'id': '1', 'name': 'group:employee'}, {'id': '2', 'name': 'group:manager'}]
    with patch(f'{MOD}.get_realm_roles', return_value=all_roles):
        assert kc._role_reps(['group:employee']) == [{'id': '1', 'name': 'group:employee'}]
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc._role_reps(['group:employee', 'bogus'])
    assert ei.value.status_code == 400 and 'bogus' in ei.value.message


def _set_roles_patches(current, after, delete_status=204, post_status=204, logout_exc=None):
    calls = iter([current, after])
    return (
        patch(f'{MOD}.get_user_realm_roles', side_effect=lambda uid: next(calls)),
        patch(f'{MOD}.requests.delete', return_value=resp(delete_status, text='e')),
        patch(f'{MOD}.requests.post',
              side_effect=([resp(post_status, text='e'), logout_exc or resp(204)])),
        patch(f'{MOD}._role_reps', return_value=[{'id': '9', 'name': 'product:view'}]),
    )


def test_set_user_roles_adds_and_removes(app):
    current = [{'id': '1', 'name': 'stock:view'}, {'id': '2', 'name': 'offline_access'}]
    after = [{'name': 'product:view'}, {'name': 'offline_access'}]
    p_roles, p_del, p_post, p_reps = _set_roles_patches(current, after)
    with p_roles, p_del as dele, p_post as post, p_reps:
        result = kc.set_user_roles('u1', ['product:view', 'not-manageable'])
    assert result == ['product:view']
    dele.assert_called_once()
    assert post.call_count == 2  # assign + logout


def test_set_user_roles_noop_still_logs_out(app):
    current = [{'id': '1', 'name': 'stock:view'}]
    calls = iter([current, current])
    with patch(f'{MOD}.get_user_realm_roles', side_effect=lambda uid: next(calls)), \
            patch(f'{MOD}.requests.post', return_value=resp(204)) as post, \
            patch(f'{MOD}.requests.delete') as dele:
        assert kc.set_user_roles('u1', ['stock:view']) == ['stock:view']
    dele.assert_not_called()
    assert post.call_count == 1  # only the logout


def test_set_user_roles_remove_fails(app):
    p_roles, p_del, p_post, p_reps = _set_roles_patches(
        [{'id': '1', 'name': 'stock:view'}], [], delete_status=500)
    with p_roles, p_del, p_post, p_reps:
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.set_user_roles('u1', [])
    assert 'Remove roles failed' in ei.value.message


def test_set_user_roles_assign_fails(app):
    p_roles, p_del, p_post, p_reps = _set_roles_patches([], [], post_status=500)
    with p_roles, p_del, p_post, p_reps:
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.set_user_roles('u1', ['product:view'])
    assert 'Assign roles failed' in ei.value.message


def test_set_user_roles_logout_failure_is_swallowed(app):
    after = [{'name': 'product:view'}]
    calls = iter([[], after])
    with patch(f'{MOD}.get_user_realm_roles', side_effect=lambda uid: next(calls)), \
            patch(f'{MOD}._role_reps', return_value=[{'id': '9', 'name': 'product:view'}]), \
            patch(f'{MOD}.requests.post',
                  side_effect=[resp(204), requests.ConnectionError('x')]):
        assert kc.set_user_roles('u1', ['product:view']) == ['product:view']


# --------------------------- fetch_user_access_token ---------------------------

def make_jwt(**claims):
    return pyjwt.encode(claims, 'secret', algorithm='HS256')


def test_fetch_token_ok(clean_env):
    now = int(time.time())
    token = make_jwt(sub='s', preferred_username='alice', email='a@x.com', iat=now, exp=now + 300,
                     realm_access={'roles': ['product:view', 'offline_access', 'group:employee']})
    body = {'access_token': token, 'token_type': 'Bearer', 'expires_in': 300, 'scope': 'openid'}
    with patch(f'{MOD}.requests.post', return_value=resp(200, body)) as post:
        out = kc.fetch_user_access_token('alice', 'pw')
    assert out['access_token'] == token
    assert out['claims']['preferred_username'] == 'alice'
    assert out['claims']['roles'] == ['product:view', 'group:employee']
    assert out['claims']['exp_iso'] and out['claims']['iat_iso']
    assert 'client_secret' not in post.call_args.kwargs['data']


def test_fetch_token_sends_secret_and_handles_missing_times(clean_env):
    clean_env.setenv('KEYCLOAK_TOKEN_CLIENT_SECRET', 's3cret')
    token = make_jwt(sub='s')
    with patch(f'{MOD}.requests.post', return_value=resp(200, {'access_token': token})) as post:
        out = kc.fetch_user_access_token('alice', 'pw')
    assert post.call_args.kwargs['data']['client_secret'] == 's3cret'
    assert out['claims']['exp_iso'] is None and out['claims']['iat_iso'] is None


def test_fetch_token_errors(clean_env):
    with patch(f'{MOD}.requests.post', side_effect=requests.ConnectionError('down')):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.fetch_user_access_token('a', 'b')
    assert ei.value.status_code == 502
    with patch(f'{MOD}.requests.post', return_value=resp(401, text='bad')):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.fetch_user_access_token('a', 'b')
    assert ei.value.status_code == 400
    with patch(f'{MOD}.requests.post', return_value=resp(200, {})):
        with pytest.raises(kc.KeycloakAdminError) as ei:
            kc.fetch_user_access_token('a', 'b')
    assert 'missing access_token' in ei.value.message


# ------------------------------- user_summary -------------------------------

def test_user_summary_defaults():
    s = kc.user_summary({'id': '1', 'username': 'u'})
    assert s['roles'] == [] and s['enabled'] is True and s['email'] is None
    assert kc.user_summary({'id': '1', 'enabled': False}, ['r'])['roles'] == ['r']
