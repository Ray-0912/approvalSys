import unittest
import os
from main import app

class TestApp(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_secret_key_loaded(self):
        self.assertIsNotNone(app.secret_key)
        self.assertNotEqual(app.secret_key, 'default-dev-key')

    def test_homepage(self):
        rv = self.client.get('/')
        self.assertEqual(rv.status_code, 200)

    def test_login_page_renders(self):
        rv = self.client.get('/login')
        self.assertEqual(rv.status_code, 200)

    def test_w_menu_renders(self):
        rv = self.client.get('/w_menu')
        self.assertEqual(rv.status_code, 200)
        self.assertIn(b'USD', rv.data)
        self.assertIn(b'JPY', rv.data)

if __name__ == '__main__':
    unittest.main()

