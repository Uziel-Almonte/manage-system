"""Unit tests for user admin API (Keycloak Admin mocked)."""
from unittest.mock import patch


@patch('app.users.views.get_user_realm_roles', return_value=[{'name': 'group:manager'}])
@patch('app.users.views.list_users')
def test_list_users_ok(mock_list, mock_roles, app_client):
    mock_list.return_value = [
        {
            'id': 'u1',
            'username': 'kratos_boss',
            'email': 'k@x.com',
            'firstName': 'Kratos',
            'lastName': 'Boss',
            'enabled': True,
        }
    ]
    res = app_client.get('/api/users')
    assert res.status_code == 200
    body = res.get_json()
    assert body['data'][0]['username'] == 'kratos_boss'
    assert 'group:manager' in body['data'][0]['roles']
    assert 'user:manage' in body['manageable_roles']


@patch('app.users.views.fetch_user_access_token')
@patch('app.users.views.get_user_realm_roles', return_value=[{'name': 'group:employee'}])
@patch('app.users.views.create_user')
def test_create_user_issues_token(mock_create, mock_roles, mock_token, app_client):
    mock_create.return_value = {
        'id': 'u2',
        'username': 'newbie',
        'email': 'n@x.com',
        'firstName': 'New',
        'lastName': 'Bie',
        'enabled': True,
    }
    mock_token.return_value = {
        'access_token': 'tok',
        'expires_in': 300,
        'claims': {'exp_iso': '2026-01-01T00:00:00+00:00', 'roles': ['group:employee']},
    }
    res = app_client.post('/api/users', json={
        'username': 'newbie',
        'password': 'password123',
        'email': 'n@x.com',
        'firstName': 'New',
        'lastName': 'Bie',
        'roles': ['group:employee'],
        'issue_token': True,
    })
    assert res.status_code == 201
    body = res.get_json()
    assert body['user']['username'] == 'newbie'
    assert body['token']['access_token'] == 'tok'
    mock_create.assert_called_once()
    mock_token.assert_called_once_with('newbie', 'password123')
    assert 'issue_token' not in (mock_create.call_args.kwargs or {})


@patch('app.users.views.set_user_roles', return_value=['product:view', 'stock:view'])
@patch('app.users.views.get_user')
def test_set_roles(mock_get, mock_set, app_client):
    mock_get.return_value = {
        'id': 'u1',
        'username': 'alice_worker',
        'email': 'a@x.com',
        'firstName': 'Alice',
        'lastName': 'Worker',
        'enabled': True,
    }
    res = app_client.put('/api/users/u1/roles', json={'roles': ['product:view', 'stock:view']})
    assert res.status_code == 200
    assert res.get_json()['roles'] == ['product:view', 'stock:view']
    mock_set.assert_called_once_with('u1', ['product:view', 'stock:view'])
