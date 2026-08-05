from database import get_db_connection, transaction
from database.models import User, Role, Team, Document, AppRecord
from datetime import datetime
import bcrypt
import logging
from typing import Any, Optional


logger = logging.getLogger('approval_system.queries')


# About Users
def get_roles() -> list[Role]:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT role_id, name FROM role')
            result = cursor.fetchall()
            roles = []
            for role in result:
                role = Role(role[0], role[1])
                roles.append(role)
            return roles

def get_all_users_admin() -> list[dict[str, Any]]:
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT u.*, r.name as role_name, t.name as team_name " \
                    "FROM user u " \
                    "LEFT JOIN role r ON u.role_id = r.role_id " \
                    "LEFT JOIN team t ON u.team_id = t.team_id " \
                    "ORDER BY u.user_id DESC"
            cursor.execute(query)
            return cursor.fetchall()
            
def get_user_by_id(user_id: int | str) -> dict[str, Any] | None:
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT * FROM user WHERE user_id = %s"
            cursor.execute(query, (user_id,))
            return cursor.fetchone()

def update_user_admin(user_id: int | str, first_name: str, last_name: str, email: str, phone: str,
                      role_id: int | str, team_id: int | str, password: str | None = None) -> bool:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            if password:
                hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                query = "UPDATE user SET first_name=%s, last_name=%s, email=%s, phone=%s, role_id=%s, team_id=%s, password=%s WHERE user_id=%s"
                cursor.execute(query, (first_name, last_name, email, phone, role_id, team_id, hashed_password.decode('utf-8'), user_id))
            else:
                query = "UPDATE user SET first_name=%s, last_name=%s, email=%s, phone=%s, role_id=%s, team_id=%s WHERE user_id=%s"
                cursor.execute(query, (first_name, last_name, email, phone, role_id, team_id, user_id))
            connection.commit()
    return True


def get_teams() -> list[Team]:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT team_id, name FROM team')
            result = cursor.fetchall()
            teams = []
            for team in result:
                team = Team(team[0], team[1])
                teams.append(team)
            return teams


def check_existing_username(username: str) -> bool:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT user_id FROM user WHERE username = %s', (username,))
            result = cursor.fetchone()
            return result is not None


def insert_user(username: str, password: str, first_name: str, last_name: str,
                role_id: int | str, team_id: int | str, phone: str, email: str) -> bool:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            if check_existing_username(username):
                return False

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

            query = "INSERT INTO user (username, password, first_name, last_name, role_id, team_id, phone, email, activation) " \
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)"
            cursor.execute(query, (username, hashed_password.decode('utf-8'), first_name, last_name, role_id,
                                   team_id, phone, email))
            connection.commit()

    return True


def import_user(username: str, password: str, first_name: str, last_name: str,
                role_id: int | str, team_id: int | str, phone: str, email: str,
                clock_id: str | int) -> bool:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            if check_existing_username(username):
                return False

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

            query = "INSERT INTO user (username, password, first_name, last_name, role_id, team_id, phone, email, clock_id, activation) " \
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)"
            cursor.execute(query, (username, hashed_password.decode('utf-8'), first_name, last_name, role_id,
                                   team_id, phone, email, clock_id))
            connection.commit()
    return True

def verify_password(username: str, password: str) -> tuple[Any, ...] | None:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = "SELECT user_id, username, password, role_id, team_id, phone, email, first_name, last_name, clock_id " \
                    "FROM user " \
                    "WHERE username = %s"
            cursor.execute(query, (username,))
            result = cursor.fetchone()

            if result is not None:
                hashed_password = result[2]

                if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
                    return result

    return None


def update_password(username: str, password: str) -> int:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = "UPDATE user SET password = %s WHERE username = %s"

            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

            cursor.execute(query, (hashed_password, username))
        connection.commit()
    return 1


def update_user_profile(user_id: int | str, firstname: str, lastname: str, e_mail: str,
                        phone: str, password: str = '') -> int:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            if password:
                query = "UPDATE user SET first_name = %s, last_name = %s, email = %s, phone = %s, password = %s " \
                        "WHERE user_id = %s"

                hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

                cursor.execute(query, (firstname, lastname, e_mail, phone, hashed_password, user_id))
            else:
                query = "UPDATE user SET first_name = %s, last_name = %s, email = %s, phone = %s " \
                        "WHERE user_id = %s"

                cursor.execute(query, (firstname, lastname, e_mail, phone, user_id))

        connection.commit()
    return 1


# todo exception function
def get_single_email_from_user_id(user_id: int | str) -> str:
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT email FROM user WHERE user_id = %s"

            cursor.execute(query, (user_id,))
            result = cursor.fetchone()

            return result['email'] if result else ''


# About Document
def get_30days_doc(creator: int | str | None = None) -> list[Document]:
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT * FROM documents_data WHERE (create_time > CURDATE() - INTERVAL 30 DAY)"
            params = []
            if creator is not None:
                query += " AND creator = %s"
                params.append(creator)
            
            cursor.execute(query, tuple(params))
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


def get_in_search_doc(created_time: str, p_type: str | None, content: str) -> list[Document]:
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            start_time, end_time = format_date_for_sql(created_time)
            query = "SELECT * FROM documents_data WHERE (create_time >= %s AND create_time <= %s)"
            params = [start_time, end_time]
            
            if p_type is not None:
                query += " AND type = %s"
                params.append(p_type)
            
            if content != '':
                # Using parameter for MATCH AGAINST is tricky in some drivers, but standard %s works in most for string literals.
                # However, full text search MATCH(title, content) AGAINST (%s) should work.
                query += " AND MATCH(title, content) AGAINST(%s)"
                params.append(content)
                
            cursor.execute(query, tuple(params))
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
def format_date_for_sql(date: str) -> tuple[str, str]:
    if not isinstance(date, str):
        raise ValueError('date must be a string in MM/DD/YYYY - MM/DD/YYYY format')

    start_date, end_date = date.split(" - ")
    start_date_obj = datetime.strptime(start_date, "%m/%d/%Y")
    end_date_obj = datetime.strptime(end_date, "%m/%d/%Y")
    formatted_start_date = start_date_obj.strftime("%Y-%m-%d")
    formatted_end_date = end_date_obj.strftime("%Y-%m-%d")
    return formatted_start_date, formatted_end_date
def get_unapproved_doc_by_user(user_id: int | str) -> list[Document]:
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


def insert_document(creator: int | str, creator_name: str, signature_required: int, doc_type: str,
                    doc_title: str, doc_content: str, user_agent: str) -> int:
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


def insert_doc_approval(doc_id: int | str, object_ids: list[str] | list[int]) -> bool:
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


def create_document_with_approvals(creator, creator_name, signature_required, doc_type,
                                   doc_title, doc_content, user_agent, object_ids):
    if not object_ids:
        return None

    with get_db_connection() as connection:
        cursor = connection.cursor()
        try:
            with transaction(connection):
                query = "INSERT INTO document (creator, signature_required, type, title, content, status, status_remark) " \
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
                current_time = datetime.now()
                formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
                status_remark = "Editor: " + creator_name + ", Time: " + formatted_time + ", Agent: " + user_agent

                cursor.execute(query, (creator, signature_required, doc_type, doc_title, doc_content, 1, status_remark))
                inserted_id = cursor.lastrowid

                approval_query = "INSERT INTO doc_approval_record (pk_doc_id, pk_user_id) VALUES (%s, %s)"
                for object_id in object_ids:
                    cursor.execute(approval_query, (inserted_id, object_id))

                return inserted_id
        except Exception:
            raise
        finally:
            cursor.close()


def update_doc(doc_id: int | str, title: str, doc_type: str, signature_required: int,
               content: str, user_agent: str, creator_name: str) -> bool:
    original_app = get_single_documents(doc_id)
    if original_app is None:
        return False

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


def update_doc_app(doc_id: int | str, user_id: int | str, status: int, reason: str = None) -> bool:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            if status == 3:
                del_query = "DELETE FROM doc_approval_record WHERE pk_doc_id = %s"
                cursor.execute(del_query, (doc_id,))
                connection.commit()
                return True
            else:
                current_time = datetime.now()
                formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
                query = ("UPDATE doc_approval_record "
                         "SET status = %s, approval_time = %s, reason = %s "
                         "WHERE pk_doc_id = %s AND pk_user_id = %s")
                cursor.execute(query, (status, formatted_time, reason, doc_id, user_id))
                connection.commit()
                return True


def update_doc_status(doc_id: int | str, status: int) -> bool:
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
                    email=row['email'],
                    role_id=row['role_id'],
                    team_id=row['team_id'],
                    role_name=row['role_name'],
                    team_name=row['team_name'],
                    clock_id=0
                )
                pending_users.append(user)

            return pending_users


def get_single_documents(doc_id: int | str) -> Document | None:
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT * FROM document WHERE doc_id = %s"
            cursor.execute(query, (doc_id,))
            result = cursor.fetchall()

            if result:
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


def get_next_pending_approver(doc_id: int | str) -> dict[str, Any] | None:
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = (
                "SELECT record.pk_user_id AS user_id, user.username, user.first_name, user.last_name, record.doc_ap_id "
                "FROM doc_approval_record AS record "
                "LEFT JOIN user ON user.user_id = record.pk_user_id "
                "WHERE record.pk_doc_id = %s AND record.status = 0 "
                "ORDER BY record.doc_ap_id ASC LIMIT 1"
            )
            cursor.execute(query, (doc_id,))
            return cursor.fetchone()


def get_approve_record_all(doc_id: int | str) -> list[AppRecord] | None:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            check_query = ("SELECT record.doc_ap_id, record.status, record.approval_time, "
                           "record.create_time, user.username, record.reason "
                           "FROM doc_approval_record as record "
                           "LEFT JOIN user ON user.user_id = record.pk_user_id "
                           "WHERE record.pk_doc_id = %s "
                           "ORDER BY record.doc_ap_id ASC")
            cursor.execute(check_query, (doc_id,))
            result = cursor.fetchall()

            records = []
            if result:
                for row in result:
                    app_record = AppRecord(
                        doc_ap_id=row[0],
                        status=row[1],
                        approval_time=row[2],
                        create_time=row[3],
                        username=row[4],
                        reason=row[5]
                    )
                    records.append(app_record)
                return records
            else:
                return None


def get_all_users_with_clock_id():
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT user_id, username, first_name, last_name, clock_id, team_id FROM user WHERE clock_id IS NOT NULL AND clock_id != '' ORDER BY team_id ASC"
            cursor.execute(query)
            result = cursor.fetchall()
            return result


# Schedule Management
def get_shift_types(only_active=True):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT * FROM shift_type"
            if only_active:
                query += " WHERE is_active = 1"
            cursor.execute(query)
            return cursor.fetchall()

def save_shift_type(name, start_time, end_time, color, shift_id=None, is_active=True):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            if shift_id:
                query = "UPDATE shift_type SET name=%s, start_time=%s, end_time=%s, color=%s, is_active=%s WHERE id=%s"
                cursor.execute(query, (name, start_time, end_time, color, is_active, shift_id))
            else:
                query = "INSERT INTO shift_type (name, start_time, end_time, color, is_active) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, start_time, end_time, color, is_active))
            connection.commit()
            return True

def get_schedules(start_date, end_date, team_ids=None):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = """
                SELECT s.*, u.first_name, u.last_name, st.name as shift_name, st.color as shift_color, st.start_time, st.end_time 
                FROM schedule s
                JOIN user u ON s.user_id = u.user_id
                JOIN shift_type st ON s.shift_type_id = st.id
                WHERE s.date >= %s AND s.date <= %s
            """
            params = [start_date, end_date]
            
            if team_ids:
                format_strings = ','.join(['%s'] * len(team_ids))
                query += f" AND u.team_id IN ({format_strings})"
                params.extend(team_ids)
                
            cursor.execute(query, tuple(params))
            return cursor.fetchall()

def save_schedule(user_id, date, shift_type_id, creator_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            # Check if exists
            check_query = "SELECT id FROM schedule WHERE user_id=%s AND date=%s"
            cursor.execute(check_query, (user_id, date))
            result = cursor.fetchone()
            
            if result:
                # Update
                query = "UPDATE schedule SET shift_type_id=%s, created_by=%s WHERE id=%s"
                cursor.execute(query, (shift_type_id, creator_id, result[0]))
            else:
                # Insert
                query = "INSERT INTO schedule (user_id, date, shift_type_id, created_by) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (user_id, date, shift_type_id, creator_id))
            
            connection.commit()
            return True

def delete_schedule(user_id, date):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = "DELETE FROM schedule WHERE user_id=%s AND date=%s"
            cursor.execute(query, (user_id, date))
            connection.commit()
            return True

def get_user_by_clock_id(clock_id):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            # Ensure clock_id is treating as string or int depending on DB, but usually string for PIN
            query = "SELECT user_id, first_name, last_name FROM user WHERE clock_id = %s"
            cursor.execute(query, (clock_id,))
            return cursor.fetchone()

def get_user_schedule_by_date(user_id, date):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            # Join with shift_type to get the full shift window.
            query = """
                SELECT st.name AS shift_name, st.start_time, st.end_time, st.color
                FROM schedule s
                JOIN shift_type st ON s.shift_type_id = st.id
                WHERE s.user_id = %s AND s.date = %s
            """
            cursor.execute(query, (user_id, date))
            return cursor.fetchone()


def get_user_schedules_in_range(user_id, start_date, end_date):
    """Returns {date: schedule_row} for all scheduled days in range."""
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = """
                SELECT s.date, st.start_time, st.end_time, st.name AS shift_name
                FROM schedule s
                JOIN shift_type st ON s.shift_type_id = st.id
                WHERE s.user_id = %s AND s.date >= %s AND s.date <= %s
            """
            cursor.execute(query, (user_id, start_date, end_date))
            return {row['date']: row for row in cursor.fetchall()}


def get_pending_approval_count(user_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM doc_approval_record WHERE pk_user_id = %s AND status = 0",
                (user_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else 0


def get_active_numeric_users():
    """Returns active users whose username is a numeric employee PIN (BioLife accounts)."""
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT user_id, username, first_name, last_name, email, role_id, team_id, clock_id "
                "FROM user WHERE activation = 1 AND username REGEXP '^[0-9]+$'"
            )
            return cursor.fetchall()


def set_users_inactive(user_ids: list):
    if not user_ids:
        return
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            fmt = ','.join(['%s'] * len(user_ids))
            cursor.execute(f"UPDATE user SET activation = 0 WHERE user_id IN ({fmt})", tuple(user_ids))
            connection.commit()


def get_user_by_username(username: str):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM user WHERE username = %s", (username,))
            return cursor.fetchone()


# Schedule off-request
def get_off_requests_for_month(user_id, month_str):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT * FROM schedule_off_request WHERE user_id=%s AND DATE_FORMAT(request_date,'%%Y-%%m')=%s",
                (user_id, month_str)
            )
            return cursor.fetchall()


def get_off_requests_by_dates(dates: list):
    """Returns all requests for given dates with requester info."""
    if not dates:
        return []
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            fmt = ','.join(['%s'] * len(dates))
            cursor.execute(
                f"SELECT r.*, u.first_name, u.last_name, u.team_id "
                f"FROM schedule_off_request r JOIN user u ON r.user_id = u.user_id "
                f"WHERE r.request_date IN ({fmt}) AND r.status != 'cancelled'",
                tuple(dates)
            )
            return cursor.fetchall()


def upsert_off_request(user_id, request_date, note):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO schedule_off_request (user_id, request_date, note) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE note=%s, status='pending'",
                (user_id, request_date, note, note)
            )
            connection.commit()


def cancel_off_request(user_id, request_date):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM schedule_off_request WHERE user_id=%s AND request_date=%s",
                (user_id, request_date)
            )
            connection.commit()


def get_all_off_requests_for_month(month_str, team_id=None):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = (
                "SELECT r.*, u.first_name, u.last_name, u.team_id "
                "FROM schedule_off_request r JOIN user u ON r.user_id = u.user_id "
                "WHERE DATE_FORMAT(r.request_date,'%%Y-%%m')=%s"
            )
            params = [month_str]
            if team_id is not None:
                query += " AND u.team_id=%s"
                params.append(team_id)
            cursor.execute(query, tuple(params))
            return cursor.fetchall()


def get_scheduling_constraints():
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT sc.*, st.name as shift_name FROM scheduling_constraint sc "
                "JOIN shift_type st ON sc.shift_type_id = st.id"
            )
            return cursor.fetchall()


def upsert_scheduling_constraint(team_id, shift_type_id, min_count, created_by):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO scheduling_constraint (team_id, shift_type_id, min_count, created_by) "
                "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE min_count=%s",
                (team_id, shift_type_id, min_count, created_by, min_count)
            )
            connection.commit()


# Comments
from datetime import timedelta 

def get_schedule_comment(department, month_str):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = "SELECT content FROM schedule_comments WHERE department=%s AND month_str=%s"
            cursor.execute(query, (department, month_str))
            result = cursor.fetchone()
            return result[0] if result else ""

def save_schedule_comment(department, month_str, content):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            # Upsert
            query = """
                INSERT INTO schedule_comments (department, month_str, content) 
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE content=%s
            """
            cursor.execute(query, (department, month_str, content, content))
            connection.commit()
            return True

def get_previous_month_comment(department, current_month_str):
    # current_month_str is 'YYYY-MM'
    # Calculate previous month
    try:
        curr = datetime.strptime(current_month_str, "%Y-%m")
        # subtract one month: replace day=1, minus 1 day, then format
        prev_date = curr.replace(day=1) - timedelta(days=1)
        prev_month_str = prev_date.strftime("%Y-%m")
        return get_schedule_comment(department, prev_month_str)
    except ValueError:
        return ""
    except Exception as exc:
        logger.exception('Failed to get previous month comment: department=%s month=%s error=%s',
                         department, current_month_str, exc)
        return ""


# Role Permission Management
def get_role_permissions_map():
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT role_id, permission_key, allowed FROM role_permissions")
            rows = cursor.fetchall()

    permissions = {}
    for row in rows:
        permissions.setdefault(int(row['role_id']), {})[row['permission_key']] = bool(row['allowed'])
    return permissions


def set_role_permission(role_id, permission_key, allowed, operator_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = (
                "INSERT INTO role_permissions (role_id, permission_key, allowed, updated_by) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE allowed=%s, updated_by=%s, updated_at=CURRENT_TIMESTAMP"
            )
            cursor.execute(query, (role_id, permission_key, int(bool(allowed)), operator_id,
                                   int(bool(allowed)), operator_id))
            connection.commit()
    return True


def get_roles_simple():
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT role_id, name FROM role ORDER BY role_id")
            return cursor.fetchall()


# Salary Rule & Profile
def get_active_salary_rule(year_month=None):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            if year_month:
                # Use last day of month so rules created mid-month still apply.
                query = (
                    "SELECT * FROM salary_rule_version "
                    "WHERE effective_from <= LAST_DAY(%s) "
                    "ORDER BY effective_from DESC, id DESC LIMIT 1"
                )
                cursor.execute(query, (f"{year_month}-01",))
            else:
                query = "SELECT * FROM salary_rule_version ORDER BY effective_from DESC, id DESC LIMIT 1"
                cursor.execute(query)
            return cursor.fetchone()


def create_salary_rule_version(version_name, effective_from, overtime_monthly_multiplier,
                               overtime_hourly_multiplier, holiday_multiplier,
                               grace_late_minutes, grace_early_minutes,
                               regular_hours_staff, regular_hours_manager,
                               created_by, late_deduction_per_instance=None,
                               default_hourly_rate=None):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = (
                "INSERT INTO salary_rule_version "
                "(version_name, effective_from, overtime_monthly_multiplier, overtime_hourly_multiplier, "
                "holiday_multiplier, grace_late_minutes, grace_early_minutes, regular_hours_staff, "
                "regular_hours_manager, created_by, late_deduction_per_instance, default_hourly_rate) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            )
            cursor.execute(query, (version_name, effective_from, overtime_monthly_multiplier,
                                   overtime_hourly_multiplier, holiday_multiplier,
                                   grace_late_minutes, grace_early_minutes,
                                   regular_hours_staff, regular_hours_manager, created_by,
                                   late_deduction_per_instance,
                                   default_hourly_rate if default_hourly_rate is not None else 200))
            connection.commit()
            return cursor.lastrowid


def get_salary_profiles():
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = (
                "SELECT u.user_id, u.username, u.first_name, u.last_name, u.role_id, u.team_id, u.clock_id, "
                "p.salary_type, p.monthly_salary, p.hourly_salary "
                "FROM user u "
                "LEFT JOIN employee_salary_profile p ON u.user_id = p.user_id "
                "WHERE u.activation = 1 "
                "ORDER BY u.user_id"
            )
            cursor.execute(query)
            return cursor.fetchall()


def upsert_salary_profile(user_id, salary_type, monthly_salary, hourly_salary, updated_by):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = (
                "INSERT INTO employee_salary_profile "
                "(user_id, salary_type, monthly_salary, hourly_salary, updated_by) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE salary_type=%s, monthly_salary=%s, hourly_salary=%s, "
                "updated_by=%s, updated_at=CURRENT_TIMESTAMP"
            )
            cursor.execute(query, (user_id, salary_type, monthly_salary, hourly_salary, updated_by,
                                   salary_type, monthly_salary, hourly_salary, updated_by))
            connection.commit()
    return True


def get_user_salary_profile(user_id):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT * FROM employee_salary_profile WHERE user_id=%s"
            cursor.execute(query, (user_id,))
            return cursor.fetchone()


def get_full_salary_profile_for_user(user_id):
    """Returns user info + salary profile joined, same shape as get_salary_profiles() rows."""
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = (
                "SELECT u.user_id, u.username, u.first_name, u.last_name, u.role_id, u.team_id, u.clock_id, "
                "p.salary_type, p.monthly_salary, p.hourly_salary "
                "FROM user u "
                "LEFT JOIN employee_salary_profile p ON u.user_id = p.user_id "
                "WHERE u.user_id = %s"
            )
            cursor.execute(query, (user_id,))
            return cursor.fetchone()


def save_salary_result(year_month, user_id, rule_version_id, total_work_minutes,
                       regular_minutes, overtime_minutes, holiday_minutes,
                       late_count, early_count, late_deduction, gross_salary,
                       net_salary, payroll_status='draft', submitted_by=None,
                       approved_by=None):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = (
                "INSERT INTO salary_monthly_result "
                "(`year_month`, user_id, rule_version_id, total_work_minutes, regular_minutes, overtime_minutes, "
                "holiday_minutes, late_count, early_count, late_deduction, gross_salary, net_salary, payroll_status, "
                "submitted_by, approved_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE rule_version_id=%s, total_work_minutes=%s, regular_minutes=%s, "
                "overtime_minutes=%s, holiday_minutes=%s, late_count=%s, early_count=%s, late_deduction=%s, "
                "gross_salary=%s, net_salary=%s, payroll_status=%s, submitted_by=%s, approved_by=%s, "
                "updated_at=CURRENT_TIMESTAMP"
            )
            cursor.execute(query, (
                year_month, user_id, rule_version_id, total_work_minutes, regular_minutes, overtime_minutes,
                holiday_minutes, late_count, early_count, late_deduction, gross_salary, net_salary,
                payroll_status, submitted_by, approved_by,
                rule_version_id, total_work_minutes, regular_minutes, overtime_minutes, holiday_minutes,
                late_count, early_count, late_deduction, gross_salary, net_salary, payroll_status,
                submitted_by, approved_by
            ))
            connection.commit()
    return True


def get_salary_results(year_month, requester_user_id=None, requester_role_id=None):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            base_query = (
                "SELECT r.*, u.username, u.first_name, u.last_name, u.team_id, u.role_id, "
                "v.version_name "
                "FROM salary_monthly_result r "
                "JOIN user u ON r.user_id = u.user_id AND u.activation = 1 "
                "LEFT JOIN salary_rule_version v ON r.rule_version_id = v.id "
                "WHERE r.`year_month`=%s"
            )
            params = [year_month]

            if requester_role_id not in [99, 0, 1, 2, 4]:
                base_query += " AND r.user_id=%s"
                params.append(requester_user_id)

            base_query += " ORDER BY u.team_id, u.user_id"
            cursor.execute(base_query, tuple(params))
            return cursor.fetchall()


def update_salary_status(year_month, user_ids, new_status, operator_id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            fmt = ','.join(['%s'] * len(user_ids))
            query = (
                f"UPDATE salary_monthly_result SET payroll_status=%s, "
                f"submitted_by=IF(%s='submitted', %s, submitted_by), "
                f"approved_by=IF(%s='approved', %s, approved_by), "
                f"updated_at=CURRENT_TIMESTAMP "
                f"WHERE `year_month`=%s AND user_id IN ({fmt})"
            )
            params = [new_status, new_status, operator_id, new_status, operator_id, year_month] + user_ids
            cursor.execute(query, tuple(params))
            connection.commit()
    return True


# Audit
def append_audit_log(entity_type, entity_id, action, changed_by, before_json, after_json,
                     ip_address=None, user_agent=None):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = (
                "INSERT INTO audit_log "
                "(entity_type, entity_id, action, changed_by, before_json, after_json, ip_address, user_agent) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )
            cursor.execute(query, (entity_type, entity_id, action, changed_by, before_json, after_json,
                                   ip_address, user_agent))
            connection.commit()
            return cursor.lastrowid


def get_audit_logs(limit: int = 200, offset: int = 0, entity_type: str | None = None) -> list[dict[str, Any]]:
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = (
                "SELECT a.*, u.username "
                "FROM audit_log a "
                "LEFT JOIN user u ON a.changed_by = u.user_id "
                "WHERE 1=1"
            )
            params: list[Any] = []

            if entity_type:
                query += " AND a.entity_type = %s"
                params.append(entity_type)

            query += " ORDER BY a.changed_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor.execute(query, tuple(params))
            return cursor.fetchall()


def get_audit_log_count(entity_type: str | None = None) -> int:
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = "SELECT COUNT(*) FROM audit_log WHERE 1=1"
            params: list[Any] = []

            if entity_type:
                query += " AND entity_type = %s"
                params.append(entity_type)

            cursor.execute(query, tuple(params))
            result = cursor.fetchone()
            return int(result[0]) if result else 0


def get_holidays_by_month(year_month, country_code='TW'):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = (
                "SELECT holiday_date, name FROM holiday_calendar "
                "WHERE DATE_FORMAT(holiday_date, '%%Y-%%m')=%s AND country_code=%s"
            )
            cursor.execute(query, (year_month, country_code))
            return cursor.fetchall()


def upsert_holiday(holiday_date, name, country_code, created_by):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            query = (
                "INSERT INTO holiday_calendar (holiday_date, name, country_code, created_by) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE name=%s"
            )
            cursor.execute(query, (holiday_date, name, country_code, created_by, name))
            connection.commit()
    return True
