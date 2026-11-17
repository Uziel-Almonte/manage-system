"""Edge-case tests for the JSON API: products, stock, audit, users, delete errors."""
from unittest.mock import patch

import pytest

from app.auth.keycloak_admin import KeycloakAdminError
from app.database import db
from app.products.models import Product
from app.stock.models import StockMovement


@pytest.fixture
def two_products(app):
    a = Product(name='Alpha', sku='A-1', price=10, qty=5, min_stock=1, category='cat1')
    b = Product(name='Beta', sku='B-1', price=20, qty=50, min_stock=1, category='cat2')
    db.session.add_all([a, b])
    db.session.commit()
    return a.id, b.id


# ------------------------------- products API -------------------------------

def test_list_products_search_category_sort(app_client, two_products):
    r = app_client.get('/api/products?search=alp')
    assert r.status_code == 200
    assert [p['sku'] for p in r.get_json()['products']] == ['A-1']

    r = app_client.get('/api/products?category=cat2')
    assert [p['sku'] for p in r.get_json()['products']] == ['B-1']

    r = app_client.get('/api/products?sort_by=price&sort_order=desc')
    assert [p['sku'] for p in r.get_json()['products']] == ['B-1', 'A-1']

    r = app_client.get('/api/products?sort_by=price&sort_order=asc')
    assert [p['sku'] for p in r.get_json()['products']] == ['A-1', 'B-1']


def test_update_product_all_fields(app_client, two_products):
    a, _ = two_products
    r = app_client.put(f'/api/products/{a}', json={
        'name': 'Alpha2', 'sku': 'A-2', 'description': 'd', 'category': 'c', 'price': 11.5,
        'qty': 20, 'min_stock': 3, 'status': 'inactive',
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body['name'] == 'Alpha2' and body['qty'] == 20 and body['status'] == 'inactive'
    assert StockMovement.query.filter_by(product_id=a, type='entry').count() == 1


def test_update_product_qty_decrease_records_exit(app_client, two_products):
    a, _ = two_products
    r = app_client.put(f'/api/products/{a}', json={'qty': 1})
    assert r.status_code == 200
    assert StockMovement.query.filter_by(product_id=a, type='exit').count() == 1


def test_update_product_duplicate_sku(app_client, two_products):
    a, _ = two_products
    r = app_client.put(f'/api/products/{a}', json={'sku': 'B-1'})
    assert r.status_code == 400


def test_update_product_same_sku_ok(app_client, two_products):
    a, _ = two_products
    assert app_client.put(f'/api/products/{a}', json={'sku': 'A-1'}).status_code == 200


def test_update_product_not_found_and_overflow(app_client):
    assert app_client.put('/api/products/9999', json={'name': 'x'}).status_code == 404
    assert app_client.put(f'/api/products/{10**30}', json={'name': 'x'}).status_code == 404


# -------------------------------- stock API --------------------------------

def test_movement_validation_errors(app_client, two_products):
    a, _ = two_products
    r = app_client.post('/api/stock/movement', json={'product_id': 9999, 'type': 'entry', 'qty_change': 1})
    assert r.status_code == 404
    r = app_client.post('/api/stock/movement', json={'product_id': a, 'type': 'exit', 'qty_change': 999})
    assert r.status_code == 400
    r = app_client.post('/api/stock/movement', json={'product_id': a, 'type': 'bogus', 'qty_change': 1})
    assert r.status_code in (400, 422)
    r = app_client.post('/api/stock/movement', json={'product_id': a, 'type': 'entry', 'qty_change': 0})
    assert r.status_code in (400, 422)


def test_movement_overflow_product_id(app_client):
    r = app_client.post('/api/stock/movement',
                        json={'product_id': 10**30, 'type': 'entry', 'qty_change': 1})
    assert r.status_code in (404, 422)


def test_history_filters(app_client, two_products):
    a, b = two_products
    app_client.post('/api/stock/movement', json={'product_id': a, 'type': 'entry', 'qty_change': 2, 'user': 'bob'})
    app_client.post('/api/stock/movement', json={'product_id': b, 'type': 'exit', 'qty_change': 2, 'user': 'amy'})

    assert len(app_client.get(f'/api/stock/history?product_id={a}').get_json()) == 1
    assert len(app_client.get('/api/stock/history?type=exit').get_json()) == 1
    assert len(app_client.get('/api/stock/history?user=bob').get_json()) == 1
    assert len(app_client.get('/api/stock/history?date_from=2000-01-01&date_to=2100-01-01').get_json()) == 2
    assert len(app_client.get('/api/stock/history?date_from=2100-01-01').get_json()) == 0
    # unparseable dates are ignored, not errors
    assert len(app_client.get('/api/stock/history?date_from=bad&date_to=bad').get_json()) == 2


def test_alerts_endpoint(app_client, two_products):
    assert app_client.get('/api/stock/alerts').status_code == 200


# -------------------------------- audit API --------------------------------

def test_audit_list_filters(app_client, two_products):
    a, _ = two_products
    assert app_client.get('/api/audit').status_code == 200
    r = app_client.get(f'/api/audit?table=products&record_id={a}&action=INSERT&limit=5&offset=0')
    assert r.status_code == 200
    assert r.get_json()['total'] >= 1


def test_audit_product_and_movement_lookup(app_client, two_products):
    a, _ = two_products
    assert app_client.get(f'/api/audit/product/{a}').status_code == 200
    assert app_client.get('/api/audit/product/9999').status_code == 404
    assert app_client.get('/api/audit/movement/9999').status_code == 404
    mv = app_client.post('/api/stock/movement',
                         json={'product_id': a, 'type': 'entry', 'qty_change': 1}).get_json()
    assert app_client.get(f"/api/audit/movement/{mv['id']}").status_code == 200


# -------------------------------- users API --------------------------------

USER = {'id': 'u1', 'username': 'alice', 'email': 'a@x.com', 'firstName': 'A', 'lastName': 'L',
        'enabled': True}


@patch('app.users.views.list_users', side_effect=KeycloakAdminError('down', 502))
def test_api_list_users_error(mock_list, app_client):
    r = app_client.get('/api/users?search=al')
    assert r.status_code == 502
    mock_list.assert_called_once_with(search='al')


def test_api_create_user_validation(app_client):
    r = app_client.post('/api/users', json={'username': 'x'})
    assert r.status_code == 400


@patch('app.users.views.create_user', side_effect=KeycloakAdminError('exists', 409))
def test_api_create_user_conflict(mock_create, app_client):
    r = app_client.post('/api/users', json={'username': 'x', 'password': 'p'})
    assert r.status_code == 409
    assert r.get_json()['message'] == 'exists'


@patch('app.users.views.get_user_realm_roles', return_value=[{'name': 'group:manager'}, {'name': 'zzz'}])
@patch('app.users.views.get_user', return_value=USER)
def test_api_get_user(mock_get, mock_roles, app_client):
    r = app_client.get('/api/users/u1')
    assert r.status_code == 200
    assert r.get_json()['roles'] == ['group:manager']


@patch('app.users.views.get_user', side_effect=KeycloakAdminError('User not found', 404))
def test_api_get_user_not_found(mock_get, app_client):
    assert app_client.get('/api/users/nope').status_code == 404


def test_api_set_roles_validation(app_client):
    r = app_client.put('/api/users/u1/roles', json={'roles': 'not-a-list'})
    assert r.status_code == 400


@patch('app.users.views.set_user_roles', side_effect=KeycloakAdminError('bad', 400))
def test_api_set_roles_error(mock_set, app_client):
    assert app_client.put('/api/users/u1/roles', json={'roles': []}).status_code == 400


def test_api_issue_token_requires_password(app_client):
    assert app_client.post('/api/users/u1/token', json={}).status_code == 400


@patch('app.users.views.fetch_user_access_token', return_value={'access_token': 't'})
@patch('app.users.views.get_user', return_value=USER)
def test_api_issue_token_ok(mock_get, mock_token, app_client):
    r = app_client.post('/api/users/u1/token', json={'password': 'pw'})
    assert r.status_code == 200
    assert r.get_json()['token']['access_token'] == 't'
    mock_token.assert_called_once_with('alice', 'pw')


@patch('app.users.views.get_user', return_value={'id': 'u1'})
def test_api_issue_token_user_without_username(mock_get, app_client):
    assert app_client.post('/api/users/u1/token', json={'password': 'pw'}).status_code == 400


@patch('app.users.views.fetch_user_access_token', side_effect=KeycloakAdminError('bad pw', 400))
@patch('app.users.views.get_user', return_value=USER)
def test_api_issue_token_keycloak_error(mock_get, mock_token, app_client):
    assert app_client.post('/api/users/u1/token', json={'password': 'x'}).status_code == 400


# --------------------------- UI delete error path ---------------------------

def test_ui_delete_product_commit_failure(app_client, two_products):
    a, _ = two_products
    with patch('app.main.db.session.commit', side_effect=RuntimeError('db error')):
        r = app_client.post(f'/products/{a}/delete')
    assert r.status_code == 302
    assert db.session.get(Product, a) is not None
