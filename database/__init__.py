import mysql.connector
import os
from contextlib import contextmanager


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
