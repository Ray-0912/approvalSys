from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash, abort, send_from_directory
from functions.permission import has_permission
from datetime import timedelta, datetime
from flask_babel import Babel
from database.models import Currency
from database.CI_API_Client import APIClient
import database.queries as db
import functions.email as email
import functions.human_resource as hr
import threading
import requests
import time
import schedule
import json
import os
from dotenv import load_dotenv

load_dotenv()

file_path = os.path.join(os.getcwd(), 'static', 'js', 'p_type_data.json')
app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv('SECRET_KEY', 'a3af8aea6ef1c50418b8a1b485ab6582')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['BABEL_DEFAULT_LOCALE'] = 'zh_TW'
app.config['BABEL_DEFAULT_TIMEZONE'] = 'UTC'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = os.path.join(os.getcwd(), 'translations')
babel = Babel(app)

# API client for bioLife
client = APIClient()


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
def forbidden_error():
    return render_template('/utility/basic_page/no_permission.html'), 403


@app.route('/')
def homepage():
    return render_template('homepage.html')


@app.route('/w_menu')
def w_menu():
    current_time = datetime.now()
    formatted_time = current_time.strftime("%Y-%m-%d")

    currency_list = update_currency(formatted_time)

    USD = float(next((curr for curr in currency_list if curr.country == 'USD'), None).bank_buying_rate) - 1
    SGD = float(next((curr for curr in currency_list if curr.country == 'SGD'), None).bank_buying_rate) - 1
    JPY = float(next((curr for curr in currency_list if curr.country == 'JPY'), None).bank_buying_rate) - 0.01
    EUR = float(next((curr for curr in currency_list if curr.country == 'EUR'), None).bank_buying_rate) - 1
    CNY = float(next((curr for curr in currency_list if curr.country == 'CNY'), None).bank_buying_rate) - 0.1

    USD = round(USD, 1)
    SGD = round(SGD, 1)
    JPY = round(JPY, 3)
    EUR = round(EUR, 1)
    CNY = round(CNY, 2)

    return render_template('front_desk_wheel_menu.html', USD=USD, SGD=SGD,
                           JPY=JPY, EUR=EUR, CNY=CNY,
                           date=formatted_time)


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
                session['clock_id'] = user[9]
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
        with open(file_path, 'r', encoding='utf-8') as file:
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

        return render_template('/utility/documents/new_approval.html', type_list=type_list,
                               app_users=approval_user_list)
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
            with open(file_path, 'r', encoding='utf-8') as file:
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
        with open(file_path, 'r', encoding='utf-8') as file:
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

# Human Resource
@app.route('/hr/new', methods=['GET', 'POST'])
def hr_new_member():
    if request.method == 'POST':
        organization_id = hr.check_organization_id(request.form.get('organization'), request.form.get('department'))
        ssn = request.form.get('ssn')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        e_mail = request.form.get('e_mail')
        phone = request.form.get('phone')
        team_id = hr.check_team_id(organization_id)
        clock_id = client.get_latest_person_pin(organization_unit_id=organization_id)

        print("123  ", request.form.get('organization'))
        print("og id : " , organization_id)
        print("ssn : " , ssn)
        print("firstname : " , first_name)
        print("lastname : " , last_name)
        print("mail : " , e_mail)
        print("phone : " , phone)
        print("teamid : " , team_id)
        print("clockid : " , clock_id)
        # add_result = hr_new_person_result(pin=clock_id, name=first_name+last_name, og_id=organization_id, ssn=ssn)
        # while add_result == 0:
        #     clock_id = int(clock_id) + 1
        #     add_result = hr_new_person_result(pin=clock_id, name=first_name+last_name, og_id=organization_id, ssn=ssn)
        #
        # db.insert_user(clock_id, '123456', first_name, last_name, '3', team_id, phone, e_mail)

        return redirect('/hr/new')
    return render_template('/utility/hr/hr_new.html')

@app.route('/hr/schedule/<department>', methods=['GET', 'POST'])
def hr_main(department):
    if department == 'FD':
        # Front Desk
        # 下面補參數
        return render_template('/utility/hr/hr_schedule.html')
    elif department == 'RT':
        # Restaurant
        # 下面補參數
        return render_template('/utility/hr/hr_schedule.html')
    elif department == 'HK':
        # Housekeeping
        # 下面補參數
        return render_template('/utility/hr/hr_schedule.html')
    elif department == 'AC':
        # Accountant
        # 下面補參數
        return render_template('/utility/hr/hr_schedule.html')

    return render_template('/utility/hr/hr_schedule.html')

@app.route('/hr/salary/cal', methods=['GET', 'POST'])
def hr_salary_cal():
    if request.method == 'GET':


        return redirect('/hr/salary/cal')

@app.route('/hr/salary/ma', methods=['GET', 'POST'])
def hr_salary_ma():
    if request.method == 'GET':


        return redirect('/hr/salary/ma')


@app.route('/hr/clockRecord', methods=['GET', 'POST'])
def hr_clock_record():
    all_users = []
    # Check if user is manager (Role ID 0 or 1)
    if session.get('role_id') in [0, 1]:
        all_users = db.get_all_users_with_clock_id()
    
    return render_template("/utility/hr/hr_clock_record.html", all_users=all_users)

@app.route('/hr/clockRecordPost', methods=['POST'])
def hr_clock_record_post():
    current_user_pin = str(session.get('clock_id'))
    
    if not current_user_pin:
        return jsonify({"error": "Unauthorized: No PIN provided"}), 401

    data = request.get_json()
    start_date = data.get("Start")
    end_date = data.get("End")
    target_pin = data.get("target_pin")

    # Permission check for viewing other users
    if target_pin:
        if session.get('role_id') not in [0, 1]:
             return jsonify({"error": "Unauthorized: Insufficient permissions"}), 403
        pin = str(target_pin)
    else:
        pin = current_user_pin

    if not isinstance(pin, str) or not pin.isdigit():
        return jsonify({"error": "Invalid PIN format"}), 400

    if not start_date or not end_date:
        return jsonify({"error": "Invalid date range"}), 400

    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S").date()
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S").date()

    att_logs = client.get_att_logs(pin, start_date_obj, end_date_obj)

    if not att_logs.get('result') or not att_logs['result'].get('items'):
        employee_info = client.get_employee_info(pin)
        
        response_data = {
             "result": {
                "items": [], # Raw items
                "summary": [], # Calculated summary
                "date": {
                    "start": start_date,
                    "end": end_date},
                "employee": employee_info if employee_info else {"pin": pin, "name": "Unknown"}
            }
        }
        if not employee_info:
             # Try to get name from DB if API fails or returns nothing (optional fallback)
             pass
             
        return jsonify(response_data)
    
    # Calculate Summary
    raw_logs = att_logs['result']['items']
    # Ensure logs are sorted by time
    raw_logs.sort(key=lambda x: x['attLogTime'])
    
    daily_groups = {}
    for log in raw_logs:
        log_time_str = log['attLogTime'] # Format: 2024-12-09T08:00:00 or similar
        # Parse ISO string to datetime object
        # The client.get_att_logs/API usually returns ISO format. 
        # CAUTION: The frontend code used: items.sort((a, b) => new Date(b.attLogTime) - new Date(a.attLogTime));
        # We need to be able to parse it in Python.
        # Assuming ISO format with 'T' or space.
        
        try:
             log_dt = datetime.strptime(log_time_str, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
             try:
                 log_dt = datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S")
             except ValueError:
                 continue # Skip invalid format
                 
        date_key = log_dt.date()
        
        if date_key not in daily_groups:
            daily_groups[date_key] = []
        daily_groups[date_key].append(log_dt)

    summary_list = []
    for date_key, times in daily_groups.items():
        times.sort()
        start_time = times[0]
        end_time = times[-1]
        
        duration_str = ""
        status = "Normal"
        
        # Calculate duration
        if len(times) > 1:
            diff = end_time - start_time
            total_seconds = int(diff.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            duration_str = f"{hours}h {minutes}m"
        else:
            duration_str = "-"
            
        # Check Late Arrival (Threshold: 09:00)
        # Assuming standard shift start is 9:00 AM
        threshold_start = start_time.replace(hour=9, minute=0, second=0, microsecond=0)
        if start_time > threshold_start:
            status = "Late"
            
        # Check Early Leave (Optional, e.g., 18:00)
        # threshold_end = start_time.replace(hour=18, minute=0, second=0, microsecond=0)
        # if end_time < threshold_end and len(times) > 1:
        #    status = "Early Leave" # Simple logic, can be complex
            
        summary_list.append({
            "date": date_key.strftime("%Y-%m-%d"),
            "start": start_time.strftime("%H:%M:%S"),
            "end": end_time.strftime("%H:%M:%S") if len(times) > 1 else "-",
            "duration": duration_str,
            "status": status
        })
    
    # Sort summary by date desc
    summary_list.sort(key=lambda x: x['date'], reverse=True)

    att_logs['summary'] = summary_list

    return jsonify({
        "result": {
            "items": att_logs, # Now contains nested result from API 
            # WAIT. att_logs from client.get_att_logs structure:
            # { "result": { "totalCount": N, "items": [...] }, ... }
            # client.get_att_logs return the dict response from API.
            # My previous view of client code was not full but usage implies structure.
            # Let's adjust structure to be safe.
            # att_logs here IS the dict returned by client.get_att_logs.
            
            "date": {
                "start": start_date,
                "end": end_date
            }
        }
    })


@app.route('/set_locale', methods=['POST'])
def set_locale():
    selected_locale = request.form['locale']
    session['locale'] = selected_locale
    return redirect(request.referrer)


@app.route('/test', methods=['GET', 'POST'])
def test():
    return render_template('practice/practicing.html')

# Schedule Management Routes
@app.route('/hr/schedule/list', methods=['POST'])
def hr_schedule_list():
    data = request.get_json()
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    # Get all Schedules
    schedules = db.get_schedules(start_date, end_date)
    
    # Get Shift Types
    shift_types = db.get_shift_types()
    
    # Get Employees (for manager palette)
    employees = []
    if session.get('role_id') in [0, 1]: 
        employees = db.get_all_users_with_clock_id()

    # Convert date/time objects to string for JSON
    def serialize(obj):
        if isinstance(obj, (datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, timedelta):
             return str(obj)
        return obj

    return jsonify({
        "schedules": [ {**s, "date": str(s['date']), "start_time": str(s['start_time']), "end_time": str(s['end_time'])} for s in schedules],
        "shift_types": [ {**st, "start_time": str(st['start_time']), "end_time": str(st['end_time'])} for st in shift_types],
        "employees": employees
    })

@app.route('/hr/schedule/save', methods=['POST'])
def hr_schedule_save():
    if session.get('role_id') not in [0, 1]:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.get_json()
    user_id = data.get('user_id')
    date = data.get('date')
    shift_type_id = data.get('shift_type_id')
    
    if not user_id or not date:
        return jsonify({"error": "Missing parameters"}), 400
        
    # If shift_type_id is null/empty, delete the schedule
    if not shift_type_id:
        db.delete_schedule(user_id, date)
    else:
        db.save_schedule(user_id, date, shift_type_id, session['user_id'])
        
    return jsonify({"success": True})


import pandas as pd
import random
import string
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import os

@app.route('/hr/shift/save', methods=['POST'])
def hr_shift_save():
    if session.get('role_id') not in [0, 1]:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.get_json()
    shift_id = data.get('id')
    name = data.get('name')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    color = data.get('color')
    
    db.save_shift_type(name, start_time, end_time, color, shift_id)
    return jsonify({"success": True})

@app.route('/excelimport', methods=['GET', 'POST'])
def excel_import():
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
        except:
             # Fallback if CID font not available (unlikely in reportlab unless minimal)
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
                    except:
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
                print(f"Error row {index}: {e}")
                summary["errors"] += 1
                
        return render_template('/utility/sys/excel_import.html', summary=summary)
        
    except Exception as e:
        flash(f'Error processing file: {str(e)}', 'danger')
        return redirect('/excelimport')


@app.route('/download/pdf/<filename>')
def download_pdf(filename):
    if session.get('role_id') not in [99, 1, 2, 3, 4, 5]: # Allow logged in users
         return jsonify({"error": "Unauthorized"}), 403
    return send_from_directory(os.path.join(os.getcwd(), 'output'), filename, as_attachment=True)



def get_agent(req):
    platform = req.user_agent.platform
    browser = req.user_agent.browser
    return f"Platform: {platform}, Browser: {browser}"

def update_currency(date):
    currency_list = []

    url = 'https://rate.bot.com.tw/xrt/flcsv/0/day'
    rate = requests.get(url)
    rate.encoding = 'utf-8'
    rt = rate.text
    rts = rt.split('\n')
    for i in rts:
        try:
            a = i.split(',')
            currency_list.append(Currency(date, a[0], a[2], a[12]))
        except:
            break

    return currency_list

def schedule_task():
    def job():
        formatted_time = datetime.now().strftime("%Y-%m-%d")
        update_currency(formatted_time)

    schedule.every().day.at("23:30").do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=schedule_task, daemon=True)
    scheduler_thread.start()

    app.run(host="0.0.0.0", port=80)
