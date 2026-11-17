"""Tests for the server-rendered UI routes in app/main.py (Keycloak mocked)."""
from unittest.mock import patch

import pytest

from app.auth.keycloak_admin import KeycloakAdminError
from app.database import db
from app.products.models import Product
from app.stock.models import StockMovement

HX = {'HX-Request': 'true'}


@pytest.fixture
def seeded(app):
    """Three products (one low stock, one inactive) and one movement."""
    p1 = Product(name='Widget', sku='W-1', price=10, qty=50, min_stock=5, category='tools')
    p2 = Product(name='Gadget', sku='G-1', price=20, qty=2, min_stock=10, category='toys')
    p3 = Product(name='Old', sku='O-1', price=5, qty=1, min_stock=1, status='inactive')
    db.session.add_all([p1, p2, p3])
    db.session.commit()
    db.session.add(StockMovement(
        product_id=p1.id, user='tester', type='entry', prev_qty=40, new_qty=50, notes='seed'
    ))
    db.session.commit()
    return {'p1': p1.id, 'p2': p2.id, 'p3': p3.id}


# --------------------------- dashboard / products ---------------------------

def test_index_renders(app_client, seeded):
    res = app_client.get('/')
    assert res.status_code == 200


def test_products_list_and_filters(app_client, seeded):
    assert app_client.get('/products').status_code == 200
    res = app_client.get('/products?search=widget&sort_by=name&sort_order=asc')
    assert res.status_code == 200
    assert b'Widget' in res.data
    assert app_client.get('/products?sort_by=price&sort_order=desc').status_code == 200
    assert app_client.get('/products?sort_by=nonexistent').status_code == 200


def test_products_list_htmx_partial(app_client, seeded):
    res = app_client.get('/products?search=gadget', headers=HX)
    assert res.status_code == 200
    assert b'Gadget' in res.data


def test_new_product_form(app_client):
    assert app_client.get('/products/new').status_code == 200


def test_edit_product_form(app_client, seeded):
    assert app_client.get(f"/products/{seeded['p1']}/edit").status_code == 200


def test_edit_product_not_found_redirects(app_client):
    res = app_client.get('/products/9999/edit')
    assert res.status_code == 302
    assert '/products' in res.headers['Location']


def test_create_product_ok(app_client, app):
    res = app_client.post('/products', data={
        'name': 'New', 'sku': 'N-1', 'price': '9.99', 'qty': '5', 'min_stock': '1',
        'description': 'd', 'category': 'c',
    })
    assert res.status_code == 302
    assert Product.query.filter_by(sku='N-1').first() is not None


def test_create_product_missing_fields(app_client):
    res = app_client.post('/products', data={'name': 'x'})
    assert res.status_code == 302
    assert '/products/new' in res.headers['Location']


def test_create_product_duplicate_sku(app_client, seeded):
    res = app_client.post('/products', data={'name': 'Dup', 'sku': 'W-1', 'price': '1'})
    assert res.status_code == 302
    assert '/products/new' in res.headers['Location']
    assert Product.query.filter_by(sku='W-1').count() == 1


def test_create_product_invalid_price(app_client):
    res = app_client.post('/products', data={'name': 'Bad', 'sku': 'B-1', 'price': 'abc'})
    assert res.status_code == 302
    assert '/products/new' in res.headers['Location']
    assert Product.query.filter_by(sku='B-1').first() is None


def test_update_product_ok_with_qty_change(app_client, seeded):
    pid = seeded['p1']
    res = app_client.post(f'/products/{pid}', data={
        'name': 'Widget 2', 'sku': 'W-1', 'price': '11', 'qty': '60', 'min_stock': '6',
        'status': 'active', 'description': '', 'category': 'tools',
    })
    assert res.status_code == 302
    product = db.session.get(Product, pid)
    assert product.name == 'Widget 2'
    assert product.qty == 60
    assert StockMovement.query.filter_by(product_id=pid).count() == 2


def test_update_product_qty_decrease(app_client, seeded):
    pid = seeded['p1']
    res = app_client.post(f'/products/{pid}', data={
        'name': 'Widget', 'sku': 'W-1', 'price': '10', 'qty': '10', 'status': 'active',
    })
    assert res.status_code == 302
    assert db.session.get(Product, pid).qty == 10


def test_update_product_not_found(app_client):
    res = app_client.post('/products/9999', data={'name': 'x', 'sku': 'x', 'price': '1'})
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/products')


def test_update_product_missing_fields(app_client, seeded):
    pid = seeded['p1']
    res = app_client.post(f'/products/{pid}', data={'name': ''})
    assert res.status_code == 302
    assert f'/products/{pid}/edit' in res.headers['Location']


def test_update_product_duplicate_sku(app_client, seeded):
    res = app_client.post(f"/products/{seeded['p1']}", data={
        'name': 'Widget', 'sku': 'G-1', 'price': '10', 'status': 'active',
    })
    assert res.status_code == 302
    assert f"/products/{seeded['p1']}/edit" in res.headers['Location']
    assert db.session.get(Product, seeded['p1']).sku == 'W-1'


def test_update_product_invalid_number(app_client, seeded):
    res = app_client.post(f"/products/{seeded['p1']}", data={
        'name': 'Widget', 'sku': 'W-1', 'price': 'nope', 'status': 'active',
    })
    assert res.status_code == 302
    assert f"/products/{seeded['p1']}/edit" in res.headers['Location']


def test_delete_product_redirect(app_client, seeded):
    res = app_client.post(f"/products/{seeded['p2']}/delete")
    assert res.status_code == 302
    assert db.session.get(Product, seeded['p2']) is None


def test_delete_product_not_found(app_client):
    res = app_client.post('/products/9999/delete')
    assert res.status_code == 302


def test_delete_product_not_found_htmx(app_client):
    res = app_client.post('/products/9999/delete', headers=HX)
    assert res.status_code == 404


def test_delete_product_htmx_returns_table(app_client, seeded):
    res = app_client.post(
        f"/products/{seeded['p2']}/delete?search=widget&sort_by=name&sort_order=asc",
        headers=HX,
    )
    assert res.status_code == 200
    assert db.session.get(Product, seeded['p2']) is None


def test_delete_product_htmx_desc_sort(app_client, seeded):
    res = app_client.post(f"/products/{seeded['p3']}/delete?sort_by=id&sort_order=desc", headers=HX)
    assert res.status_code == 200


# ------------------------------ stock screens ------------------------------

def test_stock_history_and_filters(app_client, seeded):
    assert app_client.get('/stock').status_code == 200
    url = (f"/stock?type=entry&product_id={seeded['p1']}"
           "&date_from=2000-01-01&date_to=2100-01-01")
    assert app_client.get(url).status_code == 200


def test_stock_history_bad_dates_ignored(app_client, seeded):
    assert app_client.get('/stock?date_from=bad&date_to=worse').status_code == 200


def test_stock_history_htmx(app_client, seeded):
    assert app_client.get('/stock?type=entry', headers=HX).status_code == 200


def test_stock_update_form(app_client, seeded):
    assert app_client.get('/stock/update').status_code == 200
    assert app_client.get(f"/stock/update?product_id={seeded['p1']}").status_code == 200


def test_stock_update_form_htmx(app_client, seeded):
    res = app_client.get(f"/stock/update?product_id={seeded['p1']}", headers=HX)
    assert res.status_code == 200


def test_stock_update_entry(app_client, seeded):
    res = app_client.post('/stock/update', data={
        'product_id': seeded['p1'], 'type': 'entry', 'qty_change': '5', 'notes': 'n',
    })
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/stock')
    assert db.session.get(Product, seeded['p1']).qty == 55


def test_stock_update_exit(app_client, seeded):
    res = app_client.post('/stock/update', data={
        'product_id': seeded['p1'], 'type': 'exit', 'qty_change': '5',
    })
    assert res.status_code == 302
    assert db.session.get(Product, seeded['p1']).qty == 45


def test_stock_update_exit_insufficient(app_client, seeded):
    res = app_client.post('/stock/update', data={
        'product_id': seeded['p2'], 'type': 'exit', 'qty_change': '999',
    })
    assert res.status_code == 200
    assert db.session.get(Product, seeded['p2']).qty == 2


@pytest.mark.parametrize('data', [
    {'type': 'entry', 'qty_change': '5'},                       # no product
    {'product_id': 9999, 'type': 'entry', 'qty_change': '5'},   # unknown product
])
def test_stock_update_product_errors(app_client, seeded, data):
    assert app_client.post('/stock/update', data=data).status_code == 200


def test_stock_update_invalid_type(app_client, seeded):
    res = app_client.post('/stock/update', data={
        'product_id': seeded['p1'], 'type': 'weird', 'qty_change': '5',
    })
    assert res.status_code == 200
    assert db.session.get(Product, seeded['p1']).qty == 50


@pytest.mark.parametrize('qty', ['0', '-3', ''])
def test_stock_update_invalid_qty(app_client, seeded, qty):
    res = app_client.post('/stock/update', data={
        'product_id': seeded['p1'], 'type': 'entry', 'qty_change': qty,
    })
    assert res.status_code == 200
    assert db.session.get(Product, seeded['p1']).qty == 50


# ---------------------------- reports / audit ----------------------------

def test_reports_ui(app_client, seeded):
    assert app_client.get('/reports').status_code == 200


def test_audit_ui_and_filters(app_client, seeded):
    assert app_client.get('/audit').status_code == 200
    assert app_client.get('/audit?table=products&action=INSERT&record_id=1').status_code == 200


def test_audit_ui_htmx(app_client, seeded):
    assert app_client.get('/audit?table=products', headers=HX).status_code == 200


def test_health(app_client):
    res = app_client.get('/health')
    assert res.status_code == 200
    assert res.get_json()['status'] == 'healthy'


def test_health_db_failure(app_client):
    with patch('app.main.db.session.execute', side_effect=RuntimeError('db down')):
        res = app_client.get('/health')
    assert res.status_code == 500
    assert res.get_json()['status'] == 'unhealthy'


# ------------------------------- users UI -------------------------------

USER = {'id': 'u1', 'username': 'alice', 'email': 'a@x.com', 'firstName': 'A', 'lastName': 'L',
        'enabled': True}
ROLES = [{'name': 'group:employee'}, {'name': 'offline_access'}]


@patch('app.auth.keycloak_admin.get_user_realm_roles', return_value=ROLES)
@patch('app.auth.keycloak_admin.list_users', return_value=[USER])
def test_users_ui_lists(mock_list, mock_roles, app_client):
    res = app_client.get('/users')
    assert res.status_code == 200
    assert b'alice' in res.data


@patch('app.auth.keycloak_admin.list_users', side_effect=KeycloakAdminError('boom', 502))
def test_users_ui_keycloak_error(mock_list, app_client):
    assert app_client.get('/users').status_code == 200


def test_users_new_ui(app_client):
    assert app_client.get('/users/new').status_code == 200


def test_users_create_ui_missing_fields(app_client):
    res = app_client.post('/users', data={'username': 'x'})
    assert res.status_code == 302
    assert '/users/new' in res.headers['Location']


@patch('app.auth.keycloak_admin.get_user_realm_roles', return_value=ROLES)
@patch('app.auth.keycloak_admin.list_users', return_value=[USER])
@patch('app.auth.keycloak_admin.fetch_user_access_token',
       return_value={'access_token': 't', 'claims': {'roles': []}})
@patch('app.auth.keycloak_admin.create_user', return_value=USER)
def test_users_create_ui_ok(mock_create, mock_token, mock_list, mock_roles, app_client):
    res = app_client.post('/users', data={
        'username': 'alice', 'password': 'pw', 'email': 'a@x.com',
        'firstName': 'A', 'lastName': 'L', 'roles': ['group:employee'],
    })
    assert res.status_code == 200
    mock_create.assert_called_once()


@patch('app.auth.keycloak_admin.list_users', side_effect=KeycloakAdminError('x', 502))
@patch('app.auth.keycloak_admin.fetch_user_access_token',
       return_value={'access_token': 't', 'claims': {'roles': []}})
@patch('app.auth.keycloak_admin.create_user', return_value=USER)
def test_users_create_ui_list_fails_after_create(mock_create, mock_token, mock_list, app_client):
    res = app_client.post('/users', data={'username': 'alice', 'password': 'pw'})
    assert res.status_code == 200


@patch('app.auth.keycloak_admin.create_user', side_effect=KeycloakAdminError('exists', 409))
def test_users_create_ui_keycloak_error(mock_create, app_client):
    res = app_client.post('/users', data={'username': 'alice', 'password': 'pw'})
    assert res.status_code == 302
    assert '/users/new' in res.headers['Location']


@patch('app.auth.keycloak_admin.create_user', side_effect=RuntimeError('unexpected'))
def test_users_create_ui_unexpected_error(mock_create, app_client):
    res = app_client.post('/users', data={'username': 'alice', 'password': 'pw'})
    assert res.status_code == 302
    assert '/users/new' in res.headers['Location']


@patch('app.auth.keycloak_admin.get_user_realm_roles', return_value=ROLES)
@patch('app.auth.keycloak_admin.get_user', return_value=USER)
def test_users_detail_ui(mock_get, mock_roles, app_client):
    assert app_client.get('/users/u1').status_code == 200


@patch('app.auth.keycloak_admin.get_user', side_effect=KeycloakAdminError('nf', 404))
def test_users_detail_ui_not_found(mock_get, app_client):
    res = app_client.get('/users/nope')
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/users')


@patch('app.auth.keycloak_admin.set_user_roles', return_value=['group:employee'])
def test_users_roles_ui_ok(mock_set, app_client):
    res = app_client.post('/users/u1/roles', data={'roles': ['group:employee']})
    assert res.status_code == 302
    mock_set.assert_called_once_with('u1', ['group:employee'])


@patch('app.auth.keycloak_admin.set_user_roles', side_effect=KeycloakAdminError('bad', 400))
def test_users_roles_ui_error(mock_set, app_client):
    res = app_client.post('/users/u1/roles', data={'roles': ['nope']})
    assert res.status_code == 302


def test_users_token_ui_requires_password(app_client):
    res = app_client.post('/users/u1/token', data={})
    assert res.status_code == 302


@patch('app.auth.keycloak_admin.get_user_realm_roles', return_value=ROLES)
@patch('app.auth.keycloak_admin.fetch_user_access_token',
       return_value={'access_token': 't', 'claims': {'roles': []}})
@patch('app.auth.keycloak_admin.get_user', return_value=USER)
def test_users_token_ui_ok(mock_get, mock_token, mock_roles, app_client):
    res = app_client.post('/users/u1/token', data={'password': 'pw'})
    assert res.status_code == 200
    mock_token.assert_called_once_with('alice', 'pw')


@patch('app.auth.keycloak_admin.fetch_user_access_token',
       side_effect=KeycloakAdminError('bad pw', 400))
@patch('app.auth.keycloak_admin.get_user', return_value=USER)
def test_users_token_ui_error(mock_get, mock_token, app_client):
    res = app_client.post('/users/u1/token', data={'password': 'wrong'})
    assert res.status_code == 302
