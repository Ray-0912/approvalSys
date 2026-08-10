from datetime import date

import pytest

import main


@pytest.fixture()
def client(monkeypatch):
    main.app.config['TESTING'] = True
    monkeypatch.setattr(main, 'date', type('FixedDate', (date,), {
        'today': classmethod(lambda cls: cls(2026, 8, 10))
    }))
    with main.app.test_client() as test_client:
        with test_client.session_transaction() as session_data:
            session_data.update({
                'logged_in': True, 'username': 'tester', 'user_id': 2,
                'team_id': 1, 'role_id': 3, '_csrf_token': 'token-off-001'
            })
        yield test_client


@pytest.mark.parametrize('requested_date', ['2026-07-15', '2026-10-01', '2025-09-15', '2027-09-15'])
def test_off_request_rejects_dates_outside_next_month(client, requested_date, monkeypatch):
    monkeypatch.setattr(main.db, 'upsert_off_request', lambda *args: pytest.fail('must not save'))
    response = client.post('/hr/schedule/off-request/save', json={
        'csrf_token': 'token-off-001', 'action': 'add', 'date': requested_date
    })
    assert response.status_code == 400


def test_off_request_accepts_date_in_next_month(client, monkeypatch):
    saved = []
    monkeypatch.setattr(main.db, 'upsert_off_request', lambda *args: saved.append(args))
    monkeypatch.setattr(main.db, 'get_off_requests_by_dates', lambda dates: [])
    response = client.post('/hr/schedule/off-request/save', json={
        'csrf_token': 'token-off-001', 'action': 'add', 'date': '2026-09-15'
    })
    assert response.status_code == 200
    assert saved
