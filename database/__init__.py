import mysql.connector
import os
from contextlib import contextmanager


def _ensure_salary_day_rate_override_table(connection):
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS salary_day_rate_override (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    user_id BIGINT NOT NULL,
                    work_date DATE NOT NULL,
                    rate DECIMAL(10,2) NOT NULL,
                    updated_by BIGINT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_salary_day_rate_override (user_id, work_date)
                )
                """
            )
            connection.commit()
    except Exception:
        pass


def get_db_connection():
    db_host = os.getenv('DB_HOST', '127.0.0.1')
    db_port = int(os.getenv('DB_PORT', '3306'))
    db_user = os.getenv('DB_USER', '')
    db_password = os.getenv('DB_PASSWORD', '')
    db_name = os.getenv('DB_NAME', 'approvalSys')

    if not db_user:
        raise RuntimeError('DB_USER is not configured')

    connection = mysql.connector.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database=db_name
    )
    _ensure_salary_day_rate_override_table(connection)
    return connection


@contextmanager
def transaction(connection):
    try:
        connection.start_transaction()
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
