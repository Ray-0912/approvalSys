from database import get_db_connection
from database.models import User, Role, Team, Document
from datetime import datetime
import bcrypt


# About User
def get_roles():
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT role_id, name FROM role')
            result = cursor.fetchall()
            roles = []
            for role in result:
                role = Role(role[0], role[1])
                roles.append(role)
            return roles


# 獲取團隊列表
def get_teams():
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT team_id, name FROM team')
            result = cursor.fetchall()
            teams = []
            for team in result:
                team = Team(team[0], team[1])
                teams.append(team)
            return teams


def check_existing_username(username):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT user_id FROM user WHERE username = %s', (username,))
            result = cursor.fetchone()
            return result is not None


def insert_user(username, password, first_name, last_name, role_id, team_id, phone, email):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            if check_existing_username(username):
                return False

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

            query = "INSERT INTO user (username, password, first_name, last_name, role_id, team_id, phone, email) " \
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            cursor.execute(query, (username, hashed_password.decode('utf-8'), first_name, last_name, role_id,
                                   team_id, phone, email))
            connection.commit()

    return True


def verify_password(username, password):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = "SELECT user_id, username, password, role_id, team_id, phone " \
                    "FROM user " \
                    "WHERE username = %s"
            cursor.execute(query, (username,))
            result = cursor.fetchone()

            if result is not None:
                hashed_password = result[2]

                if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
                    return result

    return None


def update_password(username, password):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = "UPDATE user SET password = %s WHERE username = %s"

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

            cursor.execute(query, (hashed_password, username))
        connection.commit()
    return 1


# About Document
def get_pending_doc(creator=None):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT * FROM documents_data " \
                    "WHERE (create_time > CURDATE() - INTERVAL 30 DAY)"
            if creator is not None:
                query = query + " AND creator = " + str(creator)
            cursor.execute(query)
            result = cursor.fetchall()

            pending_documents = []
            for row in result:
                document = Document(
                    doc_id=row['doc_id'],
                    creator=row['creator'],
                    creator_name=row['creator_name'],
                    title=row['title'],
                    doc_type=row['type'],
                    signature_required=row['signature_required'],
                    content=row['content'],
                    status=row['status'],
                    status_remark=row['status_remark'],
                    create_time=row['create_time'],
                    last_update=row['last_update']
                )
                pending_documents.append(document)

            return pending_documents


def get_unapproved_doc_by_user(user_id):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT vw_data.doc_id, vw_data.creator, vw_data.creator_name, vw_data.title, vw_data.type, " \
                    "vw_data.signature_required, vw_data.content, vw_data.status, vw_data.status_remark, " \
                    "vw_data.create_time, vw_data.last_update " \
                    "FROM doc_approval_record as record " \
                    "INNER JOIN documents_data as vw_data ON record.pk_doc_id = vw_data.doc_id " \
                    "WHERE record.pk_user_id = %s AND record.status = 0"

            cursor.execute(query, (user_id,))
            result = cursor.fetchall()

            pending_documents = []
            for row in result:
                document = Document(
                    doc_id=row['doc_id'],
                    creator=row['creator'],
                    creator_name=row['creator_name'],
                    title=row['title'],
                    doc_type=row['type'],
                    signature_required=row['signature_required'],
                    content=row['content'],
                    status=row['status'],
                    status_remark=row['status_remark'],
                    create_time=row['create_time'],
                    last_update=row['last_update']
                )
                pending_documents.append(document)

            return pending_documents


def insert_document(creator, creator_name, signature_required, doc_type, doc_title, doc_content, user_agent):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = "INSERT INTO document (creator, signature_required, type, title, content, status, status_remark) " \
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)"

            current_time = datetime.now()
            formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
            status_remark = "Editor: " + creator_name + ", Time: " + formatted_time + ", Agent: " + user_agent

            cursor.execute(query, (creator, signature_required, doc_type, doc_title, doc_content, 1, status_remark))

        connection.commit()

        inserted_id = cursor.lastrowid

    return inserted_id


def insert_doc_approval(doc_id, object_ids):
    if object_ids is not None:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                query = "INSERT INTO doc_approval_record (pk_doc_id, pk_user_id) VALUES (%s, %s)"

                for object_id in object_ids:
                    cursor.execute(query, (doc_id, object_id))

            connection.commit()

        return True
    else:
        return False


def update_doc(doc_id, title, doc_type, signature_required, content, user_agent, creator_name):
    original_app = get_single_documents(doc_id)
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            current_time = datetime.now()
            formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
            status_remark = "Editor: " + creator_name + ", Time: " + formatted_time + ", Agent: " + user_agent
            new_status_remark = original_app.status_remark + "<br>" + status_remark
            doc_query = "UPDATE document " \
                        "SET title = %s, type = %s, signature_required = %s, content = %s, status_remark = %s " \
                        "WHERE doc_id = %s"

            approval_user_query = "UPDATE doc_approval_record " \
                                  "SET status = 0 " \
                                  "WHERE pk_doc_id = %s"

            cursor.execute(doc_query, (title, doc_type, signature_required, content, new_status_remark, doc_id))
            cursor.execute(approval_user_query, (doc_id,))
            connection.commit()
        return True


def update_doc_app(doc_id, user_id, status):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            if status == 3 or 4:
                del_query = "DELETE FROM doc_approval_record WHERE pk_doc_id = %s"
                cursor.execute(del_query, (doc_id,))

                return True
            else:
                current_time = datetime.now()
                formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
                query = "UPDATE doc_approval_record " \
                        "SET status = %s, approval_time = %s " \
                        "WHERE pk_doc_id = %s AND pk_user_id = %s"

                cursor.execute(query, (status, formatted_time, doc_id, user_id))
                connection.commit()

                return True


def update_doc_status(doc_id, status):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            if status == 2:
                check_query = "SELECT COUNT(*) as amount FROM doc_approval_record WHERE pk_doc_id = %s AND status = 0"
                cursor.execute(check_query, (doc_id,))
                result = cursor.fetchall()
                if result[0][0] == 0:
                    update_query = "UPDATE document SET status = %s WHERE doc_id = %s"
                    cursor.execute(update_query, (status, doc_id))
                    connection.commit()
            elif status == 3:
                update_query = "UPDATE document SET status = %s WHERE doc_id = %s"
                cursor.execute(update_query, (status, doc_id))
                connection.commit()
            elif status == 4:
                delete_query = "DELETE FROM document WHERE doc_id = %s"
                cursor.execute(delete_query, (doc_id,))
                connection.commit()
    return True


def get_approval_users(user_id):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT * FROM vw_user_data_combine WHERE user_id != %s ORDER BY team_id ASC"
            cursor.execute(query, (user_id,))
            result = cursor.fetchall()

            pending_users = []
            for row in result:
                user = User(
                    user_id=row['user_id'],
                    username=row['username'],
                    first_name=row['first_name'],
                    last_name=row['last_name'],
                    role_id=row['role_id'],
                    team_id=row['team_id'],
                    role_name=row['role_name'],
                    team_name=row['team_name']
                )
                pending_users.append(user)

            return pending_users


def get_single_documents(doc_id):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT * FROM document WHERE doc_id = %s"
            cursor.execute(query, (doc_id,))
            result = cursor.fetchall()

            if result is not []:
                document = Document(
                    doc_id=result[0]['doc_id'],
                    creator=result[0]['creator'],
                    title=result[0]['title'],
                    doc_type=result[0]['type'],
                    signature_required=result[0]['signature_required'],
                    content=result[0]['content'],
                    status=result[0]['status'],
                    status_remark=result[0]['status_remark'],
                    create_time=result[0]['create_time'],
                    last_update=result[0]['last_update']
                )

                return document
            else:
                return None


def get_approve_record_by_user(user_id, doc_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            check_query = "SELECT COUNT(*) as amount FROM doc_approval_record " \
                          "WHERE pk_doc_id = %s AND status = 0 AND pk_user_id = %s"
            cursor.execute(check_query, (doc_id, user_id))
            result = cursor.fetchall()

            return result[0][0]
