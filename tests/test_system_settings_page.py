import pytest

from main import app


@pytest.fixture()
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        with test_client.session_transaction() as session_data:
            session_data['logged_in'] = True
            session_data['username'] = 'sys'
            session_data['user_id'] = 1
            session_data['team_id'] = 0
            session_data['role_id'] = 99
            session_data['clock_id'] = '1001'
            session_data['_csrf_token'] = 'token-system-001'
        yield test_client


def test_system_settings_links_to_user_list(client):
    response = client.get('/sys/settings')
    assert response.status_code == 200
    assert b'/sys/users' in response.data
