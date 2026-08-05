import logging

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

import database.queries as db
from functions.permission import has_permission

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger('approval_system.auth')


def normalize_text(value, max_len=255):
    if value is None:
        return ''
    value = str(value).strip()
    return value[:max_len]


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = normalize_text(request.form.get('username'), 100)
        password = request.form.get('password', '')

        if not username or not password:
            flash('請輸入帳號與密碼', category='danger')
            return render_template('/utility/personal/login.html')

        if db.check_existing_username(username):
            user = db.verify_password(username, password)
            if user is not None:
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role_id'] = user[3]
                session['team_id'] = user[4]
                session['phone'] = user[5]
                session['email'] = user[6]
                session['first_name'] = user[7]
                session['last_name'] = user[8]
                session['clock_id'] = user[9]
                session['logged_in'] = True
                logger.info('Login success: username=%s user_id=%s role_id=%s', user[1], user[0], user[3])
                return redirect('/')

            logger.warning('Login failed: invalid password username=%s', username)
            flash('密碼錯誤', category='danger')
        else:
            logger.warning('Login failed: unknown username=%s', username)
            flash('用戶名稱不存在', category='danger')

        return render_template('/utility/personal/login.html')

    return render_template('/utility/personal/login.html')


@auth_bp.route('/logout', methods=['GET'])
def logout():
    logger.info('Logout: username=%s', session.get('username', 'unknown'))
    session.clear()
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if session.get('role_id') not in [99, 0]:
            abort(403)

        username = normalize_text(request.form.get('username'), 100)
        password = request.form.get('password', '')
        firstname = normalize_text(request.form.get('firstname'), 50)
        lastname = normalize_text(request.form.get('lastname'), 50)
        role_id = normalize_text(request.form.get('role'), 10)
        team_id = normalize_text(request.form.get('team'), 10)
        e_mail = normalize_text(request.form.get('email'), 255)
        phone = normalize_text(request.form.get('phone'), 30)

        if not username or len(password) < 8:
            flash('帳號不可為空，且密碼至少 8 碼', category='danger')
            return render_template('/utility/personal/login.html')

        if db.check_existing_username(username):
            error_message = '用戶名稱已存在'
            return render_template('/utility/personal/login.html', error_message=error_message)

        db.insert_user(username, password, firstname, lastname, role_id, team_id, phone, e_mail)
        return redirect(url_for('auth.login'))

    return render_template('/utility/personal/login.html')


@auth_bp.route('/u/update', methods=['GET', 'POST'])
def user_update():
    if request.method == 'POST':
        password = request.form.get('password', '')
        firstname = normalize_text(request.form.get('first_name'), 50)
        lastname = normalize_text(request.form.get('last_name'), 50)
        e_mail = normalize_text(request.form.get('email'), 255)
        phone = normalize_text(request.form.get('Phone'), 30)

        if not firstname or not lastname:
            flash('姓名不可為空', category='danger')
            return redirect(request.referrer or url_for('auth.login'))

        db.update_user_profile(user_id=session['user_id'], firstname=firstname, lastname=lastname,
                               e_mail=e_mail, phone=phone, password=password)
        return redirect(url_for('auth.login'))

    return render_template('/utility/personal/personal_profile.html', user_name=session['username'],
                           first_name=session['first_name'], last_name=session['last_name'], phone=session['phone'],
                           email=session['email'],
                           salary_profile=db.get_user_salary_profile(session['user_id']),
                           user_info=db.get_user_by_id(session['user_id']))


@auth_bp.route('/resetPassword', methods=['GET', 'POST'])
def reset_password():
    if has_permission('reset_password', session['user_id'], session['team_id'], session['role_id']):
        if request.method == 'POST':
            username = normalize_text(request.form.get('username'), 100)
            password = request.form.get('password', '')

            if not username or len(password) < 8:
                flash('重設密碼失敗：請確認帳號與密碼格式', category='danger')
                return render_template('reset_password.html')

            db.update_password(username, password)
            return render_template('/utility/personal/login.html')

        return render_template('reset_password.html')

    abort(403)