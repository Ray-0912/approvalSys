import logging
from pathlib import Path

from database import get_db_connection


MIGRATIONS_DIR = Path(__file__).resolve().parent / 'versions'
logger = logging.getLogger('approval_system.migrations')


def ensure_migration_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(100) NOT NULL PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_applied_versions(cursor):
    cursor.execute('SELECT version FROM schema_migrations ORDER BY version')
    return {row[0] for row in cursor.fetchall()}


def load_sql_files():
    if not MIGRATIONS_DIR.exists():
        return []
    return sorted(MIGRATIONS_DIR.glob('*.sql'))


def run_migrations():
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            ensure_migration_table(cursor)
            applied_versions = get_applied_versions(cursor)

            for sql_file in load_sql_files():
                version = sql_file.stem
                if version in applied_versions:
                    continue

                sql_statements = [statement.strip() for statement in sql_file.read_text(encoding='utf-8').split(';') if statement.strip()]
                if not sql_statements:
                    continue

                for statement in sql_statements:
                    cursor.execute(statement)

                cursor.execute('INSERT INTO schema_migrations (version) VALUES (%s)', (version,))
                connection.commit()
                logger.info('migration_applied version=%s file=%s', version, sql_file.name)


def main():
    run_migrations()


if __name__ == '__main__':
    main()