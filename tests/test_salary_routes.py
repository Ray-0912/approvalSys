import pytest

import main


@pytest.fixture()
def client():
    main.app.config['TESTING'] = True
    with main.app.test_client() as test_client:
        with test_client.session_transaction() as session_data:
            session_data['logged_in'] = True
            session_data['username'] = 'finance'
            session_data['user_id'] = 1
            session_data['team_id'] = 0
            session_data['role_id'] = 99
            session_data['clock_id'] = '1001'
            session_data['_csrf_token'] = 'token-salary-001'
        yield test_client


def test_salary_rule_create_rejects_invalid_date(client, monkeypatch):
    called = {'create': False}

    def fake_create_salary_rule_version(**kwargs):
        called['create'] = True
        return 1

    monkeypatch.setattr(main.db, 'create_salary_rule_version', fake_create_salary_rule_version)

    response = client.post('/hr/salary/ma', data={
        'csrf_token': 'token-salary-001',
        'action': 'create_rule',
        'version_name': 'v1',
        'effective_from': '2026/08/01'
    })

    assert response.status_code == 302
    assert called['create'] is False


def test_salary_calculate_handles_empty_profiles(client, monkeypatch):
    monkeypatch.setattr(main.db, 'get_active_salary_rule', lambda year_month=None: {
        'id': 1,
        'version_name': 'default',
        'effective_from': '2026-08-01',
        'overtime_monthly_multiplier': 1.33,
        'overtime_hourly_multiplier': 1.5,
        'holiday_multiplier': 2.0,
        'grace_late_minutes': 5,
        'grace_early_minutes': 5,
        'regular_hours_staff': 8.5,
        'regular_hours_manager': 9.0,
    })
    monkeypatch.setattr(main.db, 'get_salary_profiles', lambda: [])
    monkeypatch.setattr(main.db, 'get_holidays_by_month', lambda year_month: [])
    monkeypatch.setattr(main.db, 'get_salary_results', lambda *args, **kwargs: [])

    response = client.post('/hr/salary/cal', data={
        'csrf_token': 'token-salary-001',
        'action': 'calculate',
        'year_month': '2026-08'
    })

    assert response.status_code == 302


def test_salary_profile_upsert_rejects_bad_user_id(client, monkeypatch):
    called = {'upsert': False}

    def fake_upsert_salary_profile(*args, **kwargs):
        called['upsert'] = True
        return True

    monkeypatch.setattr(main.db, 'get_active_salary_rule', lambda year_month=None: None)
    monkeypatch.setattr(main.db, 'get_salary_profiles', lambda: [])
    monkeypatch.setattr(main.db, 'get_holidays_by_month', lambda year_month: [])
    monkeypatch.setattr(main.db, 'upsert_salary_profile', fake_upsert_salary_profile)

    response = client.post('/hr/salary/ma', data={
        'csrf_token': 'token-salary-001',
        'action': 'upsert_profile',
        'user_id': 'abc',
        'salary_type': 'monthly',
        'monthly_salary': '50000',
        'hourly_salary': ''
    })

    assert response.status_code == 302
    assert called['upsert'] is False
