from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.styles import PatternFill

import database.queries as queries
import main
import migrations.runner as runner


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


def test_salary_day_rate_override_helpers_return_empty_when_table_missing(monkeypatch):
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            raise RuntimeError('missing table')

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self, *args, **kwargs):
            return FakeCursor()

        def commit(self):
            pass

    def fake_get_db_connection():
        return FakeConnection()

    monkeypatch.setattr(queries, 'get_db_connection', fake_get_db_connection)

    assert queries.get_salary_day_rate_overrides(1, '2026-08-01', '2026-08-31') == []
    assert queries.upsert_salary_day_rate_override(1, '2026-08-01', 220, 7) is True


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


def test_build_salary_result_uses_weekday_and_holiday_rates(monkeypatch):
    profile = {
        'user_id': 7,
        'clock_id': '2002',
        'role_id': 3,
        'salary_type': 'hourly',
        'hourly_salary': None,
        'monthly_salary': None,
        'weekday_hourly_rate': 200,
        'holiday_hourly_rate': 300,
        'professional_allowance': 1000,
        'position_allowance': 500,
        'base_salary_amount': 0,
        'sales_allowance': 0,
        'overtime_allowance': 0,
        'night_shift_allowance': 0,
        'special_leave_allowance': 0,
    }
    rule = {
        'regular_hours_staff': 8.5,
        'regular_hours_manager': 9.0,
        'grace_late_minutes': 5,
        'grace_early_minutes': 5,
        'overtime_hourly_multiplier': 1.5,
        'overtime_monthly_multiplier': 1.33,
        'holiday_multiplier': 2.0,
        'default_hourly_rate': 200,
    }
    monkeypatch.setattr(main.client, 'get_att_logs', lambda *args, **kwargs: {'result': {'items': []}})
    monkeypatch.setattr(main.db, 'get_user_schedules_in_range', lambda *args, **kwargs: {})
    monkeypatch.setattr(main.db, 'get_salary_day_rate_overrides', lambda *args, **kwargs: [])
    monkeypatch.setattr(main, 'smart_group_punches', lambda parsed: {
        date(2026, 8, 3): [datetime(2026, 8, 3, 9, 0), datetime(2026, 8, 3, 17, 0)],
        date(2026, 8, 1): [datetime(2026, 8, 1, 9, 0), datetime(2026, 8, 1, 17, 0)],
    })
    monkeypatch.setattr(main, 'parse_att_dt', lambda value: datetime.fromisoformat(value))

    result = main.build_salary_result_for_user(profile, '2026-08', rule, {date(2026, 8, 1)})

    assert result['regular_minutes'] == 480
    assert result['holiday_minutes'] == 480
    assert result['gross_salary'] == pytest.approx(1000 + 500 + 200 * 8 + 300 * 8 * 2)  # fixed + weekday + holiday double-pay


def test_salary_detail_fetches_biolife_attendance_once(monkeypatch):
    profile = {
        'user_id': 7, 'clock_id': '2002', 'role_id': 3, 'salary_type': 'hourly',
        'hourly_salary': 200, 'monthly_salary': None,
        'weekday_hourly_rate': 200, 'holiday_hourly_rate': 300,
        'professional_allowance': 0, 'position_allowance': 0, 'base_salary_amount': 0,
        'sales_allowance': 0, 'overtime_allowance': 0,
        'night_shift_allowance': 0, 'special_leave_allowance': 0,
    }
    rule = {
        'regular_hours_staff': 8.5, 'regular_hours_manager': 9.0,
        'grace_late_minutes': 5, 'grace_early_minutes': 5,
        'overtime_hourly_multiplier': 1.5, 'overtime_monthly_multiplier': 1.33,
        'holiday_multiplier': 2.0, 'default_hourly_rate': 200,
    }
    calls = []
    monkeypatch.setattr(main.client, 'get_att_logs', lambda *args: calls.append(args) or {
        'result': {'items': [
            {'attLogTime': '2026-08-03T09:00:00'},
            {'attLogTime': '2026-08-03T17:00:00'},
        ]}
    })
    monkeypatch.setattr(main.db, 'get_user_schedules_in_range', lambda *args: {})
    monkeypatch.setattr(main.db, 'get_salary_day_rate_overrides', lambda *args: [])

    detail = main.build_salary_detail_for_user(profile, '2026-08', rule, set())

    assert len(calls) == 1
    assert detail['daily'][0]['work_hours'] == 8
    assert detail['summary']['total_work_minutes'] == 480


def test_monthly_salary_does_not_count_fixed_allowances_twice(monkeypatch):
    profile = {
        'user_id': 7, 'clock_id': '2002', 'role_id': 3, 'salary_type': 'monthly',
        'monthly_salary': 40000, 'hourly_salary': None,
        'weekday_hourly_rate': None, 'holiday_hourly_rate': None,
        'professional_allowance': 2000, 'position_allowance': 1000,
        'base_salary_amount': 35000, 'sales_allowance': 1000,
        'overtime_allowance': 500, 'night_shift_allowance': 300,
        'special_leave_allowance': 200,
    }
    rule = {
        'regular_hours_staff': 8.5, 'regular_hours_manager': 9.0,
        'grace_late_minutes': 5, 'grace_early_minutes': 5,
        'overtime_hourly_multiplier': 1.5, 'overtime_monthly_multiplier': 1.33,
        'holiday_multiplier': 2.0, 'default_hourly_rate': 200,
    }
    monkeypatch.setattr(main.client, 'get_att_logs', lambda *args: {'result': {'items': []}})
    monkeypatch.setattr(main.db, 'get_user_schedules_in_range', lambda *args: {})
    monkeypatch.setattr(main.db, 'get_salary_day_rate_overrides', lambda *args: [])

    result = main.build_salary_result_for_user(profile, '2026-08', rule, set())

    assert result['base_pay'] == 40000
    assert result['gross_salary'] == 40000
    assert result['net_salary'] == 40000


def test_salary_excel_summary_wraps_at_column_h_and_bolds_net_pay():
    workbook = Workbook()
    ws = workbook.active
    summary = {
        'total_work_minutes': 480, 'regular_minutes': 450,
        'overtime_minutes': 30, 'holiday_minutes': 0,
        'late_count': 0, 'early_count': 0, 'late_deduction': 0,
        'base_salary_amount': 35000, 'professional_allowance': 2000,
        'position_allowance': 1000, 'sales_allowance': 500,
        'overtime_allowance': 300, 'night_shift_allowance': 200,
        'special_leave_allowance': 100, 'gross_salary': 39600, 'net_salary': 39600,
    }

    end_row = main.write_salary_excel_summary(
        ws, summary, 3, PatternFill('solid', fgColor='D9E1F2')
    )

    assert ws.max_column == 8
    assert ws['A5'].value == '底薪'
    assert ws['H5'].value == '實發'
    assert ws['H6'].value == 39600
    assert ws['H6'].font.bold is True
    assert end_row == 6


def test_salary_ma_upserts_professional_allowance_item(client, monkeypatch):
    called = {'value': False}

    def fake_upsert(item_id, name, amount, note, updated_by):
        called['value'] = True
        return True

    monkeypatch.setattr(main.db, 'upsert_professional_allowance_item', fake_upsert)

    response = client.post('/hr/salary/ma', data={
        'csrf_token': 'token-salary-001',
        'action': 'upsert_allowance_item',
        'item_id': '',
        'name': 'N1',
        'amount': '3000',
        'note': 'Professional allowance'
    })

    assert response.status_code == 302
    assert called['value'] is True


def test_salary_structure_page_renders_filtered_rows(client, monkeypatch):
    monkeypatch.setattr(main.db, 'get_salary_structure_rows', lambda query_text=None, team_id=None, role_id=None: [{
        'user_id': 3,
        'username': 'alice',
        'first_name': 'Alice',
        'last_name': 'Wang',
        'role_id': 3,
        'team_id': 2,
        'salary_type': 'monthly',
        'monthly_salary': 50000,
        'hourly_salary': None,
        'weekday_hourly_rate': None,
        'holiday_hourly_rate': None,
        'professional_allowance': 3000,
        'position_allowance': 1000,
        'base_salary_amount': 0,
        'sales_allowance': 0,
        'overtime_allowance': 0,
        'night_shift_allowance': 0,
        'special_leave_allowance': 0,
    }])
    monkeypatch.setattr(main.db, 'get_teams', lambda: [{'team_id': 2, 'name': 'HR'}])
    monkeypatch.setattr(main.db, 'get_roles', lambda: [{'role_id': 3, 'name': 'Staff'}])
    monkeypatch.setattr(main.db, 'get_professional_allowance_items', lambda: [])
    monkeypatch.setattr(main.db, 'get_user_professional_allowance_map', lambda user_ids: {})

    response = client.get('/hr/salary/structure?q=alice&team_id=2')

    assert response.status_code == 200
    assert b'alice' in response.data


def test_runner_creates_professional_allowance_table(monkeypatch):
    created = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            created.append(sql)

        def fetchall(self):
            return []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

    monkeypatch.setattr(runner, 'get_db_connection', lambda: FakeConnection())
    monkeypatch.setattr(runner, 'load_sql_files', lambda: [Path('migrations/versions/0008_professional_allowance.sql')])

    runner.run_migrations()

    assert any('CREATE TABLE IF NOT EXISTS professional_allowance_item' in statement for statement in created)
