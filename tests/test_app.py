import pytest
import os
from main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_secret_key_loaded():
    assert app.secret_key is not None
    assert app.secret_key != 'default-dev-key' # Should be loaded from env or default specific value if env missing but here we test availability

def test_homepage(client):
    rv = client.get('/')
    assert rv.status_code == 200

def test_login_page_renders(client):
    rv = client.get('/login')
    assert rv.status_code == 200
