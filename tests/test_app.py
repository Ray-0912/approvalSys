import unittest
import os
from unittest.mock import patch
from main import app, calculate_front_desk_currency_rate, handle_unexpected_error
import database.queries as db_queries

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
        self.assertIn(b'6.0.0', rv.data)

    def test_homepage_title_uses_zh_tw_translation(self):
        with self.client.session_transaction() as session_data:
            session_data['locale'] = 'zh_TW'

        rv = self.client.get('/', follow_redirects=True)
        self.assertEqual(rv.status_code, 200)
        data = rv.get_data(as_text=True)
        self.assertIn('首頁', data)
        self.assertIn('我的資料', data)
        self.assertIn('簽呈區', data)
        self.assertIn('歡迎回來', data)

    def test_clock_record_page_uses_zh_tw_translation(self):
        with self.client.session_transaction() as session_data:
            session_data['locale'] = 'zh_TW'

        rv = self.client.get('/hr/clockRecord', follow_redirects=True)
        self.assertEqual(rv.status_code, 200)
        data = rv.get_data(as_text=True)
        rendered_bytes = rv.get_data()
        self.assertIn('打卡記錄查詢'.encode('utf-8'), rendered_bytes)
        self.assertIn('出勤時間'.encode('utf-8'), rendered_bytes)

    def test_unhandled_error_renders_error_message(self):
        with app.test_request_context('/__test_error__', method='GET'):
            response = handle_unexpected_error(RuntimeError('simulated failure details'))
        self.assertEqual(response[1], 500)
        payload = response[0]
        if hasattr(payload, 'data'):
            raw = payload.get_data()
        else:
            raw = payload
        if isinstance(raw, str):
            raw = raw.encode('utf-8')
        self.assertIn(b'simulated failure details', raw)

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

    def test_salary_profile_columns_are_schema_aware(self):
        with patch('database.queries._column_exists', side_effect=lambda table, column: column in {'weekday_hourly_rate', 'holiday_hourly_rate'}):
            columns = db_queries._salary_profile_select_columns()
        self.assertIn('p.weekday_hourly_rate', columns)
        self.assertIn('p.holiday_hourly_rate', columns)
        self.assertNotIn('p.professional_allowance', columns)

if __name__ == '__main__':
    unittest.main()

