from database import get_db_connection
from database.models import Role, Team, Document
import bcrypt

# 獲取角色列表
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


# 檢查使用者名稱是否已存在
def check_existing_username(username):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT user_id FROM user WHERE username = %s', (username,))
            result = cursor.fetchone()
            return result is not None


# 插入使用者資訊到資料庫中
def insert_user(username, password, role_id, team_id, phone):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            # 檢查是否有重複的使用者名稱
            if check_existing_username(username):
                return False

            # 使用 bcrypt 加密密碼
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

            # 將使用者資訊插入到資料庫中
            query = "INSERT INTO user (username, password, role_id, team_id, phone) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(query, (username, hashed_password.decode('utf-8'), role_id, team_id, phone))
            connection.commit()

    return True


def verify_password(username, password):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            # 查詢資料庫中的密碼哈希值
            query = "SELECT password FROM user WHERE username = %s"
            cursor.execute(query, (username,))
            result = cursor.fetchone()

            # 如果查詢結果不為空，則檢查密碼是否匹配
            if result is not None:
                hashed_password = result[0]

                # 使用 bcrypt 的 checkpw 函式來驗證密碼
                if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
                    return True

    return False

def get_pending_documents():
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            query = "SELECT * FROM document"
            cursor.execute(query)
            result = cursor.fetchall()

            pending_documents = []
            for row in result:
                document = Document(
                    doc_id=row['doc_id'],
                    creator=row['creator'],
                    name=row['name'],
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
