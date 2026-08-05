from datetime import datetime
import json
import logging
import os

from flask import Blueprint, abort, flash, redirect, render_template, request, session

import database.queries as db
import functions.email as email
from functions.permission import has_permission

approval_bp = Blueprint('approval', __name__)
logger = logging.getLogger('approval_system.approval')
TYPE_FILE_PATH = os.path.join(os.getcwd(), 'static', 'js', 'p_type_data.json')


def normalize_text(value, max_len=255):
    if value is None:
        return ''
    value = str(value).strip()
    return value[:max_len]


def invalid_request(message='Invalid request', status_code=400):
    flash(message, category='danger')
    return redirect(request.referrer or '/p/list')


def get_agent(req):
    platform = req.user_agent.platform
    browser = req.user_agent.browser
    return f'Platform: {platform}, Browser: {browser}'


def load_type_list():
    type_list = []
    with open(TYPE_FILE_PATH, 'r', encoding='utf-8') as file:
        data = json.load(file)
        for key, value in data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    type_list.append([sub_key, sub_value])
    return type_list


@approval_bp.route('/p/list', methods=['GET', 'POST'])
def p_list():
    if not has_permission('p_list', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    creator_pending_documents = db.get_30days_doc(session['user_id'])
    unapproved_documents = db.get_unapproved_doc_by_user(session['user_id'])
    all_documents = db.get_30days_doc()

    query_text = normalize_text(request.args.get('q'), 100).lower()

    try:
        page_size = int(request.args.get('page_size', 10))
    except ValueError:
        page_size = 10
    page_size = max(5, min(page_size, 50))

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    page = max(1, page)

    if query_text:
        def match_document(document):
            return (
                query_text in str(document.title).lower()
                or query_text in str(document.doc_type_cht).lower()
                or query_text in str(document.creator_name).lower()
            )

        creator_pending_documents = [document for document in creator_pending_documents if match_document(document)]
        unapproved_documents = [document for document in unapproved_documents if match_document(document)]
        all_documents = [document for document in all_documents if match_document(document)]

    total_count = len(all_documents)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    all_documents = all_documents[start_idx:end_idx]

    return render_template('/utility/documents/approval_list.html',
                           creator_pending_documents=creator_pending_documents,
                           unapproved_documents=unapproved_documents,
                           all_documents=all_documents,
                           q=query_text,
                           page=page,
                           page_size=page_size,
                           total_pages=total_pages,
                           total_count=total_count)


@approval_bp.route('/p/new', methods=['GET', 'POST'])
def p_new():
    if not has_permission('p_new', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    type_list = load_type_list()
    approval_user_list = db.get_approval_users(session['user_id'])

    if request.method == 'POST':
        user_agent = get_agent(request)
        doc_type = normalize_text(request.form.get('type'), 20)
        title = normalize_text(request.form.get('title'), 120)
        content = normalize_text(request.form.get('content'), 10000)
        send_approval_users = request.form.getlist('mySelect')
        notify_users = request.form.getlist('notify')
        signature_required = 0

        if not doc_type or not title or not content:
            flash('簽呈類型、標題與內容不可為空', category='danger')
            return render_template('/utility/documents/new_approval.html', type_list=type_list,
                                   app_users=approval_user_list)

        if not send_approval_users:
            flash('你沒有填入任何簽呈對象', category='warning')
        else:
            try:
                created_doc_id = db.create_document_with_approvals(
                    session['user_id'], session['username'], signature_required,
                    doc_type, title, content, user_agent, send_approval_users
                )
            except Exception as exc:
                logger.exception('Document create transaction failed: creator=%s error=%s',
                                 session.get('user_id'), exc)
                created_doc_id = None

            if created_doc_id:
                email.send_email(created_doc_id, send_approval_users, notify_users, title, content)
                logger.info('Document created: doc_id=%s creator=%s approvers=%s',
                            created_doc_id, session.get('user_id'), len(send_approval_users))
                flash('簽呈已送出', category='success')
                return render_template('/utility/documents/new_approval.html',
                                       type_list=type_list, app_users=approval_user_list)
            flash('送出失敗！', category='danger')

    return render_template('/utility/documents/new_approval.html', type_list=type_list,
                           app_users=approval_user_list)


@approval_bp.route('/p/edit/<doc_id>', methods=['GET', 'POST'])
def p_edit(doc_id):
    if not has_permission('p_edit', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    if request.method == 'POST':
        if not str(doc_id).isdigit():
            flash('文件編號格式錯誤', category='danger')
            return redirect('/p/list')

        title = normalize_text(request.form.get('title'), 120)
        doc_type = normalize_text(request.form.get('type'), 20)
        content = normalize_text(request.form.get('content'), 10000)

        if not title or not doc_type or not content:
            flash('標題、類型與內容不可為空', category='danger')
            return redirect(request.referrer or '/p/list')

        db.update_doc(doc_id, title, doc_type, 0, content, get_agent(request), session['username'])
        flash('簽呈已更新', category='success')
        return redirect('/p/list')

    doc = db.get_single_documents(doc_id)
    if doc is None:
        abort(404)

    doc_content = doc.content.replace('\n', '')
    json_content = json.dumps(doc_content)[1:-1]

    if doc.creator == session['user_id'] and doc.status == 1:
        type_list = load_type_list()
        return render_template('/utility/documents/edit_document.html',
                               type_list=type_list, doc=doc, content=json_content)

    return render_template('/utility/basic_page/no_permission.html')


@approval_bp.route('/p/search', methods=['GET', 'POST'])
def p_search():
    if not has_permission('p_new', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    type_list = load_type_list()
    if request.method == 'POST':
        created_time = normalize_text(request.form.get('createdtime'), 50)
        try:
            if created_time:
                start_str, end_str = created_time.split(' - ')
                datetime.strptime(start_str, '%m/%d/%Y')
                datetime.strptime(end_str, '%m/%d/%Y')
        except ValueError:
            flash('日期區間格式錯誤，請使用 MM/DD/YYYY - MM/DD/YYYY', category='danger')
            return render_template('/utility/documents/search.html', type_list=type_list, documents=[])

        documents = db.get_in_search_doc(created_time=created_time,
                                         p_type=request.form.get('type'), content=request.form.get('content'))
        return render_template('/utility/documents/search.html', type_list=type_list, documents=documents)

    documents = db.get_30days_doc()
    return render_template('/utility/documents/search.html', type_list=type_list, documents=documents)


@approval_bp.route('/p/view/<doc_id>', methods=['GET'])
def p_view(doc_id):
    if not has_permission('p_view', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    doc = db.get_single_documents(doc_id)
    if doc is None:
        abort(404)

    doc_sign_record = db.get_approve_record_all(doc_id)
    creator = 1 if session['user_id'] == doc.creator else 0
    next_approver = db.get_next_pending_approver(doc_id)
    approve = 1 if next_approver and int(next_approver['user_id']) == int(session['user_id']) else 0
    return render_template('/utility/documents/doc_view.html',
                           document=doc, creator=creator, approve=approve,
                           app_record=doc_sign_record, next_approver=next_approver)


@approval_bp.route('/p/approve', methods=['POST'])
def p_approve():
    if not has_permission('p_view', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    doc_id = normalize_text(request.form.get('doc_id'), 20)
    if not doc_id.isdigit():
        flash('文件編號格式錯誤', category='danger')
        return redirect('/p/list')

    next_approver = db.get_next_pending_approver(doc_id)
    if not next_approver or int(next_approver['user_id']) != int(session['user_id']):
        flash('目前不是你的簽核順序，請等待前一位簽核完成', category='danger')
        return redirect(f'/p/view/{doc_id}')

    db.update_doc_app(doc_id, session['user_id'], 1)
    db.update_doc_status(doc_id, 2)
    logger.info('Document approved: doc_id=%s approver=%s', doc_id, session.get('user_id'))

    doc = db.get_single_documents(doc_id)
    if doc:
        approver_name = f"{session.get('username', '')}"
        try:
            email.send_approval_status_email(doc_id, doc.creator, doc.title, approver_name, 'approve')
        except Exception:
            logger.warning('Approval notification email failed: doc_id=%s', doc_id)

    return redirect('/p/list')


@approval_bp.route('/p/reject', methods=['POST'])
def p_reject():
    if not has_permission('p_view', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    doc_id = normalize_text(request.form.get('doc_id'), 20)
    if not doc_id.isdigit():
        flash('文件編號格式錯誤', category='danger')
        return redirect('/p/list')

    reason = normalize_text(request.form.get('reason'), 500) or None

    next_approver = db.get_next_pending_approver(doc_id)
    if not next_approver or int(next_approver['user_id']) != int(session['user_id']):
        flash('目前不是你的簽核順序，請等待前一位簽核完成', category='danger')
        return redirect(f'/p/view/{doc_id}')

    db.update_doc_app(doc_id, session['user_id'], 2, reason)
    db.update_doc_status(doc_id, 3)
    logger.info('Document rejected: doc_id=%s approver=%s reason=%s', doc_id, session.get('user_id'), reason)

    doc = db.get_single_documents(doc_id)
    if doc:
        approver_name = f"{session.get('username', '')}"
        try:
            email.send_approval_status_email(doc_id, doc.creator, doc.title, approver_name, 'reject', reason)
        except Exception:
            logger.warning('Rejection notification email failed: doc_id=%s', doc_id)

    return redirect('/p/list')


@approval_bp.route('/p/delete', methods=['POST'])
def p_delete():
    if not has_permission('p_view', session['user_id'], session['team_id'], session['role_id']):
        abort(403)

    doc_id = normalize_text(request.form.get('doc_id'), 20)
    if not doc_id.isdigit():
        flash('文件編號格式錯誤', category='danger')
        return redirect('/p/list')

    db.update_doc_app(doc_id, session['user_id'], 4)
    db.update_doc_status(doc_id, 4)
    logger.info('Document deleted: doc_id=%s user=%s', doc_id, session.get('user_id'))
    return redirect('/p/list')
