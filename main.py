from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash, abort, send_from_directory
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from datetime import timedelta, datetime, date
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask_babel import Babel
from blueprints.auth import auth_bp
from blueprints.approval import approval_bp
from blueprints.admin import admin_bp
from functions.permission import has_permission
from database.CI_API_Client import APIClient
from database.models import Currency
from dotenv import load_dotenv
from curl_cffi import requests
from config import get_config_class
from logging_config import setup_logging, set_request_id
import database.queries as db
import functions.email as email
import functions.human_resource as hr
import pandas as pd
import logging
import threading
import time
import schedule
import json
import os
import random
import re
import secrets
import string
import calendar
from decimal import Decimal, InvalidOperation

load_dotenv()

file_path = os.path.join(os.getcwd(), 'static', 'js', 'p_type_data.json')
app = Flask(__name__, template_folder='templates')
app.config.from_object(get_config_class())

app_secret = app.config.get('SECRET_KEY')
if not app_secret:
    if os.getenv('APP_ENV') == 'production':
        raise RuntimeError('SECRET_KEY is required in production environment')
    app_secret = secrets.token_hex(32)
app.secret_key = app_secret

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=app.config.get('SESSION_TIMEOUT_MINUTES', 60))

setup_logging(
    app.config.get('LOG_LEVEL', 'INFO'),
    service_name='approval_system',
    environment=os.getenv('APP_ENV', 'development').strip().lower()
)
logger = logging.getLogger('approval_system')


def get_locale():
    return session.get('locale', 'zh_TW')


babel = Babel(app, locale_selector=get_locale)
app.register_blueprint(auth_bp)
app.register_blueprint(approval_bp)
app.register_blueprint(admin_bp)


def validate_required_env():
    if os.getenv('APP_ENV', 'development').strip().lower() != 'production':
        return

    required_keys = ['DB_USER', 'DB_PASSWORD', 'API_USERNAME', 'API_PASSWORD', 'SMTP_SENDER_EMAIL', 'SMTP_PASSWORD']
    missing_keys = [key for key in required_keys if not os.getenv(key)]
    if missing_keys:
        raise RuntimeError(f'Missing required production environment variables: {", ".join(missing_keys)}')


validate_required_env()

UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
MANAGER_ROLES = {99, 0, 1, 2, 4}
ADMIN_ROLES = {99, 0}
ACCOUNTANT_ROLES = {99, 0, 4}
PERMISSION_KEYS = [
    'reset_password', 'p_list', 'p_edit', 'p_new', 'p_view',
    'hr_view_cross_department', 'hr_salary_calculate', 'hr_salary_rules_manage',
    'hr_new_member_manage', 'sys_settings_manage', 'role_permission_manage',
    'salary_submit', 'salary_approve'
]

# API client for bioLife
client = APIClient()

@app.context_processor
def inject_global_variables():
    logged_in = session.get('logged_in', False)
    username = session.get('username', 'NONE') if logged_in else ''
    pending_approval_count = 0
    if logged_in and session.get('user_id'):
        try:
            pending_approval_count = db.get_pending_approval_count(session['user_id'])
        except Exception:
            pass
    return {'username': username, 'csrf_token': get_csrf_token(),
            'pending_approval_count': pending_approval_count}


@app.after_request
def after_request(response):
    session.permanent = True
    response.set_cookie(
        'csrf_token',
        get_csrf_token(),
        secure=app.config['SESSION_COOKIE_SECURE'],
        httponly=True,
        samesite=app.config['SESSION_COOKIE_SAMESITE']
    )
    return response


@app.before_request
def assign_request_id():
    request_id = request.headers.get('X-Request-ID') or secrets.token_hex(8)
    set_request_id(request_id)


def get_csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


def json_error(message, status_code=400):
    return jsonify({'success': False, 'error': message, 'data': None}), status_code


def json_success(data=None, message='OK', status_code=200):
    payload = {'success': True, 'message': message, 'data': data}
    if isinstance(data, dict):
        payload.update(data)
    return jsonify(payload), status_code


def is_public_endpoint(endpoint):
    if not endpoint:
        return False
    return endpoint in {'w_menu', 'w_menu_test', 'static'} or endpoint.startswith('auth.login') or endpoint.startswith('auth.logout') or endpoint.startswith('auth.register')


def invalid_request(message='Invalid request', status_code=400):
    if request.is_json or request.path.startswith('/hr/') or request.path.startswith('/sys/'):
        return json_error(message, status_code)
    flash(message, category='danger')
    return redirect(request.referrer or url_for('homepage'))


def ensure_manager_role():
    return session.get('role_id') in MANAGER_ROLES


def ensure_admin_role():
    return session.get('role_id') in ADMIN_ROLES


def ensure_accountant_role():
    return session.get('role_id') in ACCOUNTANT_ROLES


def read_json_dict():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, json_error('Invalid JSON payload', 400)
    return data, None


def normalize_text(value, max_len=255):
    if value is None:
        return ''
    value = str(value).strip()
    return value[:max_len]


def valid_month_string(value):
    return bool(re.fullmatch(r'\d{4}-\d{2}', value or ''))


def parse_decimal(value, default=None):
    if value is None or str(value).strip() == '':
        return default
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return default


def month_range(year_month):
    year, month = [int(x) for x in year_month.split('-')]
    start_date = datetime(year, month, 1)
    end_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, end_day)
    return start_date, end_date


def parse_att_dt(value):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def parse_time_component(value):
    if value is None:
        return None

    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return datetime.min.replace(hour=hours, minute=minutes, second=seconds).time()

    if hasattr(value, 'hour') and hasattr(value, 'minute'):
        return value

    value_str = str(value).strip()
    if not value_str:
        return None

    try:
        return datetime.strptime(value_str, '%H:%M:%S').time()
    except ValueError:
        try:
            return datetime.strptime(value_str, '%H:%M').time()
        except ValueError:
            return None


def build_shift_window(day_key, schedule_row):
    start_time = parse_time_component((schedule_row or {}).get('start_time'))
    end_time = parse_time_component((schedule_row or {}).get('end_time'))
    if not start_time:
        return None, None

    shift_start = datetime.combine(day_key, start_time)
    if end_time:
        shift_end = datetime.combine(day_key, end_time)
        if shift_end <= shift_start:
            shift_end += timedelta(days=1)
    else:
        shift_end = shift_start + timedelta(hours=8)

    return shift_start, shift_end


def get_shift_day(dt_value):
    # Night shift logs after midnight (before 08:00) are attributed to previous shift day.
    if dt_value.hour < 8:
        return (dt_value - timedelta(days=1)).date()
    return dt_value.date()


def smart_group_punches(punches):
    """Group punches into {shift_date: [clock_in, clock_out]} without a fixed hour cutoff.

    A single LATE punch (>=12:00) on day D is carried forward and paired with
    the first EARLY punch (<12:00) on day D+1 to form a cross-midnight shift.
    All other cases are grouped within the same calendar date.
    """
    from collections import defaultdict
    by_date = defaultdict(list)
    for p in punches:
        by_date[p.date()].append(p)

    groups = {}
    carry = None  # unpaired late punch from the previous day

    for day in sorted(by_date.keys()):
        day_punches = sorted(by_date[day])

        if carry is not None:
            first = day_punches[0]
            if first.hour < 12:
                # first punch of today is the clock-out for carry's night shift
                groups[carry.date()] = [carry, first]
                day_punches = day_punches[1:]
            else:
                # no clock-out found; carry stands alone
                groups[carry.date()] = [carry]
            carry = None

        if not day_punches:
            continue

        if len(day_punches) >= 2:
            groups[day] = [day_punches[0], day_punches[-1]]
        else:
            punch = day_punches[0]
            if punch.hour >= 12:
                carry = punch  # defer: might be start of cross-midnight shift
            else:
                groups[day] = [punch]  # early solo punch → missing clock-out

    if carry is not None:
        groups[carry.date()] = [carry]

    return groups


def collect_request_meta():
    return request.remote_addr, f"{request.user_agent.platform}/{request.user_agent.browser}"


def _audit_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')


def write_audit(entity_type, entity_id, action, before_json, after_json):
    ip_addr, user_agent = collect_request_meta()
    db.append_audit_log(
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        changed_by=session.get('user_id'),
        before_json=json.dumps(before_json, ensure_ascii=False, default=_audit_default) if before_json is not None else None,
        after_json=json.dumps(after_json, ensure_ascii=False, default=_audit_default) if after_json is not None else None,
        ip_address=ip_addr,
        user_agent=user_agent
    )


def build_salary_result_for_user(profile, year_month, rule, holiday_date_set):
    start_date, end_date = month_range(year_month)
    pin = str(profile.get('clock_id') or '').strip()
    if not pin.isdigit():
        return None

    # ±1 day buffer so night-shift clock-outs on the 1st of next month are captured.
    att_logs = client.get_att_logs(pin, start_date - timedelta(days=1), end_date + timedelta(days=1))
    items = ((att_logs or {}).get('result') or {}).get('items') or []
    parsed = [parse_att_dt(item.get('attLogTime', '')) for item in items]
    parsed = [dt for dt in parsed if dt is not None]
    parsed.sort()

    month_start = start_date.date()
    month_end = end_date.date()
    all_groups = smart_group_punches(parsed)
    day_groups = {d: v for d, v in all_groups.items() if month_start <= d <= month_end}

    role_id = int(profile.get('role_id') or 3)
    regular_hours = Decimal(str(rule['regular_hours_manager'])) if role_id in [0, 1, 2, 4, 99] else Decimal(str(rule['regular_hours_staff']))
    break_minutes = 60 if role_id in [0, 1, 2, 4, 99] else 30
    paid_regular_minutes = int((regular_hours * Decimal('60')).quantize(Decimal('1'))) - break_minutes
    grace_late = int(rule['grace_late_minutes'])
    grace_early = int(rule['grace_early_minutes'])

    # Pre-fetch all scheduled shifts for the month to avoid per-day DB calls.
    schedules_by_date = db.get_user_schedules_in_range(profile['user_id'], start_date, end_date)

    total_work_minutes = 0
    regular_minutes = 0
    overtime_minutes = 0
    holiday_minutes = 0
    late_count = 0
    early_count = 0

    for day_key, punches in day_groups.items():
        punches.sort()
        if len(punches) < 2:
            continue
        start_punch = punches[0]
        end_punch = punches[-1]
        work_minutes = max(0, int((end_punch - start_punch).total_seconds() // 60))
        total_work_minutes += work_minutes

        # Use assigned shift window; fall back to 09:00 + regular_hours when no schedule set.
        sched_row = schedules_by_date.get(day_key)
        is_overnight = end_punch.date() != day_key
        if sched_row:
            sched_start, sched_end = build_shift_window(day_key, sched_row)
            if not sched_start:
                sched_start = datetime.combine(day_key, datetime.min.time()).replace(hour=9, minute=0)
                sched_end = sched_start + timedelta(minutes=int(regular_hours * 60))
        elif is_overnight:
            # Cross-midnight shift with no schedule — skip late/early; use actual times as window.
            sched_start, sched_end = start_punch, end_punch
        else:
            sched_start = datetime.combine(day_key, datetime.min.time()).replace(hour=9, minute=0)
            sched_end = sched_start + timedelta(minutes=int(regular_hours * 60))
        if start_punch > sched_start + timedelta(minutes=grace_late) and role_id not in MANAGER_ROLES and not is_overnight:
            pass  # late/early detection disabled until scheduling goes live
        if end_punch < sched_end - timedelta(minutes=grace_early) and role_id not in MANAGER_ROLES and not is_overnight:
            pass  # late/early detection disabled until scheduling goes live

        if day_key in holiday_date_set:
            holiday_minutes += work_minutes
            continue

        day_regular = min(work_minutes, max(0, paid_regular_minutes))
        day_overtime = max(0, work_minutes - day_regular)
        regular_minutes += day_regular
        overtime_minutes += day_overtime

    default_rate = parse_decimal((rule or {}).get('default_hourly_rate'), Decimal('200'))
    salary_type = profile.get('salary_type') or 'hourly'
    hourly_rate = parse_decimal(profile.get('hourly_salary'), None)
    monthly_salary = parse_decimal(profile.get('monthly_salary'), None)
    # Fall back to default hourly rate when no salary is configured.
    if salary_type == 'hourly' and (hourly_rate is None or hourly_rate == Decimal('0')):
        hourly_rate = default_rate
        salary_type = 'hourly'
    elif salary_type == 'monthly' and (monthly_salary is None or monthly_salary == Decimal('0')):
        hourly_rate = default_rate
        salary_type = 'hourly'
        monthly_salary = Decimal('0')
    hourly_rate = hourly_rate or Decimal('0')
    monthly_salary = monthly_salary or Decimal('0')
    hourly_overtime_multiplier = parse_decimal(rule['overtime_hourly_multiplier'], Decimal('1.5'))
    monthly_overtime_multiplier = parse_decimal(rule['overtime_monthly_multiplier'], Decimal('1.33'))
    holiday_multiplier = parse_decimal(rule['holiday_multiplier'], Decimal('2.0'))

    base_pay = Decimal('0')
    overtime_pay = Decimal('0')
    holiday_pay = Decimal('0')

    if salary_type == 'hourly':
        base_pay = (hourly_rate * Decimal(regular_minutes) / Decimal('60'))
        overtime_pay = (hourly_rate * hourly_overtime_multiplier * Decimal(overtime_minutes) / Decimal('60'))
        holiday_pay = (hourly_rate * holiday_multiplier * Decimal(holiday_minutes) / Decimal('60'))
    else:
        base_pay = monthly_salary
        # Monthly-based overtime reference hourly rate based on 30 days * regular paid minutes.
        ref_minutes = max(1, paid_regular_minutes * 30)
        monthly_hourly = monthly_salary / (Decimal(ref_minutes) / Decimal('60'))
        overtime_pay = (monthly_hourly * monthly_overtime_multiplier * Decimal(overtime_minutes) / Decimal('60'))
        holiday_pay = (monthly_hourly * holiday_multiplier * Decimal(holiday_minutes) / Decimal('60'))

    gross_salary = base_pay + overtime_pay + holiday_pay
    # Use per-instance deduction from rule; multiply by late_count.
    rule_deduction = parse_decimal((rule or {}).get('late_deduction_per_instance'), None)
    late_deduction = rule_deduction * late_count if rule_deduction is not None else None
    net_salary = gross_salary - late_deduction if late_deduction is not None else gross_salary

    return {
        'user_id': profile['user_id'],
        'year_month': year_month,
        'salary_type': salary_type,
        'total_work_minutes': total_work_minutes,
        'regular_minutes': regular_minutes,
        'overtime_minutes': overtime_minutes,
        'holiday_minutes': holiday_minutes,
        'late_count': late_count,
        'early_count': early_count,
        'late_deduction': float(late_deduction) if late_deduction is not None else None,
        'gross_salary': float(gross_salary.quantize(Decimal('0.01'))),
        'net_salary': float(net_salary.quantize(Decimal('0.01')))
    }


def build_salary_detail_for_user(profile, year_month, rule, holiday_date_set):
    """Returns per-day breakdown + salary summary for payslip display / export."""
    start_date, end_date = month_range(year_month)
    pin = str(profile.get('clock_id') or '').strip()

    daily_rows = []
    if not pin.isdigit():
        return {'daily': [], 'summary': None}

    att_logs = client.get_att_logs(pin, start_date - timedelta(days=1), end_date + timedelta(days=1))
    items = ((att_logs or {}).get('result') or {}).get('items') or []
    parsed = [parse_att_dt(item.get('attLogTime', '')) for item in items]
    parsed = [dt for dt in parsed if dt is not None]
    parsed.sort()

    month_start = start_date.date()
    month_end = end_date.date()
    all_groups = smart_group_punches(parsed)
    day_groups = {d: v for d, v in all_groups.items() if month_start <= d <= month_end}

    role_id = int(profile.get('role_id') or 3)
    regular_hours = Decimal(str(rule['regular_hours_manager'])) if role_id in [0, 1, 2, 4, 99] else Decimal(str(rule['regular_hours_staff']))
    break_minutes = 60 if role_id in [0, 1, 2, 4, 99] else 30
    paid_regular_minutes = int((regular_hours * Decimal('60')).quantize(Decimal('1'))) - break_minutes
    grace_late = int(rule['grace_late_minutes'])
    grace_early = int(rule['grace_early_minutes'])
    schedules_by_date = db.get_user_schedules_in_range(profile['user_id'], start_date, end_date)

    WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

    for day_key, punches in sorted(day_groups.items()):
        punches.sort()
        is_holiday = day_key in holiday_date_set
        sched_row = schedules_by_date.get(day_key)

        # Determine shift window; handle cross-midnight shifts without a schedule gracefully.
        has_two = len(punches) >= 2
        is_overnight = has_two and punches[-1].date() != day_key
        if sched_row:
            sched_start, sched_end = build_shift_window(day_key, sched_row)
            if not sched_start:
                sched_start = datetime.combine(day_key, datetime.min.time()).replace(hour=9, minute=0)
                sched_end = sched_start + timedelta(minutes=int(regular_hours * 60))
        elif is_overnight:
            sched_start, sched_end = punches[0], punches[-1]
        else:
            sched_start = datetime.combine(day_key, datetime.min.time()).replace(hour=9, minute=0)
            sched_end = sched_start + timedelta(minutes=int(regular_hours * 60))

        if len(punches) < 2:
            # single punch: late (>=12:00) = missing clock-out; early = missing clock-out too
            # (cross-midnight pairing was already handled by smart_group_punches)
            daily_rows.append({
                'date': day_key.strftime('%Y-%m-%d'),
                'weekday': WEEKDAYS[day_key.weekday()],
                'actual_start': punches[0].strftime('%H:%M:%S'),
                'actual_end': '-',
                'work_hours': 0,
                'regular_hours': 0,
                'overtime_hours': 0,
                'is_holiday': is_holiday,
                'status': '缺簽退',
            })
            continue

        start_punch = punches[0]
        end_punch = punches[-1]
        work_minutes = max(0, int((end_punch - start_punch).total_seconds() // 60))
        can_check_lateness = not is_overnight or sched_row  # skip if cross-midnight with no schedule
        is_late = False  # disabled until scheduling goes live
        is_early = False  # disabled until scheduling goes live

        if is_late and is_early:
            status = '遲到+早退'
        elif is_late:
            status = '遲到'
        elif is_early:
            status = '早退'
        elif is_holiday:
            status = '假日出勤'
        elif end_punch > sched_end + timedelta(minutes=30):
            status = '加班'
        else:
            status = '正常'

        if is_holiday:
            day_regular, day_overtime = 0, 0
        else:
            day_regular = min(work_minutes, max(0, paid_regular_minutes))
            day_overtime = max(0, work_minutes - day_regular)

        daily_rows.append({
            'date': day_key.strftime('%Y-%m-%d'),
            'weekday': WEEKDAYS[day_key.weekday()],
            'actual_start': start_punch.strftime('%H:%M:%S'),
            'actual_end': end_punch.strftime('%H:%M:%S'),
            'work_hours': round(work_minutes / 60, 2),
            'regular_hours': round(day_regular / 60, 2),
            'overtime_hours': round(day_overtime / 60, 2),
            'is_holiday': is_holiday,
            'status': status,
        })

    # Re-use build_salary_result_for_user for the summary (avoids duplicate API call issue;
    # pass pre-parsed data via a lightweight re-calculation here).
    summary = build_salary_result_for_user(profile, year_month, rule, holiday_date_set)
    return {'daily': daily_rows, 'summary': summary}


@app.route('/hr/salary/detail', methods=['POST'])
def hr_salary_detail():
    if not has_permission('hr_salary_calculate', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    data, error = read_json_dict()
    if error:
        return error

    user_id_raw = str(data.get('user_id', '')).strip()
    year_month = normalize_text(data.get('year_month', ''), 7)
    if not user_id_raw.isdigit() or not valid_month_string(year_month):
        return json_error('Invalid parameters', 400)

    profile = db.get_full_salary_profile_for_user(int(user_id_raw))
    if not profile:
        return json_error('User not found', 404)

    rule = db.get_active_salary_rule(year_month)
    if not rule:
        return json_error('No salary rule for this month', 400)

    holidays = db.get_holidays_by_month(year_month)
    holiday_date_set = {item['holiday_date'] for item in holidays}

    detail = build_salary_detail_for_user(profile, year_month, rule, holiday_date_set)
    return json_success(detail)


@app.route('/hr/salary/export', methods=['GET'])
def hr_salary_export():
    if not has_permission('hr_salary_calculate', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    year_month = request.args.get('year_month') or datetime.now().strftime('%Y-%m')
    if not valid_month_string(year_month):
        return json_error('Invalid year_month', 400)

    rule = db.get_active_salary_rule(year_month)
    if not rule:
        flash('無對應薪資規則，無法匯出', category='danger')
        return redirect(url_for('hr_salary_cal', year_month=year_month))

    holidays = db.get_holidays_by_month(year_month)
    holiday_date_set = {item['holiday_date'] for item in holidays}

    results = db.get_salary_results(year_month, session.get('user_id'), session.get('role_id'))
    if not results:
        flash('尚無試算資料', category='warning')
        return redirect(url_for('hr_salary_cal', year_month=year_month))

    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    header_fill = PatternFill('solid', fgColor='4472C4')
    header_font = Font(bold=True, color='FFFFFF')
    sub_fill = PatternFill('solid', fgColor='D9E1F2')
    holiday_fill = PatternFill('solid', fgColor='FFF2CC')

    for row in results:
        profile = db.get_full_salary_profile_for_user(row['user_id'])
        if not profile:
            continue
        detail = build_salary_detail_for_user(profile, year_month, rule, holiday_date_set)
        s = detail.get('summary') or {}
        daily = detail.get('daily') or []

        name = f"{row.get('first_name','')}{row.get('last_name','')}"
        ws = wb.create_sheet(title=f"{row['user_id']}-{name}"[:31])

        ws.append([f'薪資單 — {year_month}', '', '', '', '', '', '', ''])
        ws.merge_cells('A1:H1')
        ws['A1'].font = Font(bold=True, size=14)

        ws.append([f'員工：{name}（ID {row["user_id"]}）', '', f'薪資型態：{s.get("salary_type","-")}'])
        ws.append([])

        day_headers = ['日期', '星期', '上班', '下班', '工時(h)', '狀態']
        ws.append(day_headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')

        for d in daily:
            fill = holiday_fill if d['is_holiday'] else None
            ws.append([
                d['date'], d['weekday'],
                d['actual_start'], d['actual_end'],
                d['work_hours'], d['status']
            ])
            if fill:
                for cell in ws[ws.max_row]:
                    cell.fill = fill

        ws.append([])
        summary_headers = ['總工時(h)', '一般工時(h)', '加班(h)', '假日(h)', '遲到次', '早退次', '遲到扣款', '應發', '實發']
        ws.append(summary_headers)
        for cell in ws[ws.max_row]:
            cell.fill = sub_fill
            cell.font = Font(bold=True)
        ws.append([
            round((s.get('total_work_minutes') or 0) / 60, 2),
            round((s.get('regular_minutes') or 0) / 60, 2),
            round((s.get('overtime_minutes') or 0) / 60, 2),
            round((s.get('holiday_minutes') or 0) / 60, 2),
            s.get('late_count', 0), s.get('early_count', 0),
            s.get('late_deduction') or 0,
            s.get('gross_salary', 0), s.get('net_salary', 0)
        ])

        from openpyxl.utils import get_column_letter
        for i in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(i)].width = 14

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    from flask import make_response
    resp = make_response(buf.read())
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    resp.headers['Content-Disposition'] = f'attachment; filename=salary_{year_month}.xlsx'
    return resp


@app.before_request
def check_authentication():
    endpoint = request.endpoint or ''
    is_logged_in = 'username' in session

    if not is_public_endpoint(endpoint) and not is_logged_in:
        if not request.path.endswith(('.js', '.css', '.jpg', '.png', '.jpeg', '.svg', '.ico', '.woff', '.woff2')):
            logger.info('Anonymous access redirected to login: path=%s endpoint=%s', request.path, endpoint)
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return json_error('Session expired, please log in again', 401)
            return redirect(url_for('auth.login'))

    if request.method in UNSAFE_METHODS and endpoint != 'static':
        session_token = session.get('_csrf_token')
        request_token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')

        if request.is_json and not request_token:
            payload = request.get_json(silent=True) or {}
            request_token = payload.get('csrf_token')

        if not session_token or not request_token or not secrets.compare_digest(session_token, request_token):
            logger.warning('CSRF validation failed: path=%s endpoint=%s method=%s user=%s',
                           request.path, endpoint, request.method, session.get('username', 'anonymous'))
            return json_error('CSRF token invalid or missing', 400)


@app.errorhandler(403)
def forbidden_error(e):
    if request.is_json or request.path.startswith('/hr/') or request.path.startswith('/sys/'):
        logger.warning('Forbidden API access: path=%s user=%s', request.path, session.get('username', 'anonymous'))
        return json_error('Forbidden', 403)
    return render_template('/utility/basic_page/no_permission.html'), 403


@app.errorhandler(401)
def unauthorized_error(e):
    if request.is_json or request.path.startswith('/hr/') or request.path.startswith('/sys/'):
        logger.warning('Unauthorized API access: path=%s', request.path)
        return json_error('Unauthorized', 401)
    return render_template('/utility/personal/login.html'), 401


@app.route('/')
def homepage():
    return render_template('homepage.html')


@app.route('/w_menu')
def w_menu():
    current_time = datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d")

    currency_list, error_msg = update_currency(formatted_time)

    # Format the error fallback string
    if not error_msg:
        error_fallback = "missing"
    else:
        error_fallback = f"missing ({error_msg})"

    def calculate_rate(country):
        curr = next((c for c in currency_list if c.country == country), None)
        rate_val = calculate_front_desk_currency_rate(curr, country)
        if rate_val is not None:
            return rate_val

        logger.warning('Currency rate parse failed: country=%s value=%s', country, getattr(curr, 'bank_selling_rate', None))
        return error_fallback

    USD_val = calculate_rate('USD')
    SGD_val = calculate_rate('SGD')
    JPY_val = calculate_rate('JPY')
    EUR_val = calculate_rate('EUR')
    CNY_val = calculate_rate('CNY')

    USD = round(USD_val, 1) if isinstance(USD_val, (int, float)) else USD_val
    SGD = round(SGD_val, 1) if isinstance(SGD_val, (int, float)) else SGD_val
    JPY = round(JPY_val, 3) if isinstance(JPY_val, (int, float)) else JPY_val
    EUR = round(EUR_val, 1) if isinstance(EUR_val, (int, float)) else EUR_val
    CNY = round(CNY_val, 2) if isinstance(CNY_val, (int, float)) else CNY_val

    rates = {
        'USD': {'label': 'US Dollar', 'symbol': '$', 'value': USD_val, 'display': str(USD)},
        'SGD': {'label': 'Singapore Dollar', 'symbol': 'S$', 'value': SGD_val, 'display': str(SGD)},
        'JPY': {'label': 'Japanese Yen', 'symbol': '¥', 'value': JPY_val, 'display': str(JPY)},
        'EUR': {'label': 'Euro', 'symbol': '€', 'value': EUR_val, 'display': str(EUR)},
        'CNY': {'label': 'Chinese Yuan', 'symbol': '¥', 'value': CNY_val, 'display': str(CNY)},
    }

    return render_template('front_desk_wheel_menu.html', rates=rates, date=formatted_time)


@app.route('/w_menu_test')
def w_menu_test():
    current_time = datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d")
    currency_list, error_msg = update_currency(formatted_time)
    error_fallback = "N/A"

    def calculate_rate(country):
        curr = next((c for c in currency_list if c.country == country), None)
        return calculate_front_desk_currency_rate(curr, country)

    rates = {
        'USD': {'label': 'US Dollar', 'symbol': '$', 'value': calculate_rate('USD'), 'decimals': 1},
        'SGD': {'label': 'Singapore Dollar', 'symbol': 'S$', 'value': calculate_rate('SGD'), 'decimals': 1},
        'JPY': {'label': 'Japanese Yen', 'symbol': '¥', 'value': calculate_rate('JPY'), 'decimals': 3},
        'EUR': {'label': 'Euro', 'symbol': '€', 'value': calculate_rate('EUR'), 'decimals': 1},
        'CNY': {'label': 'Chinese Yuan', 'symbol': '¥', 'value': calculate_rate('CNY'), 'decimals': 2},
    }
    for k, v in rates.items():
        if v['value'] is not None:
            v['display'] = f"{round(v['value'], v['decimals'])}"
        else:
            v['display'] = error_fallback

    return render_template('front_desk_wheel_menu_test.html', rates=rates, date=formatted_time)


# Human Resource
@app.route('/hr/new', methods=['GET', 'POST'])
def hr_new_member():
    if not has_permission('hr_new_member_manage', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    if request.method == 'POST':
        organization = normalize_text(request.form.get('organization'), 50)
        department = normalize_text(request.form.get('department'), 50)
        organization_id = hr.check_organization_id(organization, department)
        ssn = normalize_text(request.form.get('ssn'), 30)
        first_name = normalize_text(request.form.get('first_name'), 50)
        last_name = normalize_text(request.form.get('last_name'), 50)
        e_mail = normalize_text(request.form.get('e_mail'), 255)
        phone = normalize_text(request.form.get('phone'), 30)

        if not organization_id or not first_name or not last_name:
            return invalid_request('新增人員資料不完整')

        team_id = hr.check_team_id(organization_id)
        clock_id = client.get_latest_person_pin(organization_unit_id=organization_id)

        logger.info(
            'hr_onboarding_input_validated org_id=%s team_id=%s clock_id=%s first_name=%s last_name=%s operator=%s',
            organization_id, team_id, clock_id, first_name, last_name, session.get('user_id')
        )

        created_pin = str(clock_id)
        create_ok = 0
        try:
            for _ in range(10):
                while db.check_existing_username(created_pin):
                    created_pin = str(int(created_pin) + 1)
                create_ok = hr.hr_new_person_result(pin=created_pin, name=f"{first_name}{last_name}",
                                                    og_id=organization_id, ssn=ssn)
                if create_ok == 1:
                    break
                created_pin = str(int(created_pin) + 1)

            if create_ok != 1:
                flash('BioLife 人員建立失敗，請稍後再試', category='danger')
                return redirect('/hr/new')

            chars = string.ascii_lowercase + string.digits
            temp_password = ''.join(random.choice(chars) for _ in range(10))
            local_created = db.import_user(
                username=created_pin,
                password=temp_password,
                first_name=first_name,
                last_name=last_name,
                role_id=3,
                team_id=team_id,
                phone=phone,
                email=e_mail,
                clock_id=created_pin
            )
            if not local_created:
                raise RuntimeError('Local user creation failed')
        except Exception as exc:
            try:
                client.leave_person(created_pin)
                logger.warning('hr_onboarding_compensated_biolife pin=%s reason=%s', created_pin, exc)
            except Exception as cleanup_exc:
                logger.exception('hr_onboarding_cleanup_failed pin=%s error=%s', created_pin, cleanup_exc)

            flash('新人建立失敗，已嘗試回復 BioLife 人員資料', category='danger')
            return redirect('/hr/new')

        write_audit(
            entity_type='hr_member',
            entity_id=created_pin,
            action='create',
            before_json=None,
            after_json={
                'pin': created_pin,
                'first_name': first_name,
                'last_name': last_name,
                'team_id': team_id,
                'organization_id': organization_id,
                'email': e_mail,
                'phone': phone
            }
        )

        logger.info(
            'hr_onboarding_completed pin=%s org_id=%s team_id=%s operator=%s',
            created_pin, organization_id, team_id, session.get('user_id')
        )
        flash(f'新人建立成功，帳號: {created_pin}，臨時密碼: {temp_password}', category='success')
        return redirect('/hr/new')
    return render_template('/utility/hr/hr_new.html')


@app.route('/hr/staff/sync', methods=['GET'])
def hr_staff_sync():
    if not has_permission('hr_new_member_manage', session['user_id'], session['team_id'], session['role_id']):
        abort(403)
    return render_template('/utility/hr/hr_staff_sync.html')


@app.route('/hr/staff/sync/check', methods=['POST'])
def hr_staff_sync_check():
    """Returns two lists: to_deactivate (in system, gone from BioLife) and to_add (in BioLife, not in system)."""
    if not has_permission('hr_new_member_manage', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    local_users = db.get_active_numeric_users()
    local_pins = {u['username']: u for u in local_users}

    try:
        biolife_persons = client.get_all_biolife_persons()
    except Exception as exc:
        logger.exception('BioLife sync check failed: %s', exc)
        return json_error('BioLife API 連線失敗，請稍後再試', 503)

    # org_unit_id → (organization, department) mapping from human_resource logic
    ORG_UNIT_MAP = {
        7: ('new_garden', 'manage'), 8: ('new_garden', 'front'),
        9: ('new_garden', 'housekeeping'), 10: ('new_garden', 'finance'),
        16: ('new_garden', 'marketing'), 18: ('new_garden', 'restaurant'),
        12: ('new_dev', 'manage'), 13: ('new_dev', 'front'),
        14: ('new_dev', 'housekeeping'), 15: ('new_dev', 'finance'),
        17: ('new_dev', 'marketing'), 19: ('new_dev', 'restaurant'),
    }

    biolife_pins = {p['pin']: p for p in biolife_persons}

    to_deactivate = [
        {'user_id': u['user_id'], 'username': u['username'],
         'name': f"{u['first_name']} {u['last_name']}"}
        for pin, u in local_pins.items() if pin not in biolife_pins
    ]

    to_add = []
    for pin, p in biolife_pins.items():
        if pin in local_pins:
            continue
        raw_name = (p.get('name') or '').strip()
        # 2 chars → 1+1, 3 chars → 1+2, 4+ chars → 2+rest
        if len(raw_name) >= 4:
            last_name, first_name = raw_name[:2], raw_name[2:]
        elif len(raw_name) == 3:
            last_name, first_name = raw_name[:1], raw_name[1:]
        elif len(raw_name) == 2:
            last_name, first_name = raw_name[:1], raw_name[1:]
        else:
            last_name, first_name = raw_name, ''

        org_id = p.get('org_unit_id')
        try:
            org_id = int(org_id) if org_id is not None else None
        except (ValueError, TypeError):
            org_id = None
        org, dept = ORG_UNIT_MAP.get(org_id, ('', ''))

        to_add.append({
            'pin': pin, 'name': raw_name,
            'last_name': last_name, 'first_name': first_name,
            'organization': org, 'department': dept,
        })

    return json_success({'to_deactivate': to_deactivate, 'to_add': to_add})


@app.route('/hr/staff/sync/deactivate', methods=['POST'])
def hr_staff_sync_deactivate():
    if not has_permission('hr_new_member_manage', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    data, error = read_json_dict()
    if error:
        return error

    user_ids = [int(uid) for uid in (data.get('user_ids') or []) if str(uid).isdigit()]
    if not user_ids:
        return json_error('No user IDs provided', 400)

    db.set_users_inactive(user_ids)
    write_audit('staff_sync', 'deactivate', 'batch_deactivate', None, {'user_ids': user_ids})
    logger.info('Staff sync deactivated: user_ids=%s operator=%s', user_ids, session.get('user_id'))
    return json_success({'deactivated': len(user_ids)})


@app.route('/hr/staff/sync/add', methods=['POST'])
def hr_staff_sync_add():
    if not has_permission('hr_new_member_manage', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    organization = normalize_text(request.form.get('organization'), 50)
    department = normalize_text(request.form.get('department'), 50)
    pin = normalize_text(request.form.get('pin'), 20)
    first_name = normalize_text(request.form.get('first_name'), 50)
    last_name = normalize_text(request.form.get('last_name'), 50)
    e_mail = normalize_text(request.form.get('e_mail'), 255)
    phone = normalize_text(request.form.get('phone'), 30)

    if not pin or not pin.isdigit() or not first_name:
        flash('員工編號與姓名為必填', category='danger')
        return redirect('/hr/staff/sync')

    organization_id = hr.check_organization_id(organization, department) if organization and department else None
    team_id = hr.check_team_id(organization_id) if organization_id else 6

    if db.check_existing_username(pin):
        flash(f'帳號 {pin} 已存在，跳過新增', category='warning')
        return redirect('/hr/staff/sync')

    DEFAULT_SYNC_PASSWORD = 'zxcvbnma'
    local_created = db.import_user(
        username=pin, password=DEFAULT_SYNC_PASSWORD,
        first_name=first_name, last_name=last_name,
        role_id=3, team_id=team_id, phone=phone, email=e_mail, clock_id=pin
    )
    if not local_created:
        flash(f'新增 {pin} 失敗', category='danger')
        return redirect('/hr/staff/sync')

    write_audit('staff_sync', pin, 'add_from_biolife', None,
                {'pin': pin, 'first_name': first_name, 'last_name': last_name})
    flash(f'已新增帳號 {pin}，預設密碼 zxcvbnma', category='success')
    return redirect('/hr/staff/sync')

@app.route('/hr/schedule/<department>', methods=['GET', 'POST'])
def hr_main(department):
    valid_depts = ['FD', 'RT', 'HK', 'AC']
    if department not in valid_depts:
        department = 'FD'
    return render_template('/utility/hr/hr_schedule.html', department=department)


SCHEDULE_TEAM_IDS = {1, 2, 4}  # 櫃台、房務、業務


@app.route('/hr/schedule/off-request', methods=['GET'])
def hr_off_request():
    if session.get('team_id') not in SCHEDULE_TEAM_IDS and session.get('role_id') not in MANAGER_ROLES:
        abort(403)
    today = datetime.now().date()
    # Requests are for next month; allowed between 1st and 27th of current month
    can_submit = 1 <= today.day <= 27
    next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    next_month_str = next_month.strftime('%Y-%m')

    my_requests = db.get_off_requests_for_month(session['user_id'], next_month_str)
    my_dates = [str(r['request_date']) for r in my_requests]

    return render_template('/utility/hr/hr_off_request.html',
                           can_submit=can_submit, next_month_str=next_month_str,
                           my_dates=my_dates)


@app.route('/hr/schedule/off-request/save', methods=['POST'])
def hr_off_request_save():
    if session.get('team_id') not in SCHEDULE_TEAM_IDS and session.get('role_id') not in MANAGER_ROLES:
        return json_error('Forbidden', 403)
    data, error = read_json_dict()
    if error:
        return error

    action = data.get('action')
    raw_date = normalize_text(data.get('date', ''), 10)

    try:
        req_date = date.fromisoformat(raw_date)
    except ValueError:
        return json_error('日期格式錯誤', 400)

    today = datetime.now().date()
    # Deadline: must request by 27th of the month before the target month
    if today.day > 27 or req_date.month == today.month:
        return json_error('申請期限已過或日期不符（僅可申請下個月、1–27日前提出）', 400)

    if action == 'add':
        note = normalize_text(data.get('note', ''), 200)
        db.upsert_off_request(session['user_id'], req_date, note)

        # Conflict detection: find others who requested the same date
        all_for_date = db.get_off_requests_by_dates([req_date])
        others = [
            f"{r['last_name']}{r['first_name']}"
            for r in all_for_date
            if r['user_id'] != session['user_id']
        ]
        return json_success({'conflicts': others})

    elif action == 'remove':
        db.cancel_off_request(session['user_id'], req_date)
        return json_success({})

    return json_error('Unknown action', 400)


@app.route('/hr/schedule/off-request/manager', methods=['GET', 'POST'])
def hr_off_request_manager():
    if not ensure_manager_role():
        abort(403)

    month_str = request.args.get('month') or datetime.now().strftime('%Y-%m')
    requests = db.get_all_off_requests_for_month(month_str)
    shift_types = db.get_shift_types()
    constraints = db.get_scheduling_constraints()
    teams = db.get_teams()

    if request.method == 'POST' and request.is_json:
        data, error = read_json_dict()
        if error:
            return error
        team_id = int(data.get('team_id', 0))
        shift_type_id = int(data.get('shift_type_id', 0))
        min_count = int(data.get('min_count', 1))
        db.upsert_scheduling_constraint(team_id, shift_type_id, min_count, session['user_id'])
        return json_success({})

    return render_template('/utility/hr/hr_off_request_manager.html',
                           month_str=month_str, requests=requests,
                           shift_types=shift_types, constraints=constraints, teams=teams)

@app.route('/hr/salary/cal', methods=['GET', 'POST'])
def hr_salary_cal():
    if not has_permission('hr_salary_calculate', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    year_month = request.values.get('year_month') or datetime.now().strftime('%Y-%m')
    if not valid_month_string(year_month):
        year_month = datetime.now().strftime('%Y-%m')

    rule = db.get_active_salary_rule(year_month)
    results = db.get_salary_results(year_month, session.get('user_id'), session.get('role_id'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'calculate':
            if not ensure_accountant_role() and session.get('role_id') not in [0, 1]:
                abort(403)

            profiles = db.get_salary_profiles()
            if session.get('role_id') not in [99, 0, 1, 2, 4]:
                profiles = [p for p in profiles if p['user_id'] == session.get('user_id')]

            if not profiles:
                flash('目前沒有可試算的員工薪資設定', category='warning')
                return redirect(url_for('hr_salary_cal', year_month=year_month))

            if not rule:
                flash('尚未建立薪資規則版本，請先至 Salary Rules 設定', category='danger')
                return redirect(url_for('hr_salary_cal', year_month=year_month))

            holidays = db.get_holidays_by_month(year_month)
            holiday_date_set = {item['holiday_date'] for item in holidays}

            calculated_count = 0
            for profile in profiles:
                result = build_salary_result_for_user(profile, year_month, rule, holiday_date_set)
                if not result:
                    continue

                db.save_salary_result(
                    year_month=year_month,
                    user_id=result['user_id'],
                    rule_version_id=rule['id'],
                    total_work_minutes=result['total_work_minutes'],
                    regular_minutes=result['regular_minutes'],
                    overtime_minutes=result['overtime_minutes'],
                    holiday_minutes=result['holiday_minutes'],
                    late_count=result['late_count'],
                    early_count=result['early_count'],
                    late_deduction=result['late_deduction'],
                    gross_salary=result['gross_salary'],
                    net_salary=result['net_salary'],
                    payroll_status='draft'
                )
                calculated_count += 1

            write_audit(
                entity_type='salary_calculation',
                entity_id=year_month,
                action='calculate',
                before_json=None,
                after_json={'year_month': year_month, 'calculated_count': calculated_count,
                            'rule_version_id': rule['id']}
            )
            flash(f'薪資試算完成，共 {calculated_count} 人', category='success')

        elif action == 'submit':
            if not has_permission('salary_submit', session['user_id'], session['team_id'], session['role_id']):
                abort(403)
            result_rows = db.get_salary_results(year_month, session.get('user_id'), session.get('role_id'))
            user_ids = [row['user_id'] for row in result_rows]
            if not user_ids:
                flash('目前沒有可提交的薪資資料', category='warning')
                return redirect(url_for('hr_salary_cal', year_month=year_month))
            if user_ids:
                db.update_salary_status(year_month, user_ids, 'submitted', session.get('user_id'))
                write_audit('salary_calculation', year_month, 'submit', None, {'user_ids': user_ids})
                flash('已提交給主管審核', category='success')

        elif action == 'approve':
            if not has_permission('salary_approve', session['user_id'], session['team_id'], session['role_id']):
                abort(403)
            result_rows = db.get_salary_results(year_month, session.get('user_id'), session.get('role_id'))
            user_ids = [row['user_id'] for row in result_rows]
            if not user_ids:
                flash('目前沒有可核可的薪資資料', category='warning')
                return redirect(url_for('hr_salary_cal', year_month=year_month))
            if user_ids:
                db.update_salary_status(year_month, user_ids, 'approved', session.get('user_id'))
                write_audit('salary_calculation', year_month, 'approve', None, {'user_ids': user_ids})
                flash('薪資已核可', category='success')

        return redirect(url_for('hr_salary_cal', year_month=year_month))

    page_size = request.args.get('page_size', '50')
    page = request.args.get('page', '1')
    try:
        page_size_int = int(page_size)
        if page_size_int not in [50, 100]:
            page_size_int = 50
    except ValueError:
        page_size_int = 50

    try:
        page_int = max(1, int(page))
    except ValueError:
        page_int = 1

    total_count = len(results)
    total_pages = max(1, (total_count + page_size_int - 1) // page_size_int)
    if page_int > total_pages:
        page_int = total_pages
    start_idx = (page_int - 1) * page_size_int
    end_idx = start_idx + page_size_int
    paged_results = results[start_idx:end_idx]

    return render_template('/utility/hr/hr_salary_cal.html', year_month=year_month,
                           rule=rule, results=paged_results, role_id=session.get('role_id'),
                           page_size=page_size_int, page=page_int, total_pages=total_pages,
                           total_count=total_count)

@app.route('/hr/salary/ma', methods=['GET', 'POST'])
def hr_salary_ma():
    if not has_permission('hr_salary_rules_manage', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'create_rule':
            version_name = normalize_text(request.form.get('version_name'), 100)
            effective_from = normalize_text(request.form.get('effective_from'), 20)

            if not version_name or not effective_from:
                flash('版本名稱與生效日不可為空', category='danger')
                return redirect('/hr/salary/ma')

            try:
                datetime.strptime(effective_from, '%Y-%m-%d')
            except ValueError:
                flash('生效日格式錯誤，請使用 YYYY-MM-DD', category='danger')
                return redirect('/hr/salary/ma')

            overtime_monthly_multiplier = parse_decimal(request.form.get('overtime_monthly_multiplier'), Decimal('1.33'))
            overtime_hourly_multiplier = parse_decimal(request.form.get('overtime_hourly_multiplier'), Decimal('1.5'))
            holiday_multiplier = parse_decimal(request.form.get('holiday_multiplier'), Decimal('2.0'))
            grace_late_minutes = int(normalize_text(request.form.get('grace_late_minutes'), 4) or '5')
            grace_early_minutes = int(normalize_text(request.form.get('grace_early_minutes'), 4) or '5')
            regular_hours_staff = parse_decimal(request.form.get('regular_hours_staff'), Decimal('8.5'))
            regular_hours_manager = parse_decimal(request.form.get('regular_hours_manager'), Decimal('9.0'))
            late_deduction_per_instance = parse_decimal(request.form.get('late_deduction_per_instance'), None)
            default_hourly_rate = parse_decimal(request.form.get('default_hourly_rate'), Decimal('200'))

            rule_id = db.create_salary_rule_version(
                version_name=version_name or f'rule-{datetime.now().strftime("%Y%m%d%H%M")}',
                effective_from=effective_from,
                overtime_monthly_multiplier=overtime_monthly_multiplier,
                overtime_hourly_multiplier=overtime_hourly_multiplier,
                holiday_multiplier=holiday_multiplier,
                grace_late_minutes=grace_late_minutes,
                grace_early_minutes=grace_early_minutes,
                regular_hours_staff=regular_hours_staff,
                regular_hours_manager=regular_hours_manager,
                created_by=session.get('user_id'),
                late_deduction_per_instance=late_deduction_per_instance,
                default_hourly_rate=default_hourly_rate
            )
            write_audit('salary_rule', rule_id, 'create', None, {
                'version_name': version_name,
                'effective_from': effective_from,
                'overtime_monthly_multiplier': float(overtime_monthly_multiplier),
                'overtime_hourly_multiplier': float(overtime_hourly_multiplier),
                'holiday_multiplier': float(holiday_multiplier),
                'grace_late_minutes': grace_late_minutes,
                'grace_early_minutes': grace_early_minutes,
                'regular_hours_staff': float(regular_hours_staff),
                'regular_hours_manager': float(regular_hours_manager),
                'late_deduction_per_instance': float(late_deduction_per_instance) if late_deduction_per_instance else None,
                'default_hourly_rate': float(default_hourly_rate)
            })
            flash('薪資規則版本已建立', category='success')

        elif action == 'upsert_profile':
            user_id_raw = normalize_text(request.form.get('user_id'), 20)
            if not user_id_raw.isdigit():
                flash('員工編號格式錯誤', category='danger')
                return redirect('/hr/salary/ma')

            user_id = int(user_id_raw)
            salary_type = normalize_text(request.form.get('salary_type'), 20) or 'monthly'
            monthly_salary = parse_decimal(request.form.get('monthly_salary'), None)
            hourly_salary = parse_decimal(request.form.get('hourly_salary'), None)
            before = db.get_user_salary_profile(user_id)
            db.upsert_salary_profile(user_id, salary_type, monthly_salary, hourly_salary, session.get('user_id'))
            after = db.get_user_salary_profile(user_id)
            write_audit('salary_profile', user_id, 'upsert', before, after)
            flash('員工薪資設定已更新', category='success')

        elif action == 'upsert_holiday':
            holiday_date = normalize_text(request.form.get('holiday_date'), 20)
            holiday_name = normalize_text(request.form.get('holiday_name'), 100)
            if not holiday_date or not holiday_name:
                flash('假日日期與名稱不可為空', category='danger')
                return redirect('/hr/salary/ma')

            try:
                datetime.strptime(holiday_date, '%Y-%m-%d')
            except ValueError:
                flash('假日日期格式錯誤，請使用 YYYY-MM-DD', category='danger')
                return redirect('/hr/salary/ma')

            db.upsert_holiday(holiday_date, holiday_name, 'TW', session.get('user_id'))
            write_audit('holiday_calendar', holiday_date, 'upsert', None,
                        {'holiday_date': holiday_date, 'holiday_name': holiday_name})
            flash('國定假日已更新', category='success')

        return redirect('/hr/salary/ma')

    rule = db.get_active_salary_rule()
    profiles = db.get_salary_profiles()
    holiday_month = datetime.now().strftime('%Y-%m')
    holidays = db.get_holidays_by_month(holiday_month)
    return render_template('/utility/hr/hr_salary_ma.html', rule=rule, profiles=profiles,
                           holiday_month=holiday_month, holidays=holidays)


@app.route('/hr/clockRecord', methods=['GET', 'POST'])
def hr_clock_record():
    all_users = []
    # Check if user is manager (Role ID 0 or 1)
    if session.get('role_id') in [99, 0, 1, 2]:
        all_users = db.get_all_users_with_clock_id()
    
    return render_template("/utility/hr/hr_clock_record.html", all_users=all_users)

@app.route('/hr/clockRecordPost', methods=['POST'])
def hr_clock_record_post():
    if not ensure_manager_role() and not session.get('clock_id'):
        return json_error('Unauthorized: No PIN provided', 401)

    current_user_pin = str(session.get('clock_id'))
    if not current_user_pin:
        return json_error('Unauthorized: No PIN provided', 401)

    data, error = read_json_dict()
    if error:
        return error

    start_date = data.get("Start")
    end_date = data.get("End")
    target_pin = data.get("target_pin")

    # Permission check for viewing other users
    if target_pin:
        if not ensure_manager_role():
             return json_error('Unauthorized: Insufficient permissions', 403)
        pin = str(target_pin)
    else:
        pin = current_user_pin

    if not isinstance(pin, str) or not pin.isdigit():
        return json_error('Invalid PIN format', 400)

    if not start_date or not end_date:
        return json_error('Invalid date range', 400)

    try:
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S").date()
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        return json_error('Invalid date format. Expected YYYY-MM-DD HH:MM:SS', 400)

    att_logs = client.get_att_logs(pin, start_date_obj, end_date_obj)

    if not att_logs.get('result') or not att_logs['result'].get('items'):
        employee_info = client.get_employee_info(pin)
        
        # Fallback to local DB if unknown
        if not employee_info:
            db_user = db.get_user_by_clock_id(pin)
            if db_user:
                employee_info = {"pin": pin, "name": f"{db_user['first_name']} {db_user['last_name']}"}
            else:
                employee_info = {"pin": pin, "name": "Unknown"}
        
        response_data = {
             "result": {
                "items": [], 
                "summary": [], 
                "date": {
                    "start": start_date,
                    "end": end_date},
                "employee": employee_info
            }
        }
        return json_success(response_data)
    
    # Calculate Summary
    raw_logs = att_logs['result']['items']
    raw_logs.sort(key=lambda x: x['attLogTime'])
    
    # Resolve Name from DB if API fails
    employee_info = None
    if 'employee' in att_logs['result']: # Sometimes API returns it inside result
        employee_info = att_logs['result']['employee']
    
    # Check if we need to fetch info (API structure varies, assuming we might need to fetch if not present)
    if not employee_info:
         employee_info = client.get_employee_info(pin)

    if not employee_info:
        db_user = db.get_user_by_clock_id(pin)
        if db_user:
            employee_info = {"pin": pin, "name": f"{db_user['first_name']} {db_user['last_name']}"}
        else:
            employee_info = {"pin": pin, "name": "Unknown"}

    att_logs['result']['employee'] = employee_info

    all_dts = []
    for log in raw_logs:
        log_time_str = log['attLogTime']
        try:
            log_dt = datetime.strptime(log_time_str, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            try:
                log_dt = datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        all_dts.append(log_dt)

    # Use the same smart grouping as salary calculation (no fixed-hour cutoff).
    smart_groups = smart_group_punches(all_dts)

    summary_list = []

    # Get User ID for Schedule Lookup
    db_user_for_schedule = db.get_user_by_clock_id(pin)
    user_id_for_schedule = db_user_for_schedule['user_id'] if db_user_for_schedule else None

    # Resolve grace minutes from salary rule so checks match salary calculation.
    active_rule = db.get_active_salary_rule()
    grace_late_minutes = int(active_rule['grace_late_minutes']) if active_rule else 5
    grace_early_minutes = int(active_rule['grace_early_minutes']) if active_rule else 5

    for date_key, times in smart_groups.items():
        times = sorted(times)
        start_time = times[0]
        end_time = times[-1]

        work_minutes = 0
        duration_str = ""
        status = "Normal"
        
        if len(times) > 1:
            diff = end_time - start_time
            work_minutes = int(diff.total_seconds() // 60)
            hours = work_minutes // 60
            minutes = work_minutes % 60
            duration_str = f"{hours}h {minutes}m"
        else:
            duration_str = "-"
            status = "Missing Punch"
            
        # Dynamic Late / Early check based on assigned schedule.
        threshold_start = start_time.replace(hour=9, minute=0, second=0, microsecond=0) # Default
        threshold_end = start_time.replace(hour=18, minute=0, second=0, microsecond=0)
        
        if user_id_for_schedule:
            # Fetch assigned schedule
            sch = db.get_user_schedule_by_date(user_id_for_schedule, date_key)
            if sch:
                threshold_start, threshold_end = build_shift_window(date_key, sch)

        if len(times) > 1 and threshold_start and threshold_end:
            is_late = start_time > threshold_start + timedelta(minutes=grace_late_minutes)
            is_early = end_time < threshold_end - timedelta(minutes=grace_early_minutes)
            if is_late and is_early:
                status = "Late / Early Leave"
            elif is_late:
                status = "Late"
            elif is_early:
                status = "Early Leave"
            else:
                # Flag overtime when punched out significantly past scheduled end.
                if end_time > threshold_end + timedelta(minutes=30):
                    status = "Overtime"
                else:
                    status = "Normal"
        elif len(times) > 1 and start_time > threshold_start:
            status = "Late"
            
        summary_list.append({
            "date": date_key.strftime("%Y-%m-%d"),
            "start": start_time.strftime("%H:%M:%S"),
            "end": end_time.strftime("%H:%M:%S") if len(times) > 1 else "-",
            "duration": duration_str,
            "work_minutes": work_minutes,
            "status": status
        })
    
    summary_list.sort(key=lambda x: x['date'], reverse=True)
    att_logs['summary'] = summary_list

    return json_success({
        "result": {
            "items": att_logs,
            "date": {
                "start": start_date,
                "end": end_date
            }
        }
    })


@app.route('/set_locale', methods=['POST'])
def set_locale():
    selected_locale = normalize_text(request.form.get('locale'), 10)
    if selected_locale not in {'zh_TW', 'ja_JP', 'en_US'}:
        return invalid_request('Unsupported locale')
    session['locale'] = selected_locale
    return redirect(request.referrer)


@app.route('/test', methods=['GET', 'POST'])
def test():
    return render_template('practice/practicing.html')

# Schedule Management Routes
@app.route('/hr/schedule/list', methods=['POST'])
def hr_schedule_list():
    data, error = read_json_dict()
    if error:
        return error

    start_date = data.get('start_date')
    end_date = data.get('end_date')
    department = normalize_text(data.get('department', ''), 10)

    if not start_date or not end_date:
        return json_error('Missing start_date or end_date', 400)

    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return json_error('Invalid date format. Expected YYYY-MM-DD', 400)
    
    # Team Mapping
    team_ids = None
    if department == 'FD': team_ids = [1, 4]
    elif department == 'RT': team_ids = [5]
    elif department == 'HK': team_ids = [2]
    elif department == 'AC': team_ids = [3]
    
    # Get all Schedules
    schedules = db.get_schedules(start_date, end_date, team_ids)
    
    # Get Shift Types
    shift_types = db.get_shift_types()
    
    # Get Employees (for manager palette)
    employees = []
    if session.get('role_id') in [99, 0, 1, 2]: 
        employees = db.get_all_users_with_clock_id()

    # Convert date/time objects to string for JSON
    def serialize(obj):
        if isinstance(obj, (datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, timedelta):
             return str(obj)
        return obj

    return json_success({
        "schedules": [{**s, "date": str(s['date']), "start_time": str(s['start_time']), "end_time": str(s['end_time'])} for s in schedules],
        "shift_types": [{**st, "start_time": str(st['start_time']), "end_time": str(st['end_time'])} for st in shift_types],
        "employees": employees
    })

@app.route('/hr/schedule/save', methods=['POST'])
def hr_schedule_save():
    if not ensure_manager_role():
        return json_error('Unauthorized', 403)

    data, error = read_json_dict()
    if error:
        return error

    user_id = data.get('user_id')
    date = data.get('date')
    shift_type_id = data.get('shift_type_id')

    if not user_id or not date:
        return json_error('Missing parameters', 400)

    if not str(user_id).isdigit():
        return json_error('Invalid user_id', 400)
        
    # If shift_type_id is null/empty, delete the schedule
    if not shift_type_id:
        db.delete_schedule(user_id, date)
    else:
        db.save_schedule(user_id, date, shift_type_id, session['user_id'])
        
    logger.info('Schedule saved: user_id=%s date=%s shift_type_id=%s operator=%s',
                user_id, date, shift_type_id, session.get('user_id'))
    return json_success({'saved': True})

@app.route('/hr/shift/save', methods=['POST'])
def hr_shift_save():
    if not ensure_manager_role():
        return json_error('Unauthorized', 403)

    data, error = read_json_dict()
    if error:
        return error

    shift_id = data.get('id')
    name = normalize_text(data.get('name'), 50)
    start_time = normalize_text(data.get('start_time'), 10)
    end_time = normalize_text(data.get('end_time'), 10)
    color = normalize_text(data.get('color'), 20)

    if not name or not start_time or not end_time:
        return json_error('Missing shift type fields', 400)
    
    db.save_shift_type(name, start_time, end_time, color, shift_id)
    logger.info('Shift type saved: shift_id=%s name=%s operator=%s', shift_id, name, session.get('user_id'))
    return json_success({'saved': True})

@app.route('/hr/api/comment/get', methods=['POST'])
def hr_comment_get():
    if not ensure_manager_role():
        return json_error('Unauthorized', 403)

    data, error = read_json_dict()
    if error:
        return error

    dept = normalize_text(data.get('department'), 10)
    month = normalize_text(data.get('month'), 7)
    if not dept or not valid_month_string(month):
        return json_error('Invalid department/month', 400)

    content = db.get_schedule_comment(dept, month)
    return json_success({'content': content})

@app.route('/hr/api/comment/save', methods=['POST'])
def hr_comment_save():
    if not ensure_manager_role():
        return json_error('Unauthorized', 403)

    data, error = read_json_dict()
    if error:
        return error

    dept = normalize_text(data.get('department'), 10)
    month = normalize_text(data.get('month'), 7)
    content = normalize_text(data.get('content'), 20000)
    if not dept or not valid_month_string(month):
        return json_error('Invalid department/month', 400)

    db.save_schedule_comment(dept, month, content)
    logger.info('Schedule comment saved: dept=%s month=%s operator=%s', dept, month, session.get('user_id'))
    return json_success({'saved': True})

@app.route('/hr/api/comment/copy', methods=['POST'])
def hr_comment_copy():
    if not ensure_manager_role():
        return json_error('Unauthorized', 403)

    data, error = read_json_dict()
    if error:
        return error

    dept = normalize_text(data.get('department'), 10)
    curr_month = normalize_text(data.get('current_month'), 7)
    if not dept or not valid_month_string(curr_month):
        return json_error('Invalid department/month', 400)

    content = db.get_previous_month_comment(dept, curr_month)
    return json_success({'content': content})

@app.route('/excelimport', methods=['GET', 'POST'])
def excel_import():
    if not ensure_admin_role():
        abort(403)

    if request.method == 'GET':
        return render_template('/utility/sys/excel_import.html')
    
    file = request.files.get('file')
    if not file or not file.filename.endswith('.xlsx'):
         flash('Invalid file', 'danger')
         return redirect('/excelimport')
         
    try:
        df = pd.read_excel(file)
        
        summary = {"total": 0, "added": 0, "skipped": 0, "errors": 0}
        
        output_dir = os.path.join(os.getcwd(), 'output')
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Register Font for Traditional Chinese
        try:
            pdfmetrics.registerFont(UnicodeCIDFont('MSung-Light'))
            font_name = 'MSung-Light'
        except Exception as exc:
            # Fallback if CID font not available (unlikely in reportlab unless minimal)
            logger.warning('CID font registration failed, falling back to Helvetica: %s', exc)
            font_name = 'Helvetica'
        
        for index, row in df.iterrows():
            summary["total"] += 1
            try:
                emp_id = str(row['員工編號']).strip()
                name = str(row['姓名']).strip()
                dept = str(row['部門名稱']).strip()
                
                # Name Split
                if len(name) == 4:
                    first_name = name[:2]
                    last_name = name[2:]
                elif len(name) == 3:
                    first_name = name[:1]
                    last_name = name[1:]
                elif len(name) == 2:
                    first_name = name[:1]
                    last_name = name[1:]
                else:
                    first_name = name
                    last_name = ""
                    
                # Team ID
                team_id = 1 
                if '管理' in dept: team_id = 0
                elif '櫃台' in dept: team_id = 1
                elif '房務' in dept: team_id = 2
                elif '會計' in dept: team_id = 3
                elif '業務' in dept: team_id = 4
                elif '餐飲' in dept: team_id = 5
                
                chars = string.ascii_lowercase + string.digits
                password = ''.join(random.choice(chars) for _ in range(10))
                
                success = db.import_user(
                    username=emp_id, 
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role_id=3,
                    team_id=team_id,
                    phone="",
                    email="",
                    clock_id=emp_id
                )
                
                if success:
                    summary["added"] += 1
                    
                    # PDF Generation
                    filename = f"{first_name}{last_name}.pdf" 
                    pdf_path = os.path.join(output_dir, filename)
                    
                    # Half of A4 (A5 Landscape-ish: 210mm wide, 148mm high)
                    # A4 is (595.27, 841.89). Half height = 420.
                    page_size = (A4[0], A4[1] / 2)
                    w, h = page_size
                    
                    c = canvas.Canvas(pdf_path, pagesize=page_size)
                    
                    # Draw English text with Helvetica (Safe)
                    c.setFont("Helvetica", 16)
                    c.setFillColorRGB(0, 0, 0)
                    c.drawString(50, h - 50, f"Welcome to the System!")
                    
                    # Draw Name (Try Chinese font, fallback to name only)
                    try:
                        c.setFont(font_name, 16) # MSung-Light if established
                        c.drawString(50, h - 80, f"Name: {name}") 
                    except Exception as exc:
                        logger.warning('PDF Chinese font draw fallback used: %s', exc)
                        c.setFont("Helvetica", 16)
                        c.drawString(50, h - 80, f"Name: {name}")

                    # Back to Helvetica for credentials
                    c.setFont("Helvetica", 16)
                    c.drawString(50, h - 110, f"Account: {emp_id}")
                    c.drawString(50, h - 140, f"Password: {password}")
                    c.save()
                    
                    if "files" not in summary:
                        summary["files"] = []
                    summary["files"].append(filename)
                    
                else:
                    summary["skipped"] += 1
                    
            except Exception as e:
                logger.exception('Excel import row error: index=%s error=%s', index, e)
                summary["errors"] += 1
                
        return render_template('/utility/sys/excel_import.html', summary=summary)
        
    except Exception as e:
        logger.exception('Excel import failed: error=%s', e)
        flash(f'Error processing file: {str(e)}', 'danger')
        return redirect('/excelimport')


@app.route('/download/pdf/<filename>')
def download_pdf(filename):
    if session.get('role_id') not in [99, 1, 2, 3, 4, 5]: # Allow logged in users
         return json_error('Unauthorized', 403)
    return send_from_directory(os.path.join(os.getcwd(), 'output'), filename, as_attachment=True)




# System Settings
def get_agent(req):
    platform = req.user_agent.platform
    browser = req.user_agent.browser
    return f"Platform: {platform}, Browser: {browser}"

def calculate_front_desk_currency_rate(curr, country):
    if not curr:
        return None

    if country in {'JPY'}:
        discount = 0.01
    elif country in {'CNY'}:
        discount = 0.1
    else:
        discount = 1

    buying_rate = getattr(curr, 'bank_buying_rate', None)
    if buying_rate is None:
        return None

    try:
        return float(buying_rate) - discount
    except (TypeError, ValueError):
        return None


def update_currency(date):
    currency_list = []
    error_msg = None

    url = 'https://rate.bot.com.tw/xrt/flcsv/0/day'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://rate.bot.com.tw/xrt?Lang=zh-TW'
    }

    try:
        rate = requests.get(url, timeout=5, headers=headers, impersonate="chrome120")
        
        if rate.status_code != 200:
            error_msg = f"HTTP {rate.status_code}"
            logger.warning('Currency fetch failed: status=%s', rate.status_code)
        else:
            rate.encoding = 'utf-8'  
            rt = rate.text
            
            if 'html' in rate.headers.get('Content-Type', '').lower() or rt.strip().startswith('<!DOCTYPE'):
                error_msg = "Blocked by BOT WAF/Challenge"
                logger.warning('Currency fetch blocked by upstream challenge')
            else:
                rts = rt.split('\n')
                for i in rts:
                    try:
                        a = i.split(',')
                        if len(a) > 13:
                            # a[0] = Currency Code (e.g. USD)
                            # a[2] = Cash Buying (現金買入)
                            # a[3] = Spot Buying (即期買入)
                            currency_list.append(Currency(date, a[0].strip(), a[2].strip(), a[3].strip()))
                    except Exception as exc:
                        logger.debug('Skipping malformed currency row: %s', exc)
                
                if not currency_list:
                    error_msg = "CSV parse failure or empty rows"
                    logger.warning('Currency CSV parse returned empty rows')
                    
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logger.exception('Currency fetch exception: %s', e)

    return currency_list, error_msg

def schedule_task():
    def job():
        formatted_time = datetime.now().strftime("%Y-%m-%d")
        _, _ = update_currency(formatted_time)

    schedule.every().day.at("23:30").do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=schedule_task, daemon=True)
    scheduler_thread.start()

    if os.getenv('APP_ENV') == 'production':
        app.run(host="0.0.0.0", port=80)
    else:
        app.run(host="0.0.0.0", port=80, debug=True)
