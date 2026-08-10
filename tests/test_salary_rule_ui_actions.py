import pytest

from main import app
import main


@pytest.fixture()
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        with test_client.session_transaction() as session_data:
            session_data['logged_in'] = True
            session_data['username'] = 'finance'
            session_data['user_id'] = 1
            session_data['team_id'] = 0
            session_data['role_id'] = 99
            session_data['clock_id'] = '1001'
            session_data['_csrf_token'] = 'token-salary-ui-001'
        yield test_client


def test_salary_ma_delete_holiday(client, monkeypatch):
    called = {'deleted': False}

    monkeypatch.setattr(main.db, 'delete_holiday', lambda holiday_date, country_code='TW': called.__setitem__('deleted', True) or True)
    monkeypatch.setattr(main, 'write_audit', lambda *args, **kwargs: None)

    response = client.post('/hr/salary/ma', data={
        'csrf_token': 'token-salary-ui-001',
        'action': 'delete_holiday',
        'holiday_date': '2026-10-10'
    })

    assert response.status_code == 302
    assert called['deleted'] is True
