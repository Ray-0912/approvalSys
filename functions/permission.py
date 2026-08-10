# Team: 0= Management, 1= Accounting, 2= FrontDesk, 3= HouseKeeping, 4= Works, 99= SysSupervisor
# Role: 0= Director, 1= Manager, 2= Mid-Manager, 3= Staff, 4= Accountant, 99= SysSupervisor

from database import get_db_connection


PERMISSION_KEYS = [
    'reset_password', 'p_list', 'p_edit', 'p_new', 'p_view',
    'hr_view_cross_department', 'hr_salary_calculate', 'hr_salary_rules_manage',
    'hr_new_member_manage', 'sys_settings_manage', 'role_permission_manage',
    'salary_submit', 'salary_approve'
]

PERMISSION_CATALOG = {
    'reset_password': {
        'label': 'Reset password',
        'route': '/sys/users',
        'purpose': 'Allows an administrator to reset another user password.',
        'typical_roles': ['99']
    },
    'p_list': {
        'label': 'Approval list',
        'route': '/p/list',
        'purpose': 'Shows the approval list that can be reviewed and processed.',
        'typical_roles': ['99', '0', '1', '2', '4']
    },
    'p_edit': {
        'label': 'Edit approval',
        'route': '/p/edit/<id>',
        'purpose': 'Allows editing an approval before it is submitted or approved.',
        'typical_roles': ['99', '0', '1', '2']
    },
    'p_new': {
        'label': 'Create approval',
        'route': '/p/new',
        'purpose': 'Enables creating a new approval request.',
        'typical_roles': ['99', '0', '1', '2', '4']
    },
    'p_view': {
        'label': 'View approval',
        'route': '/p/view/<id>',
        'purpose': 'Allows opening the detail view for an approval.',
        'typical_roles': ['99', '0', '1', '2', '3', '4']
    },
    'hr_view_cross_department': {
        'label': 'Cross-department HR view',
        'route': '/hr/*',
        'purpose': 'Enables HR pages that look across departments.',
        'typical_roles': ['99', '0', '1', '2', '4']
    },
    'hr_salary_calculate': {
        'label': 'Salary simulation',
        'route': '/hr/salary/cal',
        'purpose': 'Runs salary simulation and explores payroll detail.',
        'typical_roles': ['99', '0', '1', '2', '4']
    },
    'hr_salary_rules_manage': {
        'label': 'Salary rules management',
        'route': '/hr/salary/ma',
        'purpose': 'Maintains salary rule versions and salary-related settings.',
        'typical_roles': ['99', '0', '4']
    },
    'hr_new_member_manage': {
        'label': 'Onboarding management',
        'route': '/hr/new',
        'purpose': 'Handles HR onboarding and member synchronization tasks.',
        'typical_roles': ['99', '0', '4']
    },
    'sys_settings_manage': {
        'label': 'System settings',
        'route': '/sys/settings',
        'purpose': 'Provides access to system configuration and maintenance features.',
        'typical_roles': ['99', '0']
    },
    'role_permission_manage': {
        'label': 'Role permissions',
        'route': '/sys/permissions',
        'purpose': 'Managed permission overrides for each role.',
        'typical_roles': ['99']
    },
    'salary_submit': {
        'label': 'Salary submission',
        'route': '/hr/salary/cal',
        'purpose': 'Lets a user submit salary calculation results for review.',
        'typical_roles': ['99', '0', '4']
    },
    'salary_approve': {
        'label': 'Salary approval',
        'route': '/hr/salary/cal',
        'purpose': 'Approves submitted salary calculations.',
        'typical_roles': ['99', '0', '1']
    }
}


DEFAULT_ROLE_PERMISSIONS = {
    99: {
        'reset_password', 'p_list', 'p_edit', 'p_new', 'p_view',
        'hr_view_cross_department', 'hr_salary_calculate', 'hr_salary_rules_manage',
        'hr_new_member_manage', 'sys_settings_manage', 'role_permission_manage',
        'salary_submit', 'salary_approve'
    },
    0: {
        'p_list', 'p_edit', 'p_new', 'p_view',
        'hr_view_cross_department', 'hr_salary_calculate', 'salary_approve',
        'sys_settings_manage', 'role_permission_manage'
    },
    1: {
        'p_list', 'p_edit', 'p_new', 'p_view',
        'hr_view_cross_department', 'hr_salary_calculate', 'salary_approve'
    },
    2: {
        'p_list', 'p_edit', 'p_new', 'p_view',
        'hr_view_cross_department', 'hr_salary_calculate'
    },
    4: {
        'p_list', 'p_edit', 'p_new', 'p_view',
        'hr_view_cross_department', 'hr_salary_calculate', 'hr_salary_rules_manage',
        'hr_new_member_manage', 'salary_submit'
    },
    3: {'p_view'}
}


def _load_db_override_permissions(role_id):
    try:
        with get_db_connection() as connection:
            with connection.cursor(dictionary=True) as cursor:
                cursor.execute(
                    "SELECT permission_key, allowed FROM role_permissions WHERE role_id=%s",
                    (role_id,)
                )
                rows = cursor.fetchall()
    except Exception:
        return None

    if not rows:
        return None

    return {row['permission_key']: bool(int(row['allowed'])) for row in rows}


def get_effective_role_permissions(role_id):
    role_id = int(role_id)
    defaults = DEFAULT_ROLE_PERMISSIONS.get(role_id, set())
    overrides = _load_db_override_permissions(role_id) or {}

    permission_keys = sorted(set(defaults) | set(overrides.keys()))
    return {key: overrides.get(key, key in defaults) for key in permission_keys}


def get_effective_role_permission(role_id, permission_key):
    role_id = int(role_id)
    defaults = DEFAULT_ROLE_PERMISSIONS.get(role_id, set())
    overrides = _load_db_override_permissions(role_id) or {}
    return overrides.get(permission_key, permission_key in defaults)


def has_permission(page, user_id, user_team, user_role):
    if user_id == 1:
        return True

    role_id = int(user_role)
    return get_effective_role_permission(role_id, page)
