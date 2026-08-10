import pytest

from config import BaseConfig
from main import app


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


def test_login_page_is_public(client):
    response = client.get('/login')
    assert response.status_code == 200


def test_development_config_uses_stable_secret_when_env_missing(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setenv('APP_ENV', 'development')

    config = BaseConfig()

    assert config.SECRET_KEY == 'approvalsys-dev-secret'


def test_login_post_allows_public_access_without_csrf_token(client, monkeypatch):
    monkeypatch.setattr('database.queries.check_existing_username', lambda username: True)
    monkeypatch.setattr('database.queries.verify_password', lambda username, password: (1, 'tester', None, 3, 1, '', '', 'Test', 'User', '123'))

    response = client.post('/login', data={
        'username': 'tester',
        'password': 'Password123'
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b'Welcome Back!' not in response.data


def test_login_sets_dedicated_session_cookie(monkeypatch):
    monkeypatch.setattr('database.queries.check_existing_username', lambda username: True)
    monkeypatch.setattr('database.queries.verify_password', lambda username, password: (1, 'tester', None, 3, 1, '', '', 'Test', 'User', '123'))

    test_client = app.test_client()
    response = test_client.post('/login', data={
        'username': 'tester',
        'password': 'Password123'
    }, follow_redirects=False)

    session_cookies = [
        header for header in response.headers.getlist('Set-Cookie')
        if header.startswith('approvalsys_session=')
    ]
    assert len(session_cookies) == 1


def test_login_session_cookie_contains_flask_session_not_csrf_token(monkeypatch):
    monkeypatch.setattr('database.queries.check_existing_username', lambda username: True)
    monkeypatch.setattr('database.queries.verify_password', lambda username, password: (1, 'tester', None, 3, 1, '', '', 'Test', 'User', '123'))

    test_client = app.test_client()
    response = test_client.post('/login', data={
        'username': 'tester',
        'password': 'Password123'
    }, follow_redirects=False)

    session_cookies = [
        header for header in response.headers.getlist('Set-Cookie')
        if header.startswith('approvalsys_session=')
    ]
    assert len(session_cookies) == 1
    with test_client.session_transaction() as session_data:
        assert session_data['user_id'] == 1


def test_register_requires_admin(client):
    with client.session_transaction() as session_data:
        session_data['_csrf_token'] = 'token-123'

    response = client.post('/register', data={
        'csrf_token': 'token-123',
        'username': 'new_user',
        'password': 'Password123',
        'firstname': 'A',
        'lastname': 'B',
        'role': '3',
        'team': '1',
        'email': 'a@example.com',
        'phone': '123'
    })
    assert response.status_code == 403


def test_hr_schedule_save_requires_manager(client):
    with client.session_transaction() as session_data:
        session_data['_csrf_token'] = 'token-456'

    response = client.post('/hr/schedule/save', json={
        'csrf_token': 'token-456',
        'user_id': '2',
        'date': '2026-08-01',
        'shift_type_id': '1'
    })
    assert response.status_code == 403
