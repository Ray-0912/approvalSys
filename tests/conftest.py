import os
import pytest
from main import app


@pytest.fixture(scope='session')
def app_client():
    app.config.update(TESTING=True, SECRET_KEY='test-secret')
    with app.test_client() as client:
        yield client


@pytest.fixture()
def authenticated_client(app_client):
    with app_client.session_transaction() as session_data:
        session_data['logged_in'] = True
        session_data['username'] = 'tester'
        session_data['user_id'] = 2
        session_data['team_id'] = 1
        session_data['role_id'] = 3
        session_data['clock_id'] = '123'
        session_data['_csrf_token'] = 'token-test-app-001'
    yield app_client
