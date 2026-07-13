from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash, abort, send_from_directory
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from datetime import timedelta, datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask_babel import Babel
from functions.permission import has_permission
from database.CI_API_Client import APIClient
from database.models import Currency
from dotenv import load_dotenv
from curl_cffi import requests
import database.queries as db
import functions.email as email
import functions.human_resource as hr
import pandas as pd
import threading
import time
import schedule
import json
import os
import random
import string

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
def forbidden_error(e):
    return render_template('/utility/basic_page/no_permission.html'), 403


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

    def calculate_rate(country, discount):
        curr = next((c for c in currency_list if c.country == country), None)
        if curr and curr.bank_selling_rate:
            try:
                rate_val = float(curr.bank_selling_rate)
                return rate_val - discount
            except ValueError:
                pass
        return error_fallback

    USD_val = calculate_rate('USD', 1)
    SGD_val = calculate_rate('SGD', 1)
    JPY_val = calculate_rate('JPY', 0.01)
    EUR_val = calculate_rate('EUR', 1)
    CNY_val = calculate_rate('CNY', 0.1)

    USD = round(USD_val, 1) if isinstance(USD_val, (int, float)) else USD_val
    SGD = round(SGD_val, 1) if isinstance(SGD_val, (int, float)) else SGD_val
    JPY = round(JPY_val, 3) if isinstance(JPY_val, (int, float)) else JPY_val
    EUR = round(EUR_val, 1) if isinstance(EUR_val, (int, float)) else EUR_val
    CNY = round(CNY_val, 2) if isinstance(CNY_val, (int, float)) else CNY_val

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
    valid_depts = ['FD', 'RT', 'HK', 'AC']
    if department not in valid_depts:
        department = 'FD' # Default or 404
        
    return render_template('/utility/hr/hr_schedule.html', department=department)

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
    if session.get('role_id') in [99, 0, 1, 2]:
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
        if session.get('role_id') not in [99, 0, 1, 2]:
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
        return jsonify(response_data)
    
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
    
    daily_groups = {}
    for log in raw_logs:
        log_time_str = log['attLogTime'] 
        try:
             log_dt = datetime.strptime(log_time_str, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
             try:
                 log_dt = datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S")
             except ValueError:
                 continue 
                 
        date_key = log_dt.date()
        
        if date_key not in daily_groups:
            daily_groups[date_key] = []
        daily_groups[date_key].append(log_dt)

    summary_list = []
    
    # Get User ID for Schedule Lookup
    db_user_for_schedule = db.get_user_by_clock_id(pin)
    user_id_for_schedule = db_user_for_schedule['user_id'] if db_user_for_schedule else None

    for date_key, times in daily_groups.items():
        times.sort()
        start_time = times[0]
        end_time = times[-1]
        
        duration_str = ""
        status = "Normal"
        
        if len(times) > 1:
            diff = end_time - start_time
            total_seconds = int(diff.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            duration_str = f"{hours}h {minutes}m"
        else:
            duration_str = "-"
            
        # Dynamic Late Check
        threshold_start = start_time.replace(hour=9, minute=0, second=0, microsecond=0) # Default
        
        if user_id_for_schedule:
            # Fetch assigned schedule
            sch = db.get_user_schedule_by_date(user_id_for_schedule, date_key)
            if sch:
                # sch['start_time'] is a timedelta or time object depending on connector
                # Assuming it is timedelta (since earlier code used string conversion) 
                # or string "HH:MM:SS" from previous context
                # Let's handle string or timedelta
                s_time = sch['start_time']
                if isinstance(s_time, timedelta):
                    total_seconds = int(s_time.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    threshold_start = start_time.replace(hour=hours, minute=minutes, second=0, microsecond=0)
                else:
                    # Try string parse
                    try:
                         # s_time might be "09:00:00"
                         st_parts = str(s_time).split(':')
                         h = int(st_parts[0])
                         m = int(st_parts[1])
                         threshold_start = start_time.replace(hour=h, minute=m, second=0, microsecond=0)
                    except:
                        pass # Keep default

        if start_time > threshold_start:
            status = "Late"
            
        summary_list.append({
            "date": date_key.strftime("%Y-%m-%d"),
            "start": start_time.strftime("%H:%M:%S"),
            "end": end_time.strftime("%H:%M:%S") if len(times) > 1 else "-",
            "duration": duration_str,
            "status": status
        })
    
    summary_list.sort(key=lambda x: x['date'], reverse=True)
    att_logs['summary'] = summary_list

    return jsonify({
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
    department = data.get('department', '')
    
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

    return jsonify({
        "schedules": [ {**s, "date": str(s['date']), "start_time": str(s['start_time']), "end_time": str(s['end_time'])} for s in schedules],
        "shift_types": [ {**st, "start_time": str(st['start_time']), "end_time": str(st['end_time'])} for st in shift_types],
        "employees": employees
    })

@app.route('/hr/schedule/save', methods=['POST'])
def hr_schedule_save():
    if session.get('role_id') not in [99, 0, 1, 2]:
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

@app.route('/hr/shift/save', methods=['POST'])
def hr_shift_save():
    if session.get('role_id') not in [99, 0, 1, 2]:
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.get_json()
    shift_id = data.get('id')
    name = data.get('name')
    start_time = data.get('start_time')
    end_time = data.get('end_time')
    color = data.get('color')
    
    db.save_shift_type(name, start_time, end_time, color, shift_id)
    return jsonify({"success": True})

@app.route('/hr/api/comment/get', methods=['POST'])
def hr_comment_get():
    data = request.get_json()
    dept = data.get('department')
    month = data.get('month')
    content = db.get_schedule_comment(dept, month)
    return jsonify({"content": content})

@app.route('/hr/api/comment/save', methods=['POST'])
def hr_comment_save():
    if session.get('role_id') not in [99, 0, 1, 2]:
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    dept = data.get('department')
    month = data.get('month')
    content = data.get('content')
    db.save_schedule_comment(dept, month, content)
    return jsonify({"success": True})

@app.route('/hr/api/comment/copy', methods=['POST'])
def hr_comment_copy():
    if session.get('role_id') not in [99, 0, 1, 2]:
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    dept = data.get('department')
    curr_month = data.get('current_month')
    content = db.get_previous_month_comment(dept, curr_month)
    return jsonify({"content": content})

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




# System Settings
@app.route('/sys/settings', methods=['GET'])
def sys_settings():
    if session.get('role_id') not in [99, 0]:
        abort(403)
    return render_template('/utility/sys/system_settings.html')

@app.route('/sys/users', methods=['GET'])
def sys_users():
    if session.get('role_id') not in [99, 0]:
        abort(403)
    users = db.get_all_users_admin()
    return render_template('/utility/sys/user_list.html', users=users)

@app.route('/sys/user/edit/<user_id>', methods=['GET'])
def sys_user_edit(user_id):
    if session.get('role_id') not in [99, 0]:
        abort(403)
    
    user = db.get_user_by_id(user_id)
    roles = db.get_roles()
    teams = db.get_teams()
    
    return render_template('/utility/sys/user_edit.html', user=user, roles=roles, teams=teams)

@app.route('/sys/user/save', methods=['POST'])
def sys_user_save():
    if session.get('role_id') not in [99, 0]:
        abort(403)
        
    user_id = request.form.get('user_id')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    role_id = request.form.get('role_id')
    team_id = request.form.get('team_id')
    password = request.form.get('password') # Optional
    
    db.update_user_admin(user_id, first_name, last_name, email, phone, role_id, team_id, password)
    
    flash("User updated successfully", "success")
    return redirect('/sys/users')

def get_agent(req):
    platform = req.user_agent.platform
    browser = req.user_agent.browser
    return f"Platform: {platform}, Browser: {browser}"

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
        else:
            rate.encoding = 'utf-8'  
            rt = rate.text
            
            if 'html' in rate.headers.get('Content-Type', '').lower() or rt.strip().startswith('<!DOCTYPE'):
                error_msg = "Blocked by BOT WAF/Challenge"
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
                    except Exception:
                        pass
                
                if not currency_list:
                    error_msg = "CSV parse failure or empty rows"
                    
    except Exception as e:
        error_msg = f"Error: {str(e)}"

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
