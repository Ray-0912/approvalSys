import json
import logging

from flask import Blueprint, abort, flash, redirect, render_template, request, session

import database.queries as db
import functions.permission as permission_module
from functions.permission import has_permission

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger('approval_system.admin')
PERMISSION_KEYS = [
    'reset_password', 'p_list', 'p_edit', 'p_new', 'p_view',
    'hr_view_cross_department', 'hr_salary_calculate', 'hr_salary_rules_manage',
    'hr_new_member_manage', 'sys_settings_manage', 'role_permission_manage',
    'salary_submit', 'salary_approve'
]


def normalize_text(value, max_len=255):
    if value is None:
        return ''
    value = str(value).strip()
    return value[:max_len]


@admin_bp.route('/sys/settings', methods=['GET'])
def sys_settings():
    if session.get('role_id') != 99:
        abort(403)
    users = db.get_active_users_with_roles()[:10]
    return render_template('/utility/sys/system_settings.html', users=users)


@admin_bp.route('/sys/audit-logs', methods=['GET'])
def sys_audit_logs():
    if session.get('role_id') != 99:
        abort(403)

    entity_type = normalize_text(request.args.get('entity_type'), 50) or None

    try:
        page_size = int(request.args.get('page_size', 25))
    except ValueError:
        page_size = 25
    page_size = max(10, min(page_size, 100))

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    page = max(1, page)

    total_count = db.get_audit_log_count(entity_type=entity_type)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * page_size
    logs = db.get_audit_logs(limit=page_size, offset=offset, entity_type=entity_type)

    return render_template(
        '/utility/sys/audit_logs.html',
        logs=logs,
        entity_type=entity_type or '',
        page_size=page_size,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
    )


@admin_bp.route('/sys/permissions', methods=['GET'])
def sys_permissions():
    if session.get('role_id') != 99:
        abort(403)

    roles = db.get_roles_simple()
    return render_template(
        '/utility/sys/role_permissions.html',
        roles=roles,
        selected_role=None,
        role_permissions={},
        permission_keys=PERMISSION_KEYS,
        permission_catalog=permission_module.PERMISSION_CATALOG,
    )


@admin_bp.route('/sys/permissions/<int:role_id>', methods=['GET', 'POST'])
def sys_permissions_role(role_id):
    if session.get('role_id') != 99:
        abort(403)

    if request.method == 'POST':
        permission_key = normalize_text(request.form.get('permission_key'), 100)
        allowed_raw = normalize_text(request.form.get('allowed'), 10)

        if permission_key not in PERMISSION_KEYS:
            flash('權限更新參數錯誤', category='danger')
            return redirect(f'/sys/permissions/{role_id}')

        allowed = allowed_raw in ['1', 'true', 'True', 'on', 'yes']
        before_map = db.get_role_permissions_map().get(role_id, {})
        before_val = before_map.get(permission_key)
        db.set_role_permission(role_id, permission_key, allowed, session.get('user_id'))
        after_map = db.get_role_permissions_map().get(role_id, {})
        after_val = after_map.get(permission_key)

        logger.info('Role permission updated: role_id=%s key=%s before=%s after=%s operator=%s',
                    role_id, permission_key, before_val, after_val, session.get('user_id'))
        flash('角色權限已更新', category='success')
        return redirect(f'/sys/permissions/{role_id}')

    roles = db.get_roles_simple()
    selected_role = next((role for role in roles if int(role['role_id']) == role_id), None)
    if not selected_role:
        abort(404)

    role_permissions = {
        key: permission_module.get_effective_role_permission(role_id, key)
        for key in PERMISSION_KEYS
    }
    return render_template(
        '/utility/sys/role_permissions.html',
        roles=roles,
        selected_role=selected_role,
        role_permissions=role_permissions,
        permission_keys=PERMISSION_KEYS,
        permission_catalog=permission_module.PERMISSION_CATALOG,
    )


@admin_bp.route('/sys/users', methods=['GET'])
def sys_users():
    if session.get('role_id') != 99:
        abort(403)

    query_text = normalize_text(request.args.get('q'), 100).lower()
    team_id = normalize_text(request.args.get('team_id'), 10)
    role_id = normalize_text(request.args.get('role_id'), 10)
    activation = normalize_text(request.args.get('activation', '1'), 10)

    try:
        page_size = int(request.args.get('page_size', 100))
    except ValueError:
        page_size = 100
    if page_size not in {50, 100}:
        page_size = 100

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    page = max(1, page)

    users = db.get_all_users_admin()
    if query_text:
        users = [
            user for user in users
            if query_text in str(user.get('username', '')).lower()
            or query_text in str(user.get('first_name', '')).lower()
            or query_text in str(user.get('last_name', '')).lower()
            or query_text in str(user.get('email', '')).lower()
            or query_text in str(user.get('role_name', '')).lower()
            or query_text in str(user.get('team_name', '')).lower()
        ]
    if team_id.isdigit():
        users = [user for user in users if str(user.get('team_id')) == team_id]
    if role_id.isdigit():
        users = [user for user in users if str(user.get('role_id')) == role_id]
    if activation in {'0', '1'}:
        users = [user for user in users if str(int(bool(user.get('activation')))) == activation]

    total_count = len(users)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    users = users[start_idx:end_idx]

    return render_template('/utility/sys/user_list.html', users=users, q=query_text,
                           teams=db.get_teams(), roles=db.get_roles(),
                           selected_team_id=team_id, selected_role_id=role_id,
                           selected_activation=activation,
                           page=page, page_size=page_size, total_pages=total_pages,
                           total_count=total_count)


@admin_bp.route('/sys/users/action', methods=['POST'])
def sys_users_action():
    if session.get('role_id') != 99:
        abort(403)

    action = normalize_text(request.form.get('action'), 20)
    raw_ids = request.form.getlist('user_ids')
    user_ids = sorted({int(value) for value in raw_ids if str(value).isdigit()})

    if action != 'deactivate' or not user_ids:
        flash('請選擇有效的使用者與操作', category='danger')
        return redirect('/sys/users')
    if int(session.get('user_id')) in user_ids:
        flash('不能停用或刪除目前登入的帳號', category='danger')
        return redirect('/sys/users')

    targets = db.get_users_by_ids(user_ids)
    if len(targets) != len(user_ids):
        flash('部分使用者不存在，操作已取消', category='danger')
        return redirect('/sys/users')
    if any(int(user.get('role_id') or 0) == 99 for user in targets):
        if db.count_active_system_admins_excluding(user_ids) < 1:
            flash('系統至少必須保留一位啟用中的系統管理員', category='danger')
            return redirect('/sys/users')

    try:
        affected = db.set_users_activation(user_ids, 0)
        action_label = '停用'
    except Exception:
        logger.exception('Admin user batch action failed: action=%s ids=%s', action, user_ids)
        flash('帳號停用失敗，請稍後再試', category='danger')
        return redirect('/sys/users')

    db.append_audit_log(
        entity_type='user', entity_id=','.join(str(value) for value in user_ids),
        action=f'batch_{action}', changed_by=session.get('user_id'), before_json=json.dumps(targets, default=str),
        after_json=json.dumps({'affected': affected, 'activation': 0}),
        ip_address=request.remote_addr, user_agent=str(request.user_agent)[:255]
    )
    flash(f'已{action_label} {affected} 個帳號', category='success')
    return redirect('/sys/users')


@admin_bp.route('/sys/user/edit/<user_id>', methods=['GET'])
def sys_user_edit(user_id):
    if session.get('role_id') != 99:
        abort(403)

    user = db.get_user_by_id(user_id)
    roles = db.get_roles()
    teams = db.get_teams()

    return render_template('/utility/sys/user_edit.html', user=user, roles=roles, teams=teams)


@admin_bp.route('/sys/user/save', methods=['POST'])
def sys_user_save():
    if session.get('role_id') != 99:
        abort(403)

    user_id = normalize_text(request.form.get('user_id'), 20)
    first_name = normalize_text(request.form.get('first_name'), 50)
    last_name = normalize_text(request.form.get('last_name'), 50)
    email = normalize_text(request.form.get('email'), 255)
    phone = normalize_text(request.form.get('phone'), 30)
    role_id = normalize_text(request.form.get('role_id'), 10)
    team_id = normalize_text(request.form.get('team_id'), 10)
    password = request.form.get('password')

    if not user_id.isdigit() or not first_name or not last_name:
        flash('使用者資料格式錯誤', category='danger')
        return redirect(request.referrer or '/sys/users')

    db.update_user_admin(user_id, first_name, last_name, email, phone, role_id, team_id, password)
    flash('使用者資料已更新', 'success')
    return redirect('/sys/users')
