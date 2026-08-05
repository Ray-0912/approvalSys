import smtplib
import os
import base64
import logging
import database.queries as db
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import ROOT_DIR

SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
SENDER_EMAIL = os.getenv('SMTP_SENDER_EMAIL', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
DEFAULT_NOTIFY_EMAIL = os.getenv('DEFAULT_NOTIFY_EMAIL', '').strip()
logger = logging.getLogger('approval_system.email')


def load_image_as_base64(path):
    with open(path, 'rb') as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return f"data:image/png;base64,{encoded_string}"


def _build_receiver_list(receiver_app_users, receiver_notify_users):
    receiver_emails = []
    if DEFAULT_NOTIFY_EMAIL:
        receiver_emails.append(DEFAULT_NOTIFY_EMAIL)

    for item in receiver_app_users:
        receiver_emails.append(db.get_single_email_from_user_id(item))

    for item in receiver_notify_users:
        if item not in receiver_emails:
            receiver_emails.append(item)

    return [email for email in receiver_emails if email]


def _send_mail(subject, html_content, receiver_emails):
    if not SENDER_EMAIL or not SMTP_PASSWORD:
        logger.error('郵件發送失敗: 請先設定 SMTP_SENDER_EMAIL 與 SMTP_PASSWORD')
        return False

    if not receiver_emails:
        logger.error('郵件發送失敗: 收件人為空')
        return False

    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = ', '.join(receiver_emails)
        msg['Subject'] = f'New*新簽呈通知郵件 - {subject}'
        msg.attach(MIMEText(html_content, 'html'))

        if SMTP_USE_TLS:
            server.starttls()

        server.login(SENDER_EMAIL, SMTP_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_emails, msg.as_string())
        logger.info('郵件發送成功: recipients=%s subject=%s', len(receiver_emails), subject)
        return True
    except Exception as e:
        logger.exception('郵件發送失敗: %s', e)
        return False
    finally:
        server.quit()


def send_email(doc_id, receiver_app_users, receiver_notify_users, subject, message):
    template_path = os.path.join(ROOT_DIR, 'templates', 'utility', 'email_template', 'email_notifyNewApproval.html')

    with open(template_path, encoding='utf-8') as file:
        html_content = file.read()

    html_content = html_content.replace('{title}', subject)
    html_content = html_content.replace('{content}', message)
    html_content = html_content.replace('{doc_id}', str(doc_id))
    receiver_emails = _build_receiver_list(receiver_app_users, receiver_notify_users)
    return _send_mail(subject, html_content, receiver_emails)


def send_approval_status_email(doc_id, creator_user_id, title, approver_name, action, reason=None):
    """Notify the document creator when an approver approves or rejects."""
    creator_email = db.get_single_email_from_user_id(creator_user_id)
    if not creator_email:
        return False

    action_text = '核准' if action == 'approve' else '駁回'
    subject = f'簽呈{action_text}通知 - {title}'

    body_lines = [
        f'<p>您的簽呈「{title}」已由 <strong>{approver_name}</strong> {action_text}。</p>',
        f'<p>簽呈編號：<a href="/p/view/{doc_id}">{doc_id}</a></p>',
    ]
    if reason:
        body_lines.append(f'<p>原因：{reason}</p>')

    html_content = (
        '<html><body>'
        + ''.join(body_lines)
        + '</body></html>'
    )
    return _send_mail(subject, html_content, [creator_email])


def send_hr_email(doc_id, receiver_app_users, receiver_notify_users, subject, message):
    return send_email(doc_id, receiver_app_users, receiver_notify_users, subject, message)