from types import SimpleNamespace

import pytest

from main import app
import database.queries as db


@pytest.fixture()
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        with test_client.session_transaction() as session_data:
            session_data['logged_in'] = True
            session_data['username'] = 'tester'
            session_data['user_id'] = 1
            session_data['team_id'] = 1
            session_data['role_id'] = 0
            session_data['clock_id'] = '123'
        yield test_client


def _doc(doc_id, title, doc_type_cht, creator_name):
    return SimpleNamespace(
        doc_id=doc_id,
        creator=1 if creator_name == 'Alice' else 2,
        title=title,
        doc_type_cht=doc_type_cht,
        creator_name=creator_name,
        create_time=SimpleNamespace(strftime=lambda fmt: '2026-08-06')
    )


def test_approval_list_supports_multifilter(client, monkeypatch):
    docs = [
        _doc(1, 'Leave request A', '請假', 'Alice'),
        _doc(2, 'Procurement B', '採購', 'Bob'),
        _doc(3, 'Leave request C', '請假', 'Bob'),
    ]

    monkeypatch.setattr(db, 'get_30days_doc', lambda creator=None: docs)
    monkeypatch.setattr(db, 'get_unapproved_doc_by_user', lambda user_id: docs)

    response = client.get('/p/list?title_q=leave&type_filter=請假&creator_filter=1')

    assert response.status_code == 200
    assert b'Leave request A' in response.data
    assert b'Procurement B' not in response.data
    assert b'Leave request C' not in response.data
