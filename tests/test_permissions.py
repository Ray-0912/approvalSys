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
        session_data['role_id'] = 99

    monkeypatch.setattr(db, 'get_all_users_admin', lambda: [
        {
            'user_id': 1,
            'username': 'alice',
            'first_name': 'Alice',
            'last_name': 'Chen',
            'role_name': 'Director',
            'role_id': 1,
            'team_name': 'Management',
            'team_id': 1,
            'activation': 1,
            'email': 'alice@example.com',
        },
        {
            'user_id': 2,
            'username': 'bob',
            'first_name': 'Bob',
            'last_name': 'Lin',
            'role_name': 'Manager',
            'role_id': 2,
            'team_name': 'Accounting',
            'team_id': 2,
            'activation': 1,
            'email': 'bob@example.com',
        },
    ])
    monkeypatch.setattr(db, 'get_teams', lambda: [])
    monkeypatch.setattr(db, 'get_roles', lambda: [])

    response = client.get('/sys/users?q=alice&page_size=10')
    assert response.status_code == 200
    assert b'alice@example.com' in response.data
    assert b'bob@example.com' not in response.data


def test_sys_users_filters_team_role_and_activation(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data['role_id'] = 99
    users = [
        {'user_id': 2, 'username': 'active-manager', 'first_name': 'A', 'last_name': 'A', 'email': '', 'role_id': 2, 'role_name': 'Manager', 'team_id': 1, 'team_name': 'Front', 'activation': 1},
        {'user_id': 3, 'username': 'inactive-staff', 'first_name': 'B', 'last_name': 'B', 'email': '', 'role_id': 3, 'role_name': 'Staff', 'team_id': 2, 'team_name': 'HR', 'activation': 0},
    ]
    monkeypatch.setattr(db, 'get_all_users_admin', lambda: users)
    monkeypatch.setattr(db, 'get_teams', lambda: [])
    monkeypatch.setattr(db, 'get_roles', lambda: [])
    response = client.get('/sys/users?team_id=2&role_id=3&activation=0')
    assert b'inactive-staff' in response.data
    assert b'active-manager' not in response.data


def test_sys_users_includes_action_script_and_translates_deactivate(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data.update({'role_id': 99, 'locale': 'zh_TW'})
    monkeypatch.setattr(db, 'get_all_users_admin', lambda: [{
        'user_id': 2, 'username': 'staff', 'first_name': 'A', 'last_name': 'B',
        'email': '', 'role_id': 3, 'role_name': 'Staff', 'team_id': 1,
        'team_name': 'Front', 'activation': 1,
    }])
    monkeypatch.setattr(db, 'get_teams', lambda: [])
    monkeypatch.setattr(db, 'get_roles', lambda: [])
    response = client.get('/sys/users')
    assert response.status_code == 200
    assert '停用'.encode('utf-8') in response.data
    assert b"$('.user-action').on('click'" in response.data
    assert b'userActionModal' in response.data
    assert b"typeof $.fn.DataTable === 'function'" in response.data


def test_sys_users_defaults_to_100_and_only_offers_50_or_100(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data['role_id'] = 99
    monkeypatch.setattr(db, 'get_all_users_admin', lambda: [])
    monkeypatch.setattr(db, 'get_teams', lambda: [])
    monkeypatch.setattr(db, 'get_roles', lambda: [])

    response = client.get('/sys/users')

    assert response.status_code == 200
    assert b'<option value="100" selected>100</option>' in response.data
    assert b'<option value="50"' in response.data
    assert b'<option value="10"' not in response.data
    assert b'<option value="20"' not in response.data


def test_sys_users_defaults_to_active_and_has_no_delete_actions(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data['role_id'] = 99
    monkeypatch.setattr(db, 'get_all_users_admin', lambda: [
        {'user_id': 2, 'username': 'active-user', 'first_name': 'A', 'last_name': 'A', 'email': '', 'role_id': 3, 'role_name': 'Staff', 'team_id': 1, 'team_name': 'Front', 'activation': 1},
        {'user_id': 3, 'username': 'inactive-user', 'first_name': 'B', 'last_name': 'B', 'email': '', 'role_id': 3, 'role_name': 'Staff', 'team_id': 1, 'team_name': 'Front', 'activation': 0},
    ])
    monkeypatch.setattr(db, 'get_teams', lambda: [])
    monkeypatch.setattr(db, 'get_roles', lambda: [])

    response = client.get('/sys/users')

    assert b'active-user' in response.data
    assert b'inactive-user' not in response.data
    assert b'data-action="delete"' not in response.data
    assert b'id="batchDeleteBtn"' not in response.data


def test_sys_users_backend_rejects_delete_action(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data.update({'role_id': 99, 'user_id': 1, '_csrf_token': 'batch-token'})
    monkeypatch.setattr(db, 'get_users_by_ids', lambda ids: pytest.fail('must not query users'))

    response = client.post('/sys/users/action', data={
        'csrf_token': 'batch-token', 'action': 'delete', 'user_ids': ['2']
    })

    assert response.status_code == 302


def test_sys_users_batch_deactivate(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data.update({'role_id': 99, 'user_id': 1, '_csrf_token': 'batch-token'})
    monkeypatch.setattr(db, 'get_users_by_ids', lambda ids: [{'user_id': 2, 'username': 'staff', 'role_id': 3, 'team_id': 1, 'activation': 1}])
    called = []
    monkeypatch.setattr(db, 'set_users_activation', lambda ids, activation: called.append((ids, activation)) or len(ids))
    monkeypatch.setattr(db, 'append_audit_log', lambda **kwargs: 1)
    response = client.post('/sys/users/action', data={'csrf_token': 'batch-token', 'action': 'deactivate', 'user_ids': ['2']})
    assert response.status_code == 302
    assert called == [([2], 0)]


def test_sys_users_action_cannot_target_current_user(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data.update({'role_id': 99, 'user_id': 1, '_csrf_token': 'batch-token'})
    monkeypatch.setattr(db, 'set_users_activation', lambda *args: pytest.fail('must not be called'))
    response = client.post('/sys/users/action', data={'csrf_token': 'batch-token', 'action': 'deactivate', 'user_ids': ['1']})
    assert response.status_code == 302


def test_verify_password_only_accepts_active_users(monkeypatch):
    executed = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, query, params): executed.append((query, params))
        def fetchone(self): return None

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return Cursor()

    monkeypatch.setattr(db, 'get_db_connection', lambda: Connection())
    assert db.verify_password('disabled-user', 'password') is None
    assert 'activation = 1' in executed[0][0]


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


def test_permissions_page_requires_role_99(client):
    response = client.get('/sys/permissions')
    assert response.status_code == 403


def test_permissions_detail_page_allows_role_99(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data['role_id'] = 99

    monkeypatch.setattr(db, 'get_roles_simple', lambda: [{'role_id': 99, 'name': 'SysSupervisor'}])
    monkeypatch.setattr(db, 'get_role_permissions_map', lambda: {})
    monkeypatch.setattr(permission_module, 'get_effective_role_permission', lambda role_id, permission_key: True)

    response = client.get('/sys/permissions/99')
    assert response.status_code == 200
    assert b'\xe8\xa7\x92\xe8\x89\xb2\xe6\xac\x8a\xe9\x99\x90' in response.data
