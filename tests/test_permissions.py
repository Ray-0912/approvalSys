import pytest

from blueprints import approval as approval_blueprint
from main import app
import database.queries as db
import functions.permission as permission_module


@pytest.fixture()
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        with test_client.session_transaction() as session_data:
            session_data['logged_in'] = True
            session_data['username'] = 'tester'
            session_data['user_id'] = 2
            session_data['team_id'] = 1
            session_data['role_id'] = 3
            session_data['clock_id'] = '123'
        yield test_client


def test_p_routes_require_permission(client):
    response = client.get('/p/list')
    assert response.status_code == 403


def test_hr_routes_require_manager(client):
    response = client.get('/hr/new')
    assert response.status_code == 403


def test_sys_routes_require_admin(client):
    with client.session_transaction() as session_data:
        session_data['_csrf_token'] = 'token-123'

    response = client.post('/sys/user/save', data={
        'csrf_token': 'token-123',
        'user_id': '2',
        'first_name': 'A',
        'last_name': 'B',
        'email': 'a@example.com',
        'phone': '123',
        'role_id': '3',
        'team_id': '1'
    })
    assert response.status_code == 403


def test_audit_logs_page_requires_admin(client):
    response = client.get('/sys/audit-logs')
    assert response.status_code == 403


def test_sys_users_supports_search_and_paging(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data['role_id'] = 0

    monkeypatch.setattr(db, 'get_all_users_admin', lambda: [
        {
            'user_id': 1,
            'username': 'alice',
            'first_name': 'Alice',
            'last_name': 'Chen',
            'role_name': 'Director',
            'team_name': 'Management',
            'email': 'alice@example.com',
        },
        {
            'user_id': 2,
            'username': 'bob',
            'first_name': 'Bob',
            'last_name': 'Lin',
            'role_name': 'Manager',
            'team_name': 'Accounting',
            'email': 'bob@example.com',
        },
    ])

    response = client.get('/sys/users?q=alice&page_size=10')
    assert response.status_code == 200
    assert b'alice@example.com' in response.data
    assert b'bob@example.com' not in response.data


def test_approval_requires_sequential_order(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data['role_id'] = 0
        session_data['_csrf_token'] = 'token-seq-001'

    monkeypatch.setattr(approval_blueprint, 'has_permission', lambda *args, **kwargs: True)
    monkeypatch.setattr(db, 'get_next_pending_approver', lambda doc_id: {
        'user_id': 99,
        'username': 'next_user',
        'first_name': 'Next',
        'last_name': 'User',
        'doc_ap_id': 1,
    })
    monkeypatch.setattr(db, 'update_doc_app', lambda *args, **kwargs: True)
    monkeypatch.setattr(db, 'update_doc_status', lambda *args, **kwargs: True)

    response = client.post('/p/approve', data={
        'csrf_token': 'token-seq-001',
        'doc_id': '1'
    })

    assert response.status_code == 302
    assert '/p/view/1' in response.headers['Location']


def test_csrf_validation_blocks_missing_token(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data['role_id'] = 0

    monkeypatch.setattr(db, 'update_doc_app', lambda *args, **kwargs: True)
    monkeypatch.setattr(db, 'update_doc_status', lambda *args, **kwargs: True)
    monkeypatch.setattr(approval_blueprint, 'has_permission', lambda *args, **kwargs: True)

    response = client.post('/p/approve', data={'doc_id': '1'})
    assert response.status_code == 400
    assert b'CSRF token invalid or missing' in response.data


def test_effective_permissions_use_defaults_when_no_override_exists(monkeypatch):
    monkeypatch.setattr(permission_module, '_load_db_override_permissions', lambda role_id: None)

    assert permission_module.get_effective_role_permission(3, 'p_view') is True
    assert permission_module.get_effective_role_permission(3, 'p_list') is False


def test_effective_permissions_use_explicit_overrides(monkeypatch):
    monkeypatch.setattr(permission_module, '_load_db_override_permissions', lambda role_id: {'p_list': True})

    assert permission_module.get_effective_role_permission(3, 'p_list') is True
    assert permission_module.get_effective_role_permission(3, 'p_view') is True
