from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from datetime import timedelta
import database.queries as db
import json
import os


file_path = os.path.join(os.getcwd(), 'static', 'js', 'p_type_data.json')
app = Flask(__name__, template_folder='templates')
app.secret_key = 'a3af8aea6ef1c50418b8a1b485ab6582'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)


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
        return redirect('/login')


@app.route('/')
def homepage():

    return render_template('homepage.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
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
                session['logged_in'] = True

                return redirect('/')
            else:
                flash('密碼錯誤', category='success')
        else:
            flash('用戶名稱不存在', category='success')

        return render_template('login.html')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        firstname = request.form['firstname']
        lastname = request.form['lastname']
        role_id = request.form['role']
        team_id = request.form['team']
        email = request.form['email']
        phone = request.form['phone']
        if db.check_existing_username(username):
            error_message = '用戶名稱已存在'
            return render_template('register.html', error_message=error_message)
        db.insert_user(username, password, firstname, lastname, role_id, team_id, phone, email)

        return redirect(url_for('login'))

    roles = db.get_roles()
    teams = db.get_teams()

    return render_template('register.html', roles=roles, teams=teams)


@app.route('/resetPassword', methods=['GET', 'POST'])
def update_password():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        db.update_password(username, password)
        return render_template('login.html')

    return render_template('reset_password.html')


@app.route('/plist', methods=['GET', 'POST'])
def approval_list():
    creator_pending_documents = db.get_pending_doc(session['user_id'])
    unapproved_documents = db.get_unapproved_doc_by_user(session['user_id'])
    all_documents = db.get_pending_doc()

    return render_template('utility/documents/approval_list.html',
                           creator_pending_documents=creator_pending_documents,
                           unapproved_documents=unapproved_documents,
                           all_documents=all_documents)


@app.route('/new_approval', methods=['GET', 'POST'])
def new_approval():
    type_list = []
    approval_user_list = db.get_approval_users(session['user_id'])
    with open(file_path) as file:
        data = json.load(file)
        for key, value in data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    type_list.append([sub_key, sub_value])

    if request.method == 'POST':
        user_agent = request.user_agent.string
        doc_type = request.form.get('type')
        title = request.form.get('title')
        content = request.form.get('content')
        send_approval_users = request.form.getlist('mySelect')
        signature_required = 0

        if not send_approval_users:
            flash('你沒有填入任何簽呈對象', category='success')
        else:
            created_doc_id = db.insert_document(session['user_id'], session['username'], signature_required,
                                                doc_type, title, content, user_agent)
            return_app_status = db.insert_doc_approval(created_doc_id, send_approval_users)
            if return_app_status:
                flash('成功送出', category='success')
                return render_template('utility/documents/new_approval.html',
                                       type_list=type_list, app_users=approval_user_list)
            else:
                flash('送出失敗！', category='success')

    return render_template('utility/documents/new_approval.html', type_list=type_list, app_users=approval_user_list)


@app.route('/edit_doc/<doc_id>', methods=['GET', 'POST'])
def edit_doc(doc_id):
    if request.method == 'POST':
        db.update_doc(doc_id, request.form.get('title'), request.form.get('type'), 0,
                      request.form.get('content'), request.user_agent.string, session['username'])
        flash('成功送出', category='success')
        return redirect('/plist')
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
            return render_template('utility/documents/edit_document.html',
                                   type_list=type_list, doc=doc, content=json_content)
    else:
        return render_template('utility/basic_page/no_permission.html')


@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        user_agent = request.user_agent.string

        return render_template('search.html')

    return render_template('search.html')


@app.route('/p/approve', methods=['POST'])
def p_approve():
    if request.method == 'POST':
        doc_id = request.form.get('doc_id')
        db.update_doc_app(doc_id, session['user_id'], 2)
        db.update_doc_status(doc_id, 2)

        return redirect('/plist')


@app.route('/p/reject', methods=['POST'])
def p_reject():
    if request.method == 'POST':
        doc_id = request.form.get('doc_id')
        db.update_doc_app(doc_id, session['user_id'], 3)
        db.update_doc_status(doc_id, 3)

        return redirect('/plist')


@app.route('/p/delete', methods=['POST'])
def p_delete():
    if request.method == 'POST':
        doc_id = request.form.get('doc_id')
        db.update_doc_app(doc_id, session['user_id'], 4)
        db.update_doc_status(doc_id, 4)

        return redirect('/plist')

@app.route('/testPage', methods=['GET', 'POST'])
def test():
    db.update_doc_status(6, 2)
    db.update_doc_status(5, 2)

    return render_template('test.html')


if __name__ == '__main__':
    app.run()