import argparse
import logging
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('sql_probe')


def run_probe(commit_changes=False):
    """
    Run a safe SQL write/delete probe.

    Default behavior is rollback-only so no persistent data is left behind.
    """
    marker = f"probe-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        conn.start_transaction()

        # Insert a probe row
        insert_sql = (
            "INSERT INTO schedule_comments (department, month_str, content) "
            "VALUES (%s, %s, %s)"
        )
        insert_values = ('FD', '2099-12', f'SQL probe marker: {marker}')
        cursor.execute(insert_sql, insert_values)
        inserted_id = cursor.lastrowid
        logger.info('Insert OK: id=%s marker=%s', inserted_id, marker)

        # Validate inserted row
        cursor.execute('SELECT content FROM schedule_comments WHERE id=%s', (inserted_id,))
        row = cursor.fetchone()
        if not row or marker not in row[0]:
            raise RuntimeError('Probe insert validation failed')
        logger.info('Insert validation OK')

        # Delete the probe row
        cursor.execute('DELETE FROM schedule_comments WHERE id=%s', (inserted_id,))
        logger.info('Delete OK: id=%s', inserted_id)

        # Validate deleted row
        cursor.execute('SELECT COUNT(*) FROM schedule_comments WHERE id=%s', (inserted_id,))
        remaining = cursor.fetchone()[0]
        if remaining != 0:
            raise RuntimeError('Probe delete validation failed')
        logger.info('Delete validation OK')

        if commit_changes:
            conn.commit()
            logger.warning('Probe transaction committed (explicit)')
        else:
            conn.rollback()
            logger.info('Probe transaction rolled back (default safe mode)')

        return True
    except Exception as exc:
        conn.rollback()
        logger.exception('SQL probe failed: %s', exc)
        return False
    finally:
        cursor.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Safe SQL write/delete probe for approvalSys')
    parser.add_argument('--commit', action='store_true', help='Commit probe transaction (not recommended)')
    args = parser.parse_args()

    ok = run_probe(commit_changes=args.commit)
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
