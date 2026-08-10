from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash, abort
from datetime import timedelta, datetime, date
from flask_babel import Babel, gettext as babel_gettext
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

try:
    import holidays as py_holidays
except Exception:
    py_holidays = None

load_dotenv()

file_path = os.path.join(os.getcwd(), 'static', 'js', 'p_type_data.json')
app = Flask(__name__, template_folder='templates')
app.config.from_object(get_config_class())

app_secret = app.config.get('SECRET_KEY')
if not app_secret:
    if os.getenv('APP_ENV') == 'production':
        raise RuntimeError('SECRET_KEY is required in production environment')
    app_secret = 'approvalsys-dev-secret'
app.secret_key = app_secret

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=app.config.get('SESSION_TIMEOUT_MINUTES', 60))
app.config['SESSION_COOKIE_NAME'] = app.config.get('SESSION_COOKIE_NAME', 'approvalsys_session')
app.session_cookie_name = app.config['SESSION_COOKIE_NAME']

setup_logging(
    app.config.get('LOG_LEVEL', 'INFO'),
    service_name='approval_system',
    environment=os.getenv('APP_ENV', 'development').strip().lower()
)
logger = logging.getLogger('approval_system')

TW_HOLIDAY_NAME_MAP = {
    'Founding Day of the Republic of China': '中華民國開國紀念日',
    'Founding Day of the Republic of China (observed)': '中華民國開國紀念日（補假）',
    'Peace Memorial Day': '和平紀念日',
    'Peace Memorial Day (observed)': '和平紀念日（補假）',
    'Chinese New Year': '春節',
    'Chinese New Year (observed)': '春節（補假）',
    "Lunar New Year's Eve": '農曆除夕',
    "Lunar New Year's Eve (observed)": '農曆除夕（補假）',
    "Chinese New Year's Eve": '農曆除夕',
    "Chinese New Year's Eve (observed)": '農曆除夕（補假）',
    'The second day of Chinese New Year': '春節初二',
    'The second day of Chinese New Year (observed)': '春節初二（補假）',
    'The third day of Chinese New Year': '春節初三',
    'The third day of Chinese New Year (observed)': '春節初三（補假）',
    'Children\'s Day': '兒童節',
    'Children\'s Day (observed)': '兒童節（補假）',
    'Tomb-Sweeping Day': '清明節',
    'Tomb-Sweeping Day (observed)': '清明節（補假）',
    'Labour Day': '勞動節',
    'Labour Day (observed)': '勞動節（補假）',
    'Labor Day': '勞動節',
    'Labor Day (observed)': '勞動節（補假）',
    'Dragon Boat Festival': '端午節',
    'Dragon Boat Festival (observed)': '端午節（補假）',
    'Mid-Autumn Festival': '中秋節',
    'Mid-Autumn Festival (observed)': '中秋節（補假）',
    "Confucius' Birthday": '孔子誕辰紀念日',
    "Confucius' Birthday (observed)": '孔子誕辰紀念日（補假）',
    'National Day': '國慶日',
    'National Day (observed)': '國慶日（補假）',
    'Taiwan Restoration and Guningtou Victory Memorial Day': '臺灣光復暨金門古寧頭大捷紀念日',
    'Taiwan Restoration and Guningtou Victory Memorial Day (observed)': '臺灣光復暨金門古寧頭大捷紀念日（補假）',
    'Constitution Day': '行憲紀念日',
    'Constitution Day (observed)': '行憲紀念日（補假）'
}


def normalize_tw_holiday_name(name):
    name = normalize_text(name, 120)
    return TW_HOLIDAY_NAME_MAP.get(name, name)


def subtract_months(base_date, months):
    year = base_date.year
    month = base_date.month - months
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(base_date.day, last_day)
    return date(year, month, day)


def fetch_public_holidays_tw(year):
    holidays = []

    # Primary source: external public holiday API.
    try:
        url = f'https://date.nager.at/api/v3/PublicHolidays/{year}/TW'
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        payload = response.json()
        for item in payload or []:
            holiday_date = normalize_text(item.get('date'), 10)
            local_name = normalize_text(item.get('localName') or item.get('name'), 120)
            try:
                parsed_date = date.fromisoformat(holiday_date)
            except ValueError:
                continue
            if not local_name:
                local_name = f'Holiday {parsed_date.isoformat()}'
            holidays.append({'date': parsed_date, 'name': normalize_tw_holiday_name(local_name)})
    except Exception as exc:
        logger.warning('Public holiday API failed: year=%s error=%s', year, exc)

    if holidays:
        return holidays

    # Fallback source: offline generation from python-holidays package.
    if py_holidays is not None:
        try:
            try:
                tw_holidays = py_holidays.country_holidays('TW', years=[year], language='zh_TW')
            except TypeError:
                tw_holidays = py_holidays.country_holidays('TW', years=[year])
            for holiday_date, holiday_name in sorted(tw_holidays.items()):
                holidays.append({'date': holiday_date, 'name': normalize_tw_holiday_name(holiday_name)})
        except Exception as exc:
            logger.warning('Offline holiday generation failed: year=%s error=%s', year, exc)

    return holidays


def sync_tw_holidays_for_year(year, operator_id):
    synced_count = 0
    for holiday in fetch_public_holidays_tw(year):
        db.upsert_holiday(holiday['date'], holiday['name'], 'TW', operator_id)
        synced_count += 1
    return synced_count


def run_holiday_sync_if_needed(today_date, operator_id):
    trigger_date = today_date.strftime('%m-%d')
    target_years = []
    if trigger_date in {'01-01', '07-01'}:
        target_years.append(today_date.year)
    if trigger_date == '10-01':
        target_years.append(today_date.year + 1)

    if not target_years:
        return 0

    synced_total = 0
    for year in target_years:
        try:
            synced_total += sync_tw_holidays_for_year(year, operator_id)
        except Exception as exc:
            logger.warning('Holiday sync failed: year=%s error=%s', year, exc)
    return synced_total


def translate_text(message, *args, **kwargs):
    locale = session.get('locale', 'zh_TW')
    fallback_map = {
        'zh_TW': {
            'HomePage': '首頁',
            'Homepage': '首頁',
            'Approval System': '簽呈系統',
            'System Setting': '系統設定',
            'System Settings': '系統設定',
            'System': '系統',
            'Settings': '設定',
            'Users & Access': '使用者與權限',
            'Users': '使用者',
            'Permissions': '權限',
            'Audit Logs': '稽核紀錄',
            'Approval': '簽呈',
            'Approval List': '簽呈列表',
            'New Approval': '新增簽呈',
            'User': '用戶',
            'Accountant': '會計',
            'Staff Management': '人員管理',
            'New Staff': '新增人員',
            'Sync Staff': '同步人員',
            'Utilities': '功能',
            'Human Resource': '人資',
            'Components': '元件',
            'Custom Components': '自訂元件',
            'Custom Utilities': '自訂功能',
            'Addons': '附加元件',
            'Pages': '頁面',
            'Login Screens': '登入畫面',
            'Login': '登入',
            'Register': '註冊',
            'Forgot Password': '忘記密碼',
            'Other Pages': '其他頁面',
            '404 Page': '404 頁面',
            'Blank Page': '空白頁面',
            'Electronic Signature System': '電子簽呈系統',
            'Colors': '顏色',
            'Borders': '邊框',
            'Animations': '動畫',
            'Other': '其他',
            'Welcome Back!': '歡迎回來！',
            'Password': '密碼',
            'First Name': '名字',
            'Last Name': '姓氏',
            'Phone Number': '電話號碼',
            'Email': '電子郵件',
            'Reset Password': '重設密碼',
            'Confirm Password': '確認密碼',
            'Submit': '送出',
            'Personal Information': '個人資料',
            'Basic Information': '基本資料',
            'To change the account, please contact the IT or HR staff.': '若要變更帳號，請聯絡 IT 或人資人員。',
            'New password (leave blank to keep current)': '新密碼（留空則維持目前密碼）',
            'HR Information (Read-only)': 'HR 資料（唯讀）',
            'Employee ID': '員工編號',
            'Super Admin': '超級管理員',
            'Admin': '管理員',
            'Manager': '主管',
            'Supervisor': '督導',
            'Staff': '員工',
            'Management Department': '管理部',
            'Front Desk': '前台',
            'Housekeeping': '房務',
            'Accounting': '會計',
            'Sales': '業務',
            'Restaurant': '餐廳',
            'Account Status': '帳號狀態',
            'Active': '啟用',
            'Inactive': '停用',
            'Salary Information': '薪資資訊',
            'Salary Type': '薪資類型',
            'Monthly Salary': '月薪',
            'Hourly Salary': '時薪',
            'No salary information has been set yet.': '尚未設定薪資資訊。',
            'System Settings': '系統設定',
            'User Management': '使用者管理',
            'Audit Trail': '稽核追蹤',
            'Access Control': '權限控管',
            'User List': '使用者列表',
            'Edit User': '編輯使用者',
            'Edit': '編輯',
            'Deactivate': '停用',
            'Batch processing': '批次處理',
            'End batch processing': '結束批次處理',
            'Batch deactivate': '批次停用',
            'Batch delete': '批次刪除',
            'Select all': '全選',
            'Confirm action': '確認操作',
            'Confirm account deactivation': '確認停用帳號',
            'Confirm account deletion': '確認刪除帳號',
            'Please select at least one account.': '請至少選擇一個帳號。',
            'The account will no longer be able to log in after deactivation.': '停用後，該帳號將無法繼續登入。',
            'Deletion cannot be undone. If the account has related data, deletion will be rejected.': '刪除後無法復原。若帳號已有關聯資料，系統將拒絕刪除。',
            'Account': '帳號',
            '%(count)s accounts selected.': '共選擇 %(count)s 個帳號。',
            'Confirm deactivate': '確認停用',
            'Confirm delete': '確認刪除',
            'Update User Information': '更新使用者資訊',
            'Approval Content': '簽呈內容',
            'Approval History': '簽呈歷史',
            'Pending approval': '待處理簽呈',
            'Approval Edit History': '簽呈修改歷史',
            'Reject Approval': '退回簽呈',
            'Pending approval requests': '待處理簽呈申請',
            'Approval Recipients': '簽呈收件人',
            'Approval Search': '簽呈搜尋',
            'Review Approval': '審核簽呈',
            'Edit Approval': '編輯簽呈',
            'Salary Simulation and Approval': '薪資試算與簽核',
            'Rule version': '規則版本',
            'No data yet. Please run the simulation first.': '尚無資料，請先執行試算。',
            'Month': '月份',
            'Items per page': '每頁筆數',
            'Batch actions': '批次動作',
            'Run simulation': '執行試算',
            'Submit for review': '送審',
            'Approve': '核准',
            'Using rule': '使用規則',
            'Effective date': '生效日期',
            'Simulation results': '試算結果',
            'Export all payslips (Excel)': '匯出所有薪資單 (Excel)',
            'Expand details': '展開詳細資料',
            'Load failed': '載入失敗',
            'Unknown error': '未知錯誤',
            'Simulation amount': '試算金額',
            'Date': '日期',
            'Weekday': '星期',
            'Clock in': '簽到',
            'Clock out': '簽退',
            'Working hours (h)': '工時 (小時)',
            'Regular hours (h)': '常規工時 (小時)',
            'Overtime hours (h)': '加班工時 (小時)',
            'Custom hourly rate': '自訂時薪',
            'Total working hours': '總工時',
            'Overtime': '加班',
            'Holiday': '假日',
            'Late': '遲到',
            'Early leave': '早退',
            'Gross / Net pay': '總薪資 / 淨薪資',
            'Late deduction': '遲到扣款',
            'API request failed. Please try again later.': 'API 請求失敗，請稍後再試。',
            'Previous page': '上一頁',
            'Next page': '下一頁',
            'Role Permissions': '角色權限',
            'Choose a role to manage its permission overrides. Each entry explains the page route, purpose, and the roles that usually use it.': '選擇一個角色來管理其權限覆寫。每個項目都說明頁面路徑、用途以及通常使用的角色。',
            'Select a role': '選擇角色',
            'Role permissions for': '角色權限：',
            'Back to role list': '返回角色列表',
            'Route / URL': '路徑 / URL',
            'Typical roles': '典型角色',
            'Allow': '允許',
            'Deny': '拒絕',
            'Select a role button above to review and adjust that role’s permissions.': '請點選上方角色按鈕來檢視與調整該角色的權限。',
            'Create salary rule version': '建立薪資規則版本',
            'Create rule version': '建立規則版本',
            'Staff management — sync with BioLife': '人員管理 — 與 BioLife 同步',
            'Confirm deactivation': '確認停用',
            'Confirm Submit': '確認送出',
            'Click dates to request or cancel off-request': '點選日期以申請或取消排休',
            'Remove shift?': '移除班表？',
            'Last Month': '上個月',
            'Working Shift': '班表',
            'Schedule': '班表',
            'Clock Record': '打卡記錄',
            'Clock Record Inquiry': '打卡記錄查詢',
            'Current month': '當月',
            'Last month': '上個月',
            'Custom date': '自訂日期',
            'My records': '我的紀錄',
            'Show daily summary': '顯示每日統計',
            'Select date range': '選擇日期範圍',
            'Start date': '開始日期',
            'End date': '結束日期',
            'Confirm': '確定',
            'Cancel': '取消',
            'Please select a complete date range': '請選擇完整的日期區間',
            'Loading...': '載入中...',
            'No records found or insufficient permissions': '查無紀錄或權限不足',
            'No data': '無資料',
            'Off Request': '排休申請',
            'Off Request Mgmt': '排休管理',
            'Language': '語言',
            'Personal Profile': '個人資料',
            'Logout': '登出',
            'Schedule System': '班表系統',
            'Back to Homepage': '返回首頁',
            'Copyright': '版權所有',
            'Version': '版本',
            'Welcome back, %(name)s': '歡迎回來，%(name)s',
            'employee': '員工',
            'This page gathers your personal information, monthly attendance records, and quick access to approvals.': '這個頁面整合了您的個人資料、每月出勤紀錄與快速簽呈入口。',
            'Attendance records': '出勤紀錄',
            'My profile': '我的資料',
            'Name': '姓名',
            'Username': '帳號',
            'Role': '角色',
            'Department': '部門',
            'PIN': 'PIN',
            'PIN': 'PIN',
            'Approval area': '簽呈區',
            'Pending approvals': '待處理簽呈',
            'Recently approved': '近期已核准',
            'All': '全部',
            'There are no matching approvals at the moment.': '目前沒有符合條件的簽呈。',
            'Monthly attendance records': '每月出勤紀錄',
            'Attendance time': '出勤時間',
            'Verification method': '驗證方式',
            'There are no attendance records for this month yet.': '這個月尚無出勤紀錄。',
            'Salary Calculate': '薪資試算',
            'Salary Rules': '薪資規則',
            'Salary Structure': '薪資結構',
            'Search': '搜尋',
            'Save': '儲存',
            'Delete': '刪除',
            'Add': '新增',
            'Title': '標題',
            'Type': '類型',
            'Creator': '建立者',
            'Created Time': '建立時間',
            'View Page': '檢視頁面',
            'View': '檢視',
            'Items per page': '每頁筆數',
            'Employee': '員工',
            'Department': '部門',
            'Role': '角色',
            'Salary type': '薪資型態',
            'Monthly': '月薪',
            'Hourly': '時薪',
            'Back to salary rules': '返回薪資規則',
            'Search by name or username': '依姓名或帳號搜尋',
            'All departments': '全部部門',
            'All roles': '全部角色',
            'All Users': '所有使用者',
            'Page': '頁',
            'Page Size': '每頁筆數',
            'Filter': '篩選',
            'ID': '編號',
            'Username': '帳號',
            'Full Name': '全名',
            'Team': '團隊',
            'Email': '電子郵件',
            'Previous': '上一頁',
            'Next': '下一頁',
            'No users found.': '找不到使用者。',
            'Manage system users.': '管理系統使用者。',
            'username, name, email, role, team': '帳號、姓名、電子郵件、角色、團隊',
            'Base amount': '基本金額',
            'Allowances': '津貼',
            'Action': '操作',
            'Monthly salary': '月薪',
            'Hourly salary': '時薪',
            'Weekday hourly rate': '平日時薪',
            'Holiday hourly rate': '假日時薪',
            'Professional allowance': '專業津貼',
            'Position allowance': '職位津貼',
            'Base salary': '底薪',
            'Sales allowance': '業績津貼',
            'Overtime allowance': '加班津貼',
            'Night shift allowance': '夜班津貼',
            'Special leave allowance': '特休津貼',
            'No employee records found.': '找不到員工資料。',
            'Open salary structure': '開啟薪資結構',
            'Professional allowance registry': '專業津貼登錄',
            'Create salary rule version': '建立薪資規則版本',
            'Rule name': '規則名稱',
            'Monthly overtime multiplier': '月薪加班倍率',
            'Hourly overtime multiplier': '時薪加班倍率',
            'Holiday multiplier': '假日倍率',
            'Late grace (minutes)': '遲到寬限（分鐘）',
            'Early leave grace (minutes)': '早退寬限（分鐘）',
            'Reference working hours (general)': '參考工時（一般）',
            'Reference working hours (manager)': '參考工時（主管）',
            'Late deduction per instance (optional, leave blank to skip)': '每次遲到扣款（可選，留空則不扣）',
            'Actual deduction = this amount × number of late arrivals this month': '實際扣款 = 本金額 × 本月遲到次數',
            'Default hourly rate (applies when no salary setting exists)': '預設時薪（未設定個人薪資時套用）',
            'Current effective rule': '目前生效規則',
            'Grace period': '寬限期',
            'Reference working hours': '參考工時',
            'General': '一般',
            'hours': '小時',
            'minutes': '分鐘',
            'Per instance': '每次',
            'No deduction': '不扣款',
            'Default hourly rate': '預設時薪',
            'No rule exists yet. Please create the first version.': '尚未建立規則，請先建立第一個版本。',
            'Holiday maintenance': '假日維護',
            'Add/Update': '新增/更新',
            'No holidays have been set for this month yet.': '本月尚未設定假日。',
            'Show holidays older than six months': '顯示六個月前的假日',
            'Hide holidays older than six months': '隱藏六個月前的假日',
            'Older than six months before today are hidden by default.': '系統預設會隱藏今天往前六個月以前的假日。',
            'No allowance items yet.': '目前沒有津貼項目。',
            'Salary rules and settings': '薪資規則與設定',
            'Checking...': '檢查中…',
            'Recheck': '重新檢查',
            'Check failed': '檢查失敗',
            'Processing...': '處理中…',
            'API request failed. Please confirm the BioLife connection.': 'API 請求失敗，請確認 BioLife 連線',
            'Are you sure you want to deactivate these': '確認要停用這',
            'accounts': '個帳號',
            'This action cannot be undone.': '此操作不可逆。',
            'Deactivated': '已停用',
            'Deactivation failed': '停用失敗',
            'items': '筆',
            'Salary rules and employee salary settings': '薪資規則與員工薪資設定',
            'Salary structure settings': '薪資結構設定',
            'Tip: use Tab to move between fields and Ctrl+Enter to save the active row.': '提示：可用 Tab 在欄位間移動，使用 Ctrl+Enter 儲存目前列。',
            'Off Request': '排休申請',
            'Off Request Management': '排休管理',
            'Clock Record': '打卡記錄',
            'Clock Record Inquiry': '打卡記錄查詢',
            'Current month': '當月',
            'Last month': '上個月',
            'Custom date': '自訂日期',
            'Select employee (admin feature)': '選擇員工（管理員功能）',
            'My records': '我的紀錄',
            'Show daily summary': '顯示每日統計',
            'Select date range': '選擇日期範圍',
            'Start date': '開始日期',
            'End date': '結束日期',
            'Cancel': '取消',
            'Confirm': '確定',
            'Loading...': '載入中...',
            'No data': '無資料',
            'No clock-in records': '無打卡紀錄',
            'No records found or insufficient permissions': '查無紀錄或權限不足',
            'Working Shift': '班表',
            'Front Desk': '前台',
            'Restaurant': '餐廳',
            'Housekeeping': '房務',
            'Accountant': '會計',
            'Edit': '編輯',
            'Manage Shift Types': '管理班別',
            'Print': '列印',
            'Employees': '員工名單',
            'Shift Types (Filter)': '班別（篩選）',
            'Statistics (This View)': '統計（目前畫面）',
            'Schedule Comments': '班表備註',
            'Last Month': '上個月',
            'Name': '名稱',
            'Start Time': '開始時間',
            'End Time': '結束時間',
            'Color': '顏色',
            'My Schedule': '我的班表',
            'Show All': '顯示全部',
            'Remove shift?': '移除班次？',
            'Please create a shift type first.': '請先建立班別。',
            'Error saving schedule': '儲存班表時發生錯誤',
            'Comment saved': '備註已儲存',
            'No comment found last month': '上個月沒有備註',
            'Month': '月份',
            'Date': '日期',
            'Note': '備註',
            'Minimum count': '最少人數',
            'Shift': '班別',
            'No rules yet': '尚無規則',
            "Overview of this month's off requests": '本月排休申請總覽',
            'There are no off requests this month.': '本月尚無排休申請。',
            'Minimum staffing rules': '排班最低人數規則',
            'Set the minimum number of staff required for each department and shift per day.': '設定各部門、各班別每日最少需要幾人在班。',
            'Select Organization': '選擇組織',
            'Select Department': '選擇部門',
            'First Name': '姓氏',
            'Last Name': '名稱',
            'National ID': '身分證字號',
            'Phone Number': '電話號碼',
            'First name and last name are required.': '姓氏與名稱為必填。',
            'Click dates to request or cancel off-request': '點擊日期申請／取消排休',
            'My requests': '我的申請',
            'After the 28th of each month, requests for the next month are no longer accepted.': '每月 28 日後不接受下個月排休申請',
            'No requests yet': '尚無申請',
            'Operation failed': '操作失敗',
            'also has an off-request submitted by': '同時也有',
            'Select employee': '選擇員工',
            'No data available': '無可用資料',
            'Filter by title': '標題篩選',
            'Filter by type': '類型篩選',
            'Filter by creator': '建立者篩選',
            'Open the full user list and edit account details.': '開啟完整使用者清單並編輯帳號資料。',
        },
        'en_US': {},
        'ja_JP': {
            'HomePage': 'ホームページ',
            'Homepage': 'ホームページ',
            'System Setting': 'システム設定',
            'Approval': '承認',
            'User': 'ユーザー',
            'Accountant': '経理',
            'Staff Management': 'スタッフ管理',
            'Utilities': 'ユーティリティ',
            'Language': '言語',
            'Personal Profile': '個人情報',
            'Logout': 'ログアウト',
            'Salary Calculate': '給与試算',
            'Salary Rules': '給与ルール',
            'Salary Structure': '給与構造',
            'Rule name': 'ルール名',
            'Monthly overtime multiplier': '月給残業倍率',
            'Hourly overtime multiplier': '時給残業倍率',
            'Holiday multiplier': '祝日倍率',
            'Late grace (minutes)': '遅刻猶予（分）',
            'Early leave grace (minutes)': '早退猶予（分）',
            'Reference working hours (general)': '基準労働時間（一般）',
            'Reference working hours (manager)': '基準労働時間（管理職）',
            'Late deduction per instance (optional, leave blank to skip)': '遅刻ごとの控除（任意、空欄で無効）',
            'Actual deduction = this amount × number of late arrivals this month': '実際の控除 = この金額 × 今月の遅刻回数',
            'Default hourly rate (applies when no salary setting exists)': 'デフォルト時給（個別設定がない場合）',
            'Current effective rule': '現在有効なルール',
            'Grace period': '猶予時間',
            'Reference working hours': '基準労働時間',
            'General': '一般',
            'hours': '時間',
            'minutes': '分',
            'Per instance': '1回ごと',
            'No deduction': '控除なし',
            'Default hourly rate': 'デフォルト時給',
            'No rule exists yet. Please create the first version.': 'まだルールがありません。最初のバージョンを作成してください。',
            'Holiday maintenance': '祝日管理',
            'Add/Update': '追加/更新',
            'No holidays have been set for this month yet.': '今月の祝日はまだ設定されていません。',
            'Show holidays older than six months': '6か月より前の祝日を表示',
            'Hide holidays older than six months': '6か月より前の祝日を非表示',
            'Older than six months before today are hidden by default.': '本日から6か月より前の祝日は既定で非表示です。',
            'Search': '検索',
            'Save': '保存',
            'Delete': '削除',
            'Add': '追加',
            'Employee': '従業員',
            'Department': '部署',
            'Role': '役割',
            'Salary type': '給与タイプ',
            'Monthly': '月給',
            'Hourly': '時給',
            'Off Request': '休暇申請',
            'Off Request Management': '休暇申請管理',
            'Clock Record': '打刻記録',
            'Clock Record Inquiry': '打刻記録照会',
            'Current month': '今月',
            'Last month': '先月',
            'Custom date': 'カスタム日付',
            'Select employee (admin feature)': '従業員を選択（管理者機能）',
            'My records': '自分の記録',
            'Show daily summary': '日次サマリーを表示',
            'Select date range': '日付範囲を選択',
            'Start date': '開始日',
            'End date': '終了日',
            'Cancel': 'キャンセル',
            'Confirm': '確認',
            'Loading...': '読み込み中...',
            'No data': 'データなし',
            'No clock-in records': '打刻記録なし',
            'No records found or insufficient permissions': '記録が見つからないか、権限が不足しています',
            'Working Shift': '勤務シフト',
            'Front Desk': 'フロントデスク',
            'Restaurant': 'レストラン',
            'Housekeeping': 'ハウスキーピング',
            'Accountant': '経理',
            'Edit': '編集',
            'Deactivate': '無効化',
            'Batch processing': '一括処理',
            'End batch processing': '一括処理を終了',
            'Batch deactivate': '一括無効化',
            'Batch delete': '一括削除',
            'Select all': 'すべて選択',
            'Confirm action': '操作の確認',
            'Confirm account deactivation': 'アカウント無効化の確認',
            'Confirm account deletion': 'アカウント削除の確認',
            'Please select at least one account.': 'アカウントを1つ以上選択してください。',
            'The account will no longer be able to log in after deactivation.': '無効化すると、このアカウントはログインできなくなります。',
            'Deletion cannot be undone. If the account has related data, deletion will be rejected.': '削除は元に戻せません。関連データがある場合、削除は拒否されます。',
            'Account': 'アカウント',
            '%(count)s accounts selected.': '%(count)s 件のアカウントを選択しました。',
            'Confirm deactivate': '無効化を確認',
            'Confirm delete': '削除を確認',
            'Manage Shift Types': 'シフト種別を管理',
            'Print': '印刷',
            'Employees': '従業員',
            'Shift Types (Filter)': 'シフト種別（フィルター）',
            'Statistics (This View)': '統計（この表示）',
            'Schedule Comments': 'スケジュールコメント',
            'Last Month': '先月',
            'Name': '名前',
            'Start Time': '開始時間',
            'End Time': '終了時間',
            'Color': '色',
            'My Schedule': '自分のスケジュール',
            'Show All': 'すべて表示',
            'Remove shift?': 'シフトを削除しますか？',
            'Please create a shift type first.': 'まずシフト種別を作成してください。',
            'Error saving schedule': 'スケジュール保存エラー',
            'Comment saved': 'コメントを保存しました',
            'No comment found last month': '先月のコメントはありません',
            'Month': '月',
            'Date': '日付',
            'Note': '備考',
            'Minimum count': '最低人数',
            'Shift': 'シフト',
            'No rules yet': 'まだルールがありません',
            "Overview of this month's off requests": '今月の休暇申請の概要',
            'There are no off requests this month.': '今月は休暇申請がありません。',
            'Minimum staffing rules': '最低人員ルール',
            'Set the minimum number of staff required for each department and shift per day.': '各部署・各シフトごとに、1日あたり最低何人必要かを設定します。',
            'Select Organization': '組織を選択',
            'Select Department': '部署を選択',
            'First Name': '名',
            'Last Name': '姓',
            'National ID': '身分証番号',
            'Phone Number': '電話番号',
            'First name and last name are required.': '名と姓は必須です。',
            'Click dates to request or cancel off-request': '日付をクリックして、休暇申請の追加・取消を行います',
            'My requests': '自分の申請',
            'After the 28th of each month, requests for the next month are no longer accepted.': '毎月28日以降は、翌月の休暇申請を受け付けません。',
            'No requests yet': 'まだ申請はありません',
            'Operation failed': '操作に失敗しました',
            'also has an off-request submitted by': '次のメンバーも申請しました',
            'Select employee': '従業員を選択',
            'No data available': '利用できるデータがありません',
            'Filter by title': 'タイトルで絞り込み',
            'Filter by type': '種類で絞り込み',
            'Filter by creator': '作成者で絞り込み',
            'Open the full user list and edit account details.': 'ユーザー一覧を開き、アカウント情報を編集します。',
        },
    }
    mapping = fallback_map.get(locale, fallback_map['zh_TW'])
    translated_message = mapping.get(message, babel_gettext(message))

    if kwargs:
        try:
            return translated_message % kwargs
        except (KeyError, TypeError, ValueError):
            return translated_message

    if args:
        try:
            return translated_message % args
        except (KeyError, TypeError, ValueError):
            return translated_message

    return translated_message


def get_locale():
    return session.get('locale', 'zh_TW')


babel = Babel(app, locale_selector=get_locale)
app.jinja_env.globals['_'] = translate_text
app.jinja_env.globals['gettext'] = translate_text
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

    locale = session.get('locale', 'zh_TW')
    translations = {
        'zh_TW': {
            'language': '語言',
            'personal_profile': '個人資料',
            'logout': '登出',
            'salary_rules': '薪資規則',
            'salary_structure': '薪資結構',
            'salary_calculate': '薪資試算',
            'back_to_salary_rules': '返回薪資規則',
            'search': '搜尋',
            'save': '儲存',
            'delete': '刪除',
            'add': '新增',
            'employee': '員工',
            'department': '部門',
            'role': '角色',
            'salary_type': '薪資型態',
            'monthly': '月薪',
            'hourly': '時薪',
        },
        'en_US': {
            'language': 'Language',
            'personal_profile': 'Personal Profile',
            'logout': 'Logout',
            'salary_rules': 'Salary Rules',
            'salary_structure': 'Salary Structure',
            'salary_calculate': 'Salary Calculate',
            'back_to_salary_rules': 'Back to salary rules',
            'search': 'Search',
            'save': 'Save',
            'delete': 'Delete',
            'add': 'Add',
            'employee': 'Employee',
            'department': 'Department',
            'role': 'Role',
            'salary_type': 'Salary type',
            'monthly': 'Monthly',
            'hourly': 'Hourly',
        },
        'ja_JP': {
            'language': '言語',
            'personal_profile': '個人情報',
            'logout': 'ログアウト',
            'salary_rules': '給与ルール',
            'salary_structure': '給与構造',
            'salary_calculate': '給与計算',
            'back_to_salary_rules': '給与ルールへ戻る',
            'search': '検索',
            'save': '保存',
            'delete': '削除',
            'add': '追加',
            'employee': '従業員',
            'department': '部署',
            'role': '役割',
            'salary_type': '給与タイプ',
            'monthly': '月給',
            'hourly': '時給',
        },
    }
    current = translations.get(locale, translations['zh_TW'])

    return {
        'username': username,
        'csrf_token': get_csrf_token(),
        'pending_approval_count': pending_approval_count,
        'app_version': APP_VERSION,
        'locale': locale,
        't': current,
    }


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
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
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


APP_VERSION = '6.0.0'


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
    return endpoint in {'w_menu', 'w_menu_test', 'healthz', 'static'} or endpoint.startswith('auth.login') or endpoint.startswith('auth.logout') or endpoint.startswith('auth.register')


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


def _decimal_or_zero(value):
    return parse_decimal(value, Decimal('0')) or Decimal('0')


def _coerce_date(value):
    if hasattr(value, 'date'):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return value
    return value


def load_salary_attendance_groups(profile, year_month):
    start_date, end_date = month_range(year_month)
    pin = str(profile.get('clock_id') or '').strip()
    if not pin.isdigit():
        return {}

    # ±1 day buffer so night-shift clock-outs on the 1st of next month are captured.
    att_logs = client.get_att_logs(pin, start_date - timedelta(days=1), end_date + timedelta(days=1))
    items = ((att_logs or {}).get('result') or {}).get('items') or []
    parsed = [parse_att_dt(item.get('attLogTime', '')) for item in items]
    parsed = [dt for dt in parsed if dt is not None]
    parsed.sort()

    month_start = start_date.date()
    month_end = end_date.date()
    all_groups = smart_group_punches(parsed)
    return {d: v for d, v in all_groups.items() if month_start <= d <= month_end}


def build_salary_result_for_user(profile, year_month, rule, holiday_date_set, day_groups=None):
    start_date, end_date = month_range(year_month)
    pin = str(profile.get('clock_id') or '').strip()
    if not pin.isdigit():
        return None

    if day_groups is None:
        day_groups = load_salary_attendance_groups(profile, year_month)

    role_id = int(profile.get('role_id') or 3)
    regular_hours = Decimal(str(rule['regular_hours_manager'])) if role_id in [0, 1, 2, 4, 99] else Decimal(str(rule['regular_hours_staff']))
    break_minutes = 60 if role_id in [0, 1, 2, 4, 99] else 30
    paid_regular_minutes = int((regular_hours * Decimal('60')).quantize(Decimal('1'))) - break_minutes
    grace_late = int(rule['grace_late_minutes'])
    grace_early = int(rule['grace_early_minutes'])

    # Pre-fetch all scheduled shifts for the month to avoid per-day DB calls.
    schedules_by_date = db.get_user_schedules_in_range(profile['user_id'], start_date, end_date)
    day_rate_overrides = {
        item['work_date'].date() if hasattr(item['work_date'], 'date') else item['work_date']: item['rate']
        for item in db.get_salary_day_rate_overrides(profile['user_id'], start_date.date(), end_date.date())
    }

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
    weekday_hourly_rate = parse_decimal(profile.get('weekday_hourly_rate'), None)
    holiday_hourly_rate = parse_decimal(profile.get('holiday_hourly_rate'), None)
    professional_allowance = parse_decimal(profile.get('professional_allowance'), Decimal('0'))
    position_allowance = parse_decimal(profile.get('position_allowance'), Decimal('0'))
    base_salary_amount = parse_decimal(profile.get('base_salary_amount'), Decimal('0'))
    sales_allowance = parse_decimal(profile.get('sales_allowance'), Decimal('0'))
    overtime_allowance = parse_decimal(profile.get('overtime_allowance'), Decimal('0'))
    night_shift_allowance = parse_decimal(profile.get('night_shift_allowance'), Decimal('0'))
    special_leave_allowance = parse_decimal(profile.get('special_leave_allowance'), Decimal('0'))
    # Fall back to default hourly rate when no salary is configured.
    if salary_type == 'hourly' and (hourly_rate is None or hourly_rate == Decimal('0')):
        hourly_rate = weekday_hourly_rate or holiday_hourly_rate or default_rate
        salary_type = 'hourly'
    elif salary_type == 'monthly' and (monthly_salary is None or monthly_salary == Decimal('0')):
        hourly_rate = weekday_hourly_rate or holiday_hourly_rate or default_rate
        salary_type = 'hourly'
        monthly_salary = Decimal('0')
    hourly_rate = hourly_rate or Decimal('0')
    monthly_salary = monthly_salary or Decimal('0')
    weekday_hourly_rate = weekday_hourly_rate or hourly_rate
    holiday_hourly_rate = holiday_hourly_rate or hourly_rate
    hourly_overtime_multiplier = parse_decimal(rule['overtime_hourly_multiplier'], Decimal('1.5'))
    monthly_overtime_multiplier = parse_decimal(rule['overtime_monthly_multiplier'], Decimal('1.33'))
    holiday_multiplier = parse_decimal(rule['holiday_multiplier'], Decimal('2.0'))

    base_pay = Decimal('0')
    overtime_pay = Decimal('0')
    holiday_pay = Decimal('0')

    if salary_type == 'hourly':
        regular_pay = Decimal('0')
        for day_key, punches in day_groups.items():
            if len(punches) < 2:
                continue
            work_minutes = max(0, int((punches[-1] - punches[0]).total_seconds() // 60))
            if day_key in holiday_date_set:
                override_rate = day_rate_overrides.get(day_key)
                day_rate = parse_decimal(override_rate, None) or holiday_hourly_rate
                holiday_pay += (day_rate * holiday_multiplier * Decimal(work_minutes) / Decimal('60'))
            else:
                day_regular = min(work_minutes, max(0, paid_regular_minutes))
                day_overtime = max(0, work_minutes - day_regular)
                override_rate = day_rate_overrides.get(day_key)
                day_rate = parse_decimal(override_rate, None) or weekday_hourly_rate
                regular_pay += (day_rate * Decimal(day_regular) / Decimal('60'))
                overtime_pay += (day_rate * hourly_overtime_multiplier * Decimal(day_overtime) / Decimal('60'))
        base_pay = regular_pay
    else:
        base_pay = monthly_salary
        # Monthly-based overtime reference hourly rate based on 30 days * regular paid minutes.
        ref_minutes = max(1, paid_regular_minutes * 30)
        monthly_hourly = monthly_salary / (Decimal(ref_minutes) / Decimal('60'))
        overtime_pay = (monthly_hourly * monthly_overtime_multiplier * Decimal(overtime_minutes) / Decimal('60'))
        holiday_pay = (monthly_hourly * holiday_multiplier * Decimal(holiday_minutes) / Decimal('60'))

    fixed_allowances = professional_allowance + position_allowance + base_salary_amount + sales_allowance + overtime_allowance + night_shift_allowance + special_leave_allowance
    # For monthly staff, monthly_salary is the computed total of base salary and
    # fixed allowances saved by the salary-structure page. Do not add them twice.
    fixed_salary_total = fixed_allowances if salary_type == 'hourly' else Decimal('0')
    gross_salary = base_pay + overtime_pay + holiday_pay + fixed_salary_total
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
        'weekday_hourly_rate': float(weekday_hourly_rate.quantize(Decimal('0.01'))) if weekday_hourly_rate is not None else None,
        'holiday_hourly_rate': float(holiday_hourly_rate.quantize(Decimal('0.01'))) if holiday_hourly_rate is not None else None,
        'professional_allowance': float(professional_allowance.quantize(Decimal('0.01'))),
        'position_allowance': float(position_allowance.quantize(Decimal('0.01'))),
        'base_salary_amount': float(base_salary_amount.quantize(Decimal('0.01'))),
        'sales_allowance': float(sales_allowance.quantize(Decimal('0.01'))),
        'overtime_allowance': float(overtime_allowance.quantize(Decimal('0.01'))),
        'night_shift_allowance': float(night_shift_allowance.quantize(Decimal('0.01'))),
        'special_leave_allowance': float(special_leave_allowance.quantize(Decimal('0.01'))),
        'base_pay': float(base_pay.quantize(Decimal('0.01'))),
        'overtime_pay': float(overtime_pay.quantize(Decimal('0.01'))),
        'holiday_pay': float(holiday_pay.quantize(Decimal('0.01'))),
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

    day_rate_overrides = {
        item['work_date'].date() if hasattr(item['work_date'], 'date') else item['work_date']: item['rate']
        for item in db.get_salary_day_rate_overrides(profile['user_id'], start_date.date(), end_date.date())
    }

    # Both the daily detail and summary must use the same BioLife response snapshot.
    day_groups = load_salary_attendance_groups(profile, year_month)

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
                'override_rate': float(parse_decimal(day_rate_overrides.get(day_key), Decimal('0')).quantize(Decimal('0.01')))
                if day_rate_overrides.get(day_key) is not None else None,
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
            'override_rate': float(parse_decimal(day_rate_overrides.get(day_key), Decimal('0')).quantize(Decimal('0.01')))
            if day_rate_overrides.get(day_key) is not None else None,
        })

    summary = build_salary_result_for_user(
        profile, year_month, rule, holiday_date_set, day_groups=day_groups
    )
    return {'daily': daily_rows, 'summary': summary}


def write_salary_excel_summary(ws, summary, start_row, sub_fill):
    """Write a two-band salary block constrained to columns A:H."""
    from openpyxl.styles import Alignment, Font

    bands = [
        [
            ('總工時(h)', round((summary.get('total_work_minutes') or 0) / 60, 2)),
            ('一般工時(h)', round((summary.get('regular_minutes') or 0) / 60, 2)),
            ('加班(h)', round((summary.get('overtime_minutes') or 0) / 60, 2)),
            ('假日(h)', round((summary.get('holiday_minutes') or 0) / 60, 2)),
            ('遲到次', summary.get('late_count', 0)),
            ('早退次', summary.get('early_count', 0)),
            ('遲到扣款', summary.get('late_deduction') or 0),
            ('應發', summary.get('gross_salary') or 0),
        ],
        [
            ('底薪', summary.get('base_salary_amount') or 0),
            ('專業加給', summary.get('professional_allowance') or 0),
            ('職務加給', summary.get('position_allowance') or 0),
            ('業務加給', summary.get('sales_allowance') or 0),
            ('加班加給', summary.get('overtime_allowance') or 0),
            ('夜班加給', summary.get('night_shift_allowance') or 0),
            ('特休加給', summary.get('special_leave_allowance') or 0),
            ('實發', summary.get('net_salary') or 0),
        ],
    ]

    for band_index, items in enumerate(bands):
        header_row = start_row + band_index * 2
        value_row = header_row + 1
        for column, (label, value) in enumerate(items, start=1):
            header_cell = ws.cell(row=header_row, column=column, value=label)
            header_cell.fill = sub_fill
            header_cell.font = Font(bold=True)
            header_cell.alignment = Alignment(horizontal='center')

            value_cell = ws.cell(row=value_row, column=column, value=value)
            value_cell.alignment = Alignment(horizontal='right')
            value_cell.number_format = '#,##0.00'

    # Net pay stays in the same block, at its bottom-right corner, and is bold.
    ws.cell(row=start_row + 3, column=8).font = Font(bold=True)
    return start_row + 3


@app.route('/hr/salary/day-rate', methods=['POST'])
def hr_salary_day_rate():
    if not has_permission('hr_salary_calculate', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    data, error = read_json_dict()
    if error:
        return error

    user_id_raw = str(data.get('user_id', '')).strip()
    work_date = normalize_text(data.get('work_date', ''), 20)
    rate = parse_decimal(data.get('rate'), None)
    if not user_id_raw.isdigit() or not work_date or rate is None:
        return json_error('Invalid parameters', 400)

    try:
        datetime.strptime(work_date, '%Y-%m-%d')
    except ValueError:
        return json_error('Invalid work_date', 400)

    db.upsert_salary_day_rate_override(int(user_id_raw), work_date, rate, session.get('user_id'))
    return json_success({'saved': True})


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

        summary_start_row = ws.max_row + 2
        write_salary_excel_summary(ws, s, summary_start_row, sub_fill)

        from openpyxl.utils import get_column_letter
        for i in range(1, 9):
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
        if endpoint in {'auth.login', 'auth.logout'}:
            return None

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


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    logger.exception('Unhandled exception', exc_info=e)
    wants_json = (
        request.is_json
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
        or request.path.startswith('/api/')
    )
    if wants_json:
        return json_error(str(e), 500)
    return render_template('/utility/basic_page/error_page.html', error_message=str(e)), 500


@app.route('/healthz')
def healthz():
    return json_success({'status': 'ok'})


def _build_monthly_attendance_rows(pin, month_start, month_end):
    if not pin.isdigit():
        return []

    att_logs = client.get_att_logs(pin, month_start - timedelta(days=1), month_end + timedelta(days=1))
    items = ((att_logs or {}).get('result') or {}).get('items') or []
    rows = []
    for item in items:
        dt = parse_att_dt(item.get('attLogTime', ''))
        if dt is None:
            continue
        rows.append({
            'timestamp': dt,
            'time_text': dt.strftime('%Y-%m-%d %H:%M:%S'),
            'verify_name': item.get('verifyName', '') or 'Unknown'
        })
    rows.sort(key=lambda row: row['timestamp'], reverse=True)
    return rows


@app.route('/')
def homepage():
    user = db.get_user_by_id(session.get('user_id')) or {}
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1)
    month_end = datetime(now.year, now.month, calendar.monthrange(now.year, now.month)[1], 23, 59, 59)
    pin = str(user.get('clock_id') or '').strip()
    month_logs = _build_monthly_attendance_rows(pin, month_start, month_end)

    approval_filter = (request.args.get('approval_filter') or 'pending').strip()
    show_approval_block = bool(session.get('logged_in'))
    approval_documents = []
    approval_status_map = {1: '待處理', 2: '已核可', 3: '已退回', 4: '已刪除'}
    if show_approval_block and has_permission(
        'p_list', session.get('user_id'), session.get('team_id'), session.get('role_id')
    ):
        if approval_filter == 'approved':
            approval_documents = [doc for doc in db.get_30days_doc(session.get('user_id')) if getattr(doc, 'status', 0) == 2]
        elif approval_filter == 'all':
            approval_documents = db.get_30days_doc(session.get('user_id'))
        else:
            approval_documents = db.get_unapproved_doc_by_user(session.get('user_id'))

    return render_template(
        'homepage.html',
        user=user,
        month_logs=month_logs,
        month_label=now.strftime('%Y-%m'),
        show_approval_block=show_approval_block,
        approval_filter=approval_filter,
        approval_documents=approval_documents,
        approval_status_map=approval_status_map
    )


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
    next_month_start = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    next_month_end = (next_month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if today.day > 27 or not (next_month_start <= req_date <= next_month_end):
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

@app.route('/hr/salary/structure', methods=['GET', 'POST'])
def hr_salary_structure():
    if not has_permission('hr_salary_rules_manage', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    active_rule = db.get_active_salary_rule()
    default_hourly_rate = parse_decimal((active_rule or {}).get('default_hourly_rate'), Decimal('200')) or Decimal('200')

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'upsert_structure':
            user_id_raw = normalize_text(request.form.get('user_id'), 20)
            if not user_id_raw.isdigit():
                flash('員工編號格式錯誤', category='danger')
                return redirect(url_for('hr_salary_structure'))

            user_id = int(user_id_raw)
            salary_type = normalize_text(request.form.get('salary_type'), 20) or 'monthly'
            monthly_salary = parse_decimal(request.form.get('monthly_salary'), None)
            hourly_salary = parse_decimal(request.form.get('hourly_salary'), None)
            weekday_hourly_rate = parse_decimal(request.form.get('weekday_hourly_rate'), None)
            holiday_hourly_rate = parse_decimal(request.form.get('holiday_hourly_rate'), None)
            selected_allowance_item_ids = request.form.getlist('professional_allowance_item_ids')
            selected_allowance_items = db.get_professional_allowance_items_by_ids(selected_allowance_item_ids)
            professional_allowance = sum(
                (parse_decimal(item.get('amount'), Decimal('0')) for item in selected_allowance_items),
                Decimal('0')
            )
            position_allowance = parse_decimal(request.form.get('position_allowance'), Decimal('0'))
            base_salary_amount = parse_decimal(request.form.get('base_salary_amount'), Decimal('0'))
            sales_allowance = parse_decimal(request.form.get('sales_allowance'), Decimal('0'))
            overtime_allowance = parse_decimal(request.form.get('overtime_allowance'), Decimal('0'))
            night_shift_allowance = parse_decimal(request.form.get('night_shift_allowance'), Decimal('0'))
            special_leave_allowance = parse_decimal(request.form.get('special_leave_allowance'), Decimal('0'))

            fixed_allowance_total = (
                professional_allowance + position_allowance + base_salary_amount +
                sales_allowance + overtime_allowance + night_shift_allowance + special_leave_allowance
            )

            if salary_type == 'hourly':
                if hourly_salary is None or hourly_salary <= Decimal('0'):
                    hourly_salary = default_hourly_rate
                weekday_hourly_rate = hourly_salary
                holiday_hourly_rate = hourly_salary
                monthly_salary = None
            else:
                monthly_salary = fixed_allowance_total
                hourly_salary = None
                weekday_hourly_rate = None
                holiday_hourly_rate = None

            db.upsert_salary_structure_row(
                user_id=user_id,
                salary_type=salary_type,
                monthly_salary=monthly_salary,
                hourly_salary=hourly_salary,
                weekday_hourly_rate=weekday_hourly_rate,
                holiday_hourly_rate=holiday_hourly_rate,
                professional_allowance=professional_allowance,
                position_allowance=position_allowance,
                base_salary_amount=base_salary_amount,
                sales_allowance=sales_allowance,
                overtime_allowance=overtime_allowance,
                night_shift_allowance=night_shift_allowance,
                special_leave_allowance=special_leave_allowance,
                updated_by=session.get('user_id')
            )
            db.upsert_user_professional_allowance_items(
                user_id=user_id,
                item_ids=selected_allowance_item_ids,
                updated_by=session.get('user_id')
            )
            flash('薪資結構已更新', category='success')
            return redirect(url_for('hr_salary_structure'))

        return redirect(url_for('hr_salary_structure'))

    query_text = normalize_text(request.args.get('q', ''), 100)
    team_ids = [int(value) for value in request.args.getlist('team_id') if str(value).isdigit()]
    role_ids = [int(value) for value in request.args.getlist('role_id') if str(value).isdigit()]
    rows = db.get_salary_structure_rows(
        query_text=query_text or None,
        team_id=team_ids or None,
        role_id=role_ids or None
    )
    allowance_items = db.get_professional_allowance_items()
    selected_item_map = db.get_user_professional_allowance_map([row['user_id'] for row in rows])
    for row in rows:
        allowances_total = (
            parse_decimal(row.get('professional_allowance'), Decimal('0')) +
            parse_decimal(row.get('position_allowance'), Decimal('0')) +
            parse_decimal(row.get('base_salary_amount'), Decimal('0')) +
            parse_decimal(row.get('sales_allowance'), Decimal('0')) +
            parse_decimal(row.get('overtime_allowance'), Decimal('0')) +
            parse_decimal(row.get('night_shift_allowance'), Decimal('0')) +
            parse_decimal(row.get('special_leave_allowance'), Decimal('0'))
        )
        row['computed_monthly_salary'] = float(allowances_total.quantize(Decimal('0.01')))

        effective_hourly = (
            parse_decimal(row.get('hourly_salary'), None) or
            parse_decimal(row.get('weekday_hourly_rate'), None) or
            parse_decimal(row.get('holiday_hourly_rate'), None) or
            default_hourly_rate
        )
        row['effective_hourly_salary'] = float(effective_hourly.quantize(Decimal('0.01')))
        row['effective_weekday_hourly_rate'] = float(effective_hourly.quantize(Decimal('0.01')))
        row['effective_holiday_hourly_rate'] = float(effective_hourly.quantize(Decimal('0.01')))
        row['selected_professional_allowance_item_ids'] = selected_item_map.get(int(row['user_id']), [])

    teams = db.get_teams()
    roles = db.get_roles()
    return render_template('/utility/hr/hr_salary_structure.html', rows=rows, teams=teams, roles=roles,
                           allowance_items=allowance_items,
                           q=query_text, team_ids=team_ids, role_ids=role_ids)


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
            weekday_hourly_rate = parse_decimal(request.form.get('weekday_hourly_rate'), None)
            holiday_hourly_rate = parse_decimal(request.form.get('holiday_hourly_rate'), None)
            professional_allowance = parse_decimal(request.form.get('professional_allowance'), Decimal('0'))
            position_allowance = parse_decimal(request.form.get('position_allowance'), Decimal('0'))
            base_salary_amount = parse_decimal(request.form.get('base_salary_amount'), Decimal('0'))
            sales_allowance = parse_decimal(request.form.get('sales_allowance'), Decimal('0'))
            overtime_allowance = parse_decimal(request.form.get('overtime_allowance'), Decimal('0'))
            night_shift_allowance = parse_decimal(request.form.get('night_shift_allowance'), Decimal('0'))
            special_leave_allowance = parse_decimal(request.form.get('special_leave_allowance'), Decimal('0'))
            before = db.get_user_salary_profile(user_id)
            db.upsert_salary_profile(user_id, salary_type, monthly_salary, hourly_salary, weekday_hourly_rate,
                                     holiday_hourly_rate, professional_allowance, position_allowance,
                                     base_salary_amount, sales_allowance, overtime_allowance,
                                     night_shift_allowance, special_leave_allowance, session.get('user_id'))
            after = db.get_user_salary_profile(user_id)
            write_audit('salary_profile', user_id, 'upsert', before, after)
            flash('員工薪資設定已更新', category='success')

        elif action == 'upsert_allowance_item':
            item_id = request.form.get('item_id') or None
            name = normalize_text(request.form.get('name'), 100)
            amount = parse_decimal(request.form.get('amount'), Decimal('0'))
            note = normalize_text(request.form.get('note'), 200)
            if not name:
                flash('專業加給名稱不可為空', category='danger')
                return redirect('/hr/salary/ma')
            db.upsert_professional_allowance_item(item_id, name, amount, note, session.get('user_id'))
            flash('專業加給項目已更新', category='success')

        elif action == 'delete_allowance_item':
            item_id = request.form.get('item_id')
            if item_id:
                db.delete_professional_allowance_item(item_id)
                flash('專業加給項目已刪除', category='success')

        elif action == 'upsert_holiday':
            original_holiday_date = normalize_text(request.form.get('original_holiday_date'), 20)
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

            if original_holiday_date and original_holiday_date != holiday_date:
                db.delete_holiday(original_holiday_date, 'TW')

            db.upsert_holiday(holiday_date, holiday_name, 'TW', session.get('user_id'))
            write_audit('holiday_calendar', holiday_date, 'upsert', None,
                        {'holiday_date': holiday_date, 'holiday_name': holiday_name})
            flash('國定假日已更新', category='success')

        elif action == 'delete_holiday':
            holiday_date = normalize_text(request.form.get('holiday_date'), 20)
            if not holiday_date:
                flash('假日日期不可為空', category='danger')
                return redirect('/hr/salary/ma')
            db.delete_holiday(holiday_date, 'TW')
            write_audit('holiday_calendar', holiday_date, 'delete', None,
                        {'holiday_date': holiday_date})
            flash('國定假日已刪除', category='success')

        return redirect('/hr/salary/ma')

    run_holiday_sync_if_needed(datetime.now().date(), session.get('user_id') or 1)
    rule = db.get_active_salary_rule()
    allowance_items = db.get_professional_allowance_items()
    holiday_month = datetime.now().strftime('%Y-%m')
    today = datetime.now().date()
    six_months_ago = subtract_months(today, 6)
    all_holidays = db.get_holidays_all('TW')

    # If no holiday data exists at all, bootstrap with current and next year.
    if not all_holidays:
        try:
            sync_tw_holidays_for_year(today.year, session.get('user_id') or 1)
            sync_tw_holidays_for_year(today.year + 1, session.get('user_id') or 1)
            all_holidays = db.get_holidays_all('TW')
        except Exception as exc:
            logger.warning('Holiday bootstrap failed: error=%s', exc)

    holidays = []
    hidden_holidays = []
    for item in all_holidays:
        holiday_date = item.get('holiday_date')
        if hasattr(holiday_date, 'date'):
            holiday_date = holiday_date.date()
        if holiday_date and holiday_date < six_months_ago:
            hidden_holidays.append(item)
        else:
            holidays.append(item)

    return render_template('/utility/hr/hr_salary_ma.html', rule=rule,
                           allowance_items=allowance_items, holiday_month=holiday_month,
                           holidays=holidays, hidden_holidays=hidden_holidays,
                           six_months_ago=six_months_ago)


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
        run_holiday_sync_if_needed(datetime.now().date(), 1)

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
