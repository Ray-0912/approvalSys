from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from functions.permission import has_permission
from datetime import timedelta, datetime
from flask_babel import Babel
import database.queries as db
import functions.email as email
import json
import os


file_path = os.path.join(os.getcwd(), 'static', 'js', 'p_type_data.json')
app = Flask(__name__, template_folder='templates')
app.secret_key = 'a3af8aea6ef1c50418b8a1b485ab6582'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['BABEL_DEFAULT_LOCALE'] = 'zh_TW'
app.config['BABEL_DEFAULT_TIMEZONE'] = 'UTC'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(os.getcwd(), 'translations')
babel = Babel(app)


@app.context_processor
def inject_global_variables():
    logged_in = session.get('logged_in', False)
    username = session.get('username', 'NONE') if logged_in else ''

    return {'username': username}


@app.after_request
def after_request(response):
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=1)
    return response


@app.before_request
def check_authentication():
    check_login = True
    if 'username' not in session:
        check_login = False
    if request.endpoint != 'login' and not check_login:
        if not request.path.endswith(('.js', '.css', '.jpg', '.png', '.jpeg')):
            if request.endpoint != 'w_menu':
                return render_template('/utility/personal/login.html')


@app.errorhandler(403)
def forbidden_error(error):
    return render_template('/utility/basic_page/no_permission.html'), 403


@app.route('/')
def homepage():
    return render_template('homepage.html')


@app.route('/w_menu')
def w_menu():
    current_time = datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d")

    USD = db.get_currency('USD', formatted_time)
    SGD = db.get_currency('SGD', formatted_time)
    JPY = db.get_currency('JPY', formatted_time)
    EUR = db.get_currency('EUR', formatted_time)
    CNY = db.get_currency('CNY', formatted_time)

    return render_template('front_desk_wheel_menu.html', USD=USD.spot_selling_rate, SGD=SGD.spot_selling_rate,
                           JPY=JPY.spot_selling_rate, EUR=EUR.spot_selling_rate, CNY=CNY.spot_selling_rate)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        app.config['BABEL_DEFAULT_LOCALE'] = 'zh_TW'
        username = request.form['username']
        password = request.form['password']

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
                session['logged_in'] = True

                return redirect('/')
            else:
                flash('密碼錯誤', category='success')
        else:
            flash('用戶名稱不存在', category='success')

        return render_template('/utility/personal/login.html')

    return render_template('/utility/personal/login.html')


@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        firstname = request.form['firstname']
        lastname = request.form['lastname']
        role_id = request.form['role']
        team_id = request.form['team']
        e_mail = request.form['email']
        phone = request.form['phone']
        if db.check_existing_username(username):
            error_message = '用戶名稱已存在'
            return render_template('/utility/personal/login.html', error_message=error_message)
        db.insert_user(username, password, firstname, lastname, role_id, team_id, phone, e_mail)

        return redirect(url_for('login'))

    return render_template('/utility/personal/login.html')


@app.route('/u/update', methods=['GET', 'POST'])
def user_update():
    if request.method == 'POST':
        password = request.form['password']
        firstname = request.form['first_name']
        lastname = request.form['last_name']
        e_mail = request.form['email']
        phone = request.form['Phone']
        db.update_user_profile(user_id=session['user_id'], firstname=firstname, lastname=lastname,
                               e_mail=e_mail, phone=phone, password=password)
        return redirect(url_for('login'))

    return render_template('/utility/personal/personal_profile.html', user_name=session['username'],
                           first_name=session['first_name'], last_name=session['last_name'], phone=session['phone'],
                           email=session['email'])


@app.route('/resetPassword', methods=['GET', 'POST'])
def reset_password():
    if has_permission('reset_password', session['user_id'], session['team_id'], session['role_id']):
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')

            db.update_password(username, password)
            return render_template('/utility/personal/login.html')

        return render_template('reset_password.html')
    else:
        abort(403)


@app.route('/p/list', methods=['GET', 'POST'])
def p_list():
    if has_permission('p_list', session['user_id'], session['team_id'], session['role_id']):
        creator_pending_documents = db.get_30days_doc(session['user_id'])
        unapproved_documents = db.get_unapproved_doc_by_user(session['user_id'])
        all_documents = db.get_30days_doc()

        return render_template('/utility/documents/approval_list.html',
                               creator_pending_documents=creator_pending_documents,
                               unapproved_documents=unapproved_documents,
                               all_documents=all_documents)
    else:
        abort(403)


@app.route('/p/new', methods=['GET', 'POST'])
def p_new():
    if has_permission('p_new', session['user_id'], session['team_id'], session['role_id']):
        type_list = []
        approval_user_list = db.get_approval_users(session['user_id'])
        with open(file_path) as file:
            data = json.load(file)
            for key, value in data.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        type_list.append([sub_key, sub_value])

        if request.method == 'POST':
            user_agent = get_agent(request)
            doc_type = request.form.get('type')
            title = request.form.get('title')
            content = request.form.get('content')
            send_approval_users = request.form.getlist('mySelect')
            notify_users = request.form.getlist('notify')
            signature_required = 0

            if not send_approval_users:
                flash('你沒有填入任何簽呈對象', category='success')
            else:
                created_doc_id = db.insert_document(session['user_id'], session['username'], signature_required,
                                                    doc_type, title, content, user_agent)
                return_app_status = db.insert_doc_approval(created_doc_id, send_approval_users)
                if return_app_status:
                    email.send_email(created_doc_id, send_approval_users, notify_users, title, content)
                    flash('成功送出', category='success')
                    return render_template('/utility/documents/new_approval.html',
                                           type_list=type_list, app_users=approval_user_list)
                else:
                    flash('送出失敗！', category='success')

        return render_template('/utility/documents/new_approval.html', type_list=type_list, app_users=approval_user_list)
    else:
        abort(403)


@app.route('/p/edit/<doc_id>', methods=['GET', 'POST'])
def p_edit(doc_id):
    if has_permission('p_edit', session['user_id'], session['team_id'], session['role_id']):
        if request.method == 'POST':
            db.update_doc(doc_id, request.form.get('title'), request.form.get('type'), 0,
                          request.form.get('content'), get_agent(request), session['username'])
            flash('成功送出', category='success')
            return redirect('/p/list')
        doc = db.get_single_documents(doc_id)
        doc_content = doc.content.replace('\n', '')
        json_content = json.dumps(doc_content)[1:-1]

        if doc.creator == session['user_id'] and doc.status == 1:
            type_list = []
            with open(file_path) as file:
                data = json.load(file)
                for key, value in data.items():
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            type_list.append([sub_key, sub_value])

            if doc is not None:
                return render_template('/utility/documents/edit_document.html',
                                       type_list=type_list, doc=doc, content=json_content)
        else:
            return render_template('/utility/basic_page/no_permission.html')
    else:
        abort(403)


@app.route('/p/search', methods=['GET', 'POST'])
def p_search():
    if has_permission('p_new', session['user_id'], session['team_id'], session['role_id']):
        type_list = []
        with open(file_path) as file:
            data = json.load(file)
            for key, value in data.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        type_list.append([sub_key, sub_value])

        if request.method == 'POST':
            documents = db.get_in_search_doc(created_time=request.form.get('createdtime'),
                                             p_type=request.form.get('type'), content=request.form.get('content'))
            return render_template('/utility/documents/search.html', type_list=type_list, documents=documents)

        documents = db.get_30days_doc()

        return render_template('/utility/documents/search.html', type_list=type_list, documents=documents)
    else:
        abort(403)


@app.route('/p/view/<doc_id>', methods=['GET'])
def p_view(doc_id):
    if has_permission('p_view', session['user_id'], session['team_id'], session['role_id']):
        doc = db.get_single_documents(doc_id)
        doc_sign_record = db.get_approve_record_all(doc_id)
        creator = 0
        approve = db.get_approve_record_by_user(session['user_id'], doc_id)
        if session['user_id'] == doc.creator:
            creator = 1

        return render_template('/utility/documents/doc_view.html',
                               document=doc, creator=creator, approve=approve, app_record=doc_sign_record)
    else:
        abort(403)


@app.route('/p/approve', methods=['POST'])
def p_approve():
    if request.method == 'POST':
        doc_id = request.form.get('doc_id')
        db.update_doc_app(doc_id, session['user_id'], 1)
        db.update_doc_status(doc_id, 2)

        return redirect('/p/list')


@app.route('/p/reject', methods=['POST'])
def p_reject():
    if request.method == 'POST':
        doc_id = request.form.get('doc_id')
        db.update_doc_app(doc_id, session['user_id'], 2)
        db.update_doc_status(doc_id, 3)

        return redirect('/p/list')


@app.route('/p/delete', methods=['POST'])
def p_delete():
    if request.method == 'POST':
        doc_id = request.form.get('doc_id')
        db.update_doc_app(doc_id, session['user_id'], 4)
        db.update_doc_status(doc_id, 4)

        return redirect('/p/list')


@app.route('/set_locale', methods=['POST'])
def set_locale():
    selected_locale = request.form['locale']
    session['locale'] = selected_locale
    return redirect(request.referrer)


@app.route('/test', methods=['GET', 'POST'])
def test():
    return render_template('practice/practicing.html')


def get_agent(requests):
    platform = requests.user_agent.platform
    browser = requests.user_agent.browser
    return f"Platform: {platform}, Browser: {browser}"


if __name__ == '__main__':
    app.run()
