import pytest

import main


@pytest.fixture()
def client():
    main.app.config['TESTING'] = True
    with main.app.test_client() as test_client:
        with test_client.session_transaction() as session_data:
            session_data['logged_in'] = True
            session_data['username'] = 'tester'
            session_data['user_id'] = 2
            session_data['team_id'] = 1
            session_data['role_id'] = 3
            session_data['clock_id'] = '123'
            session_data['_csrf_token'] = 'token-att-001'
        yield test_client


def test_clock_record_post_uses_shift_window_and_cross_midnight(client, monkeypatch):
    monkeypatch.setattr(main.client, 'get_att_logs', lambda pin, start_date, end_date: {
        'result': {
            'items': [
                {'attLogTime': '2026-08-01T23:00:00'},
                {'attLogTime': '2026-08-02T07:10:00'},
            ]
        }
    })
    monkeypatch.setattr(main.client, 'get_employee_info', lambda pin: None)
    monkeypatch.setattr(main.db, 'get_user_by_clock_id', lambda pin: {
        'user_id': 2,
        'first_name': 'Test',
        'last_name': 'User'
    })
    monkeypatch.setattr(main.db, 'get_user_schedule_by_date', lambda user_id, date: {
        'shift_name': 'Night',
        'start_time': '22:00:00',
        'end_time': '08:00:00',
        'color': '#000000'
    })

    response = client.post('/hr/clockRecordPost', json={
        'csrf_token': 'token-att-001',
        'Start': '2026-08-01 00:00:00',
        'End': '2026-08-02 23:59:59'
    })

    assert response.status_code == 200
    payload = response.get_json()
    summary = payload['result']['items']['summary']
    assert len(summary) == 1
    assert summary[0]['status'] == 'Late / Early Leave'
    assert summary[0]['date'] == '2026-08-01'
