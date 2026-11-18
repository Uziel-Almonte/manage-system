"""Tests for JWT middleware, session guards and the OAuth views.

The shared `app` fixture sets TESTING=True, which bypasses auth. Here we turn it
off so the real checks run. Keycloak is never contacted: keys are generated locally.
"""
import json
import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.auth import middleware

KID = 'test-kid'


@pytest.fixture(scope='module')
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def real_auth(app, monkeypatch):
    """Run with the real auth checks and a clean key cache."""
    app.config['TESTING'] = False
    monkeypatch.setattr(middleware, '_public_keys', None)
    yield app
    app.config['TESTING'] = True


@pytest.fixture
def client(real_auth):
    return real_auth.test_client()


def make_token(rsa_key, roles=(), kid=KID, exp_delta=300, key=None):
    now = int(time.time())
    payload = {'sub': 'u', 'iat': now, 'exp': now + exp_delta,
               'realm_access': {'roles': list(roles)}}
    return jwt.encode(payload, key or rsa_key, algorithm='RS256', headers={'kid': kid})


def keys_for(rsa_key):
    return {KID: rsa_key.public_key()}


def auth(token):
    return {'Authorization': f'Bearer {token}'}


# ------------------------------- require_jwt -------------------------------

def test_missing_header_is_401(client):
    res = client.get('/health')
    assert res.status_code == 401
    assert 'Missing' in res.get_json()['message']


def test_non_bearer_header_is_401(client):
    assert client.get('/health', headers={'Authorization': 'Basic abc'}).status_code == 401


def test_valid_token_passes(client, rsa_key):
    with patch.object(middleware, 'get_keycloak_public_keys', return_value=keys_for(rsa_key)):
        res = client.get('/health', headers=auth(make_token(rsa_key)))
    assert res.status_code == 200


def test_unknown_kid_is_401(client, rsa_key):
    with patch.object(middleware, 'get_keycloak_public_keys', return_value=keys_for(rsa_key)):
        res = client.get('/health', headers=auth(make_token(rsa_key, kid='other')))
    assert res.status_code == 401
    assert 'key not found' in res.get_json()['message']


def test_expired_token_is_401(client, rsa_key):
    with patch.object(middleware, 'get_keycloak_public_keys', return_value=keys_for(rsa_key)):
        res = client.get('/health', headers=auth(make_token(rsa_key, exp_delta=-60)))
    assert res.status_code == 401
    assert 'expired' in res.get_json()['message']


def test_wrong_signature_is_401(client, rsa_key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with patch.object(middleware, 'get_keycloak_public_keys', return_value=keys_for(rsa_key)):
        res = client.get('/health', headers=auth(make_token(rsa_key, key=other)))
    assert res.status_code == 401
    assert 'Invalid token' in res.get_json()['message']


def test_garbage_token_is_401(client, rsa_key):
    with patch.object(middleware, 'get_keycloak_public_keys', return_value=keys_for(rsa_key)):
        res = client.get('/health', headers=auth('not.a.jwt'))
    assert res.status_code == 401


def test_unexpected_error_is_500(client, rsa_key):
    with patch.object(middleware, 'get_keycloak_public_keys', side_effect=RuntimeError('boom')):
        res = client.get('/health', headers=auth(make_token(rsa_key)))
    assert res.status_code == 500


# ------------------------------- require_scope -------------------------------

def test_scope_missing_is_403(client, rsa_key):
    with patch.object(middleware, 'get_keycloak_public_keys', return_value=keys_for(rsa_key)):
        res = client.get('/api/users', headers=auth(make_token(rsa_key, roles=['product:view'])))
    assert res.status_code == 403
    assert 'user:manage' in res.get_json()['message']


def test_scope_present_is_allowed(client, rsa_key):
    with patch.object(middleware, 'get_keycloak_public_keys', return_value=keys_for(rsa_key)), \
            patch('app.users.views.list_users', return_value=[]):
        res = client.get('/api/users', headers=auth(make_token(rsa_key, roles=['user:manage'])))
    assert res.status_code == 200


def test_scope_without_token_is_401(client):
    assert client.get('/api/users').status_code == 401


# --------------------------- get_keycloak_public_keys ---------------------------

def _jwks(rsa_key):
    jwk = json.loads(RSAAlgorithm.to_jwk(rsa_key.public_key()))
    jwk['kid'] = KID
    return json.dumps({'keys': [jwk]}).encode()


def _urlopen_returning(body):
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = body
    return cm


def test_public_keys_from_jwks_url(real_auth, rsa_key, monkeypatch):
    monkeypatch.setenv('KEYCLOAK_JWKS_URL', 'http://kc/certs')
    with real_auth.app_context(), \
            patch('app.auth.middleware.urllib.request.urlopen',
                  return_value=_urlopen_returning(_jwks(rsa_key))) as op:
        keys = middleware.get_keycloak_public_keys()
    assert KID in keys
    assert op.call_args.args[0] == 'http://kc/certs'


def test_public_keys_from_realm_url(real_auth, rsa_key, monkeypatch):
    monkeypatch.delenv('KEYCLOAK_JWKS_URL', raising=False)
    monkeypatch.setenv('KEYCLOAK_REALM_URL', 'http://kc/realms/r')
    with real_auth.app_context(), \
            patch('app.auth.middleware.urllib.request.urlopen',
                  return_value=_urlopen_returning(_jwks(rsa_key))) as op:
        middleware.get_keycloak_public_keys()
    assert op.call_args.args[0] == 'http://kc/realms/r/protocol/openid-connect/certs'


def test_public_keys_requires_config(real_auth, monkeypatch):
    monkeypatch.delenv('KEYCLOAK_JWKS_URL', raising=False)
    monkeypatch.delenv('KEYCLOAK_REALM_URL', raising=False)
    with real_auth.app_context(), pytest.raises(ValueError):
        middleware.get_keycloak_public_keys()


def test_public_keys_fetch_failure_returns_empty(real_auth, monkeypatch):
    monkeypatch.setenv('KEYCLOAK_JWKS_URL', 'http://kc/certs')
    with real_auth.app_context(), \
            patch('app.auth.middleware.urllib.request.urlopen', side_effect=OSError('down')):
        assert middleware.get_keycloak_public_keys() == {}


# ------------------------ login_required / require_ui_scope ------------------------

def test_login_required_redirects_anonymous(client):
    res = client.get('/')
    assert res.status_code == 302
    assert '/auth/login-page' in res.headers['Location']


def test_login_required_allows_session_user(client):
    with client.session_transaction() as s:
        s['user'] = {'preferred_username': 'alice'}
        s['user_scopes'] = ['product:view']
    assert client.get('/').status_code == 200


def test_login_required_user_fallbacks(client):
    with client.session_transaction() as s:
        s['user'] = {'email': 'a@x.com'}
    assert client.get('/').status_code == 200
    with client.session_transaction() as s:
        s['user'] = {}
    assert client.get('/').status_code == 200


def test_ui_scope_denies_without_permission(client):
    with client.session_transaction() as s:
        s['user'] = {'preferred_username': 'alice'}
        s['user_scopes'] = ['product:view']
    res = client.get('/reports')
    assert res.status_code == 303
    assert res.headers['Location'].endswith('/')


def test_ui_scope_allows_with_permission(client):
    with client.session_transaction() as s:
        s['user'] = {'preferred_username': 'boss'}
        s['user_scopes'] = ['report:view']
    assert client.get('/reports').status_code == 200


# --------------------------------- OAuth views ---------------------------------

def test_login_page_renders(app_client):
    assert app_client.get('/auth/login-page').status_code == 200


def test_login_redirects_to_keycloak(app_client):
    from flask import redirect
    with patch('app.auth.views.oauth.keycloak.authorize_redirect',
               return_value=redirect('http://kc/auth')) as ar:
        res = app_client.get('/auth/login')
    assert res.status_code == 302
    assert ar.call_args.args[0].endswith('/auth/callback')


def _access_token(roles):
    return jwt.encode({'realm_access': {'roles': roles}}, 'k', algorithm='HS256')


def test_callback_success_stores_session(app_client):
    token = {'userinfo': {'preferred_username': 'alice'},
             'access_token': _access_token(['product:view', 'offline_access', 'group:employee'])}
    with patch('app.auth.views.oauth.keycloak.authorize_access_token', return_value=token):
        res = app_client.get('/auth/callback')
    assert res.status_code == 302
    with app_client.session_transaction() as s:
        assert s['user'] == {'preferred_username': 'alice'}
        assert s['user_scopes'] == ['product:view', 'group:employee']


def test_callback_bad_access_token_gives_no_scopes(app_client):
    token = {'userinfo': {'preferred_username': 'alice'}, 'access_token': 'garbage'}
    with patch('app.auth.views.oauth.keycloak.authorize_access_token', return_value=token):
        res = app_client.get('/auth/callback')
    assert res.status_code == 302
    with app_client.session_transaction() as s:
        assert s['user_scopes'] == []


def test_callback_without_access_token(app_client):
    token = {'userinfo': {'preferred_username': 'alice'}}
    with patch('app.auth.views.oauth.keycloak.authorize_access_token', return_value=token):
        assert app_client.get('/auth/callback').status_code == 302


def test_callback_oauth_error_is_500(app_client):
    with patch('app.auth.views.oauth.keycloak.authorize_access_token',
               side_effect=RuntimeError('state mismatch')):
        res = app_client.get('/auth/callback')
    assert res.status_code == 500
    assert 'state mismatch' in res.get_json()['error']


def test_logout_clears_session_and_redirects(app_client, monkeypatch):
    monkeypatch.setenv('KEYCLOAK_LOGOUT_BASE', 'http://kc/logout')
    with app_client.session_transaction() as s:
        s['user'] = {'preferred_username': 'alice'}
    res = app_client.get('/auth/logout')
    assert res.status_code == 302
    loc = res.headers['Location']
    assert loc.startswith('http://kc/logout?client_id=')
    assert 'post_logout_redirect_uri=' in loc
    with app_client.session_transaction() as s:
        assert 'user' not in s


class TestAuthFailureMetrics:
    """Bad API tokens must feed the security dashboard/alert metrics (per-IP and total)."""

    def test_missing_token_counts_failure_by_ip(self, client):
        from app.telemetry import auth_failures_total, invalid_tokens_total

        ip = '10.9.8.7'
        before_ip = auth_failures_total.labels(source_ip=ip)._value.get()
        before_total = invalid_tokens_total._value.get()

        resp = client.get('/api/products', environ_overrides={'REMOTE_ADDR': ip})

        assert resp.status_code == 401
        assert auth_failures_total.labels(source_ip=ip)._value.get() == before_ip + 1
        assert invalid_tokens_total._value.get() == before_total + 1
