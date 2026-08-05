import pytest

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