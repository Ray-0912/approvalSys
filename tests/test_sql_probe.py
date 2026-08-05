import os
import pytest

from scripts.sql_write_delete_probe import run_probe


@pytest.mark.skipif(
    os.getenv('RUN_DB_WRITE_TEST', '0') != '1',
    reason='Set RUN_DB_WRITE_TEST=1 to enable real DB write/delete probe test',
)
def test_sql_write_delete_probe_rollback():
    assert run_probe(commit_changes=False) is True
