import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import ROOT_DIR

sender_email = 's1034603@gmail.com'
server = smtplib.SMTP('smtp.gmail.com', 587)


def send_email(doc_id, receiver_app_users, receiver_notify_users, subject, message):
    template_path = os.path.join(ROOT_DIR, 'templates', 'utility', 'email_template', 'email_notifyNewApproval.html')

    with open(template_path, 'r') as file:
        html_content = file.read()

    html_content = html_content.replace('{title}', subject)
    html_content = html_content.replace('{content}', message)
    html_content = html_content.replace('{doc_id}', str(doc_id))
    receiver_emails = []

    for item in receiver_app_users:
        receiver_emails.append(item)
    for item in receiver_notify_users:
        if item not in receiver_emails:
            receiver_emails.append(item)

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ', '.join(receiver_emails)
        print(msg['To'])
        msg['Subject'] = f'New*新簽呈通知郵件 - {subject}'
        msg.attach(MIMEText(html_content, 'html'))

        server.starttls()

        server.login(sender_email, 'zfdugowgogaotezm')

        server.sendmail(sender_email, receiver_emails, msg.as_string())
    except Exception as e:
        print('郵件發送失敗:', str(e))

    finally:
        print('郵件發送成功')
        server.quit()
