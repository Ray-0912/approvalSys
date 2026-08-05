import unittest
import os
from main import app, calculate_front_desk_currency_rate

class TestApp(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        with self.client.session_transaction() as session_data:
            session_data['logged_in'] = True
            session_data['username'] = 'tester'
            session_data['user_id'] = 2
            session_data['team_id'] = 1
            session_data['role_id'] = 3
            session_data['clock_id'] = '123'
            session_data['_csrf_token'] = 'token-test-app-001'

    def test_secret_key_loaded(self):
        self.assertIsNotNone(app.secret_key)
        self.assertNotEqual(app.secret_key, 'default-dev-key')

    def test_homepage(self):
        rv = self.client.get('/', follow_redirects=True)
        self.assertEqual(rv.status_code, 200)

    def test_login_page_renders(self):
        rv = self.client.get('/login')
        self.assertEqual(rv.status_code, 200)

    def test_w_menu_renders(self):
        rv = self.client.get('/w_menu')
        self.assertEqual(rv.status_code, 200)
        self.assertIn(b'USD', rv.data)
        self.assertIn(b'JPY', rv.data)

    def test_front_desk_rate_uses_buying_rate_with_spread(self):
        class DummyCurrency:
            def __init__(self, bank_buying_rate, bank_selling_rate):
                self.bank_buying_rate = bank_buying_rate
                self.bank_selling_rate = bank_selling_rate

        currency = DummyCurrency('33.6', '34.1')
        self.assertEqual(calculate_front_desk_currency_rate(currency, 'USD'), 32.6)

if __name__ == '__main__':
    unittest.main()

