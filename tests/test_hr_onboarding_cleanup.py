import pytest

import main


@pytest.fixture()
def client():
    main.app.config['TESTING'] = True
    with main.app.test_client() as test_client:
        with test_client.session_transaction() as session_data:
            session_data['logged_in'] = True
            session_data['username'] = 'admin'
            session_data['user_id'] = 1
            session_data['team_id'] = 0
            session_data['role_id'] = 0
            session_data['clock_id'] = '1001'
        yield test_client


def test_hr_onboarding_compensates_biolife_failure(client, monkeypatch):
    with client.session_transaction() as session_data:
        session_data['_csrf_token'] = 'token-hr-001'

    monkeypatch.setattr(main.hr, 'check_organization_id', lambda org, dep: 8)
    monkeypatch.setattr(main.hr, 'check_team_id', lambda org_id: 1)
    monkeypatch.setattr(main.client, 'get_latest_person_pin', lambda organization_unit_id: '9001')
    monkeypatch.setattr(main.db, 'check_existing_username', lambda username: False)
    monkeypatch.setattr(main.hr, 'hr_new_person_result', lambda **kwargs: 1)

    imported = {'called': False}

    def fake_import_user(**kwargs):
        imported['called'] = True
        return False

    leave_calls = []

    monkeypatch.setattr(main.db, 'import_user', fake_import_user)
    monkeypatch.setattr(main.client, 'leave_person', lambda pins: leave_calls.append(pins))

    response = client.post('/hr/new', data={
        'csrf_token': 'token-hr-001',
        'organization': 'HQ',
        'department': 'Ops',
        'ssn': 'A123456789',
        'first_name': 'A',
        'last_name': 'B',
        'e_mail': 'ab@example.com',
        'phone': '123'
    })

    assert response.status_code == 302
    assert imported['called'] is True
    assert leave_calls == ['9001']