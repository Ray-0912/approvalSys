import mysql.connector


def get_db_connection():
    connection = mysql.connector.connect(
        host='192.168.1.4',
        user='remote',
        password='!QAZxdr5',
        database='approvalSys'
    )
    return connection
