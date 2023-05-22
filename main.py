from flask import Flask, render_template, request, redirect, url_for, session
import database.queries as db

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 替換為實際的密鑰


@app.route('/')
def homepage():
    # if not check_login():
    #     return redirect('/login')  # 重新導向到登入頁面

    all_documents = db.get_pending_documents()
    pending_review_documents = get_pending_review_documents(all_documents)
    creator_pending_documents = get_creator_pending_documents(all_documents, session['username'])

    return render_template('homepage.html', pending_review_documents=pending_review_documents,
                           creator_pending_documents=creator_pending_documents)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # 使用 check_existing_username 函式檢查用戶名稱是否存在
        if db.check_existing_username(username):
            # 驗證密碼
            if db.verify_password(username, password):
                # 登入成功，將用戶名稱儲存到 session 中
                session['username'] = username
                return redirect(url_for('index'))
            else:
                error_message = '密碼錯誤'
        else:
            error_message = '用戶名稱不存在'

        return render_template('login.html', error_message=error_message)

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role_id = request.form['role']
        team_id = request.form['team']
        phone = request.form['phone']

        # 使用 check_existing_username 函式檢查用戶名稱是否存在
        if db.check_existing_username(username):
            error_message = '用戶名稱已存在'
            return render_template('register.html', error_message=error_message)

        # 插入新用戶資料
        db.insert_user(username, password, role_id, team_id, phone)

        # 註冊成功，轉到登入頁面
        return redirect(url_for('login'))

    roles = db.get_roles()
    teams = db.get_teams()

    return render_template('register.html', roles=roles, teams=teams)

def check_login():
    if 'username' not in session:
        return False
    # 進行其他登入狀態檢查，例如檢查使用者的權限等
    # 如果使用者已登入，返回 True；否則返回 False
    return True

def get_pending_review_documents(documents):
    pending_review_documents = []
    for document in documents:
        if document.status == 1:
            pending_review_documents.append(document)
    return pending_review_documents

def get_creator_pending_documents(documents, creator):
    creator_pending_documents = []
    for document in documents:
        if document.creator == creator and document.status == 1:
            creator_pending_documents.append(document)
    return creator_pending_documents


if __name__ == '__main__':
    app.run()
