import mysql.connector
import bcrypt
from flask import Flask, render_template, request, redirect, session


app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MySQL連線設定
db = mysql.connector.connect(
    host='your_host',
    user='your_user',
    password='your_password',
    database='your_database'
)


# 路由：登入頁面
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # 在這裡進行身份驗證的邏輯
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if user is None:
            # 驗證失敗，返回登入頁面或顯示錯誤信息
            return render_template('login.html', error='Invalid username or password')

        hashed_password = user[1]

        if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
            # 密碼驗證成功，將用戶信息保存到session中
            session['username'] = username
            return redirect('/')
        else:
            # 驗證失敗，返回登入頁面或顯示錯誤信息
            return render_template('login.html', error='Invalid username or password')

    return render_template('login.html')


# 路由：註冊新用戶
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # 在這裡進行密碼加密的邏輯
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # 將加密後的密碼存儲到資料庫
        cursor = db.cursor()
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
        db.commit()
        cursor.close()

        return redirect('/login')

    return render_template('register.html')


if __name__ == '__main__':
    app.run(debug=True)
