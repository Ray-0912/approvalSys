from types import SimpleNamespace

import pytest

import blueprints.approval as approval_module
import main


@pytest.fixture()
def client():
    main.app.config['TESTING'] = True
    with main.app.test_client() as test_client:
        with test_client.session_transaction() as session_data:
            session_data['logged_in'] = True
            session_data['username'] = 'tester'
            session_data['user_id'] = 2
            session_data['team_id'] = 1
            session_data['role_id'] = 3
            session_data['clock_id'] = '123'
            session_data['_csrf_token'] = 'token-approval-001'
        yield test_client


def test_reject_route_saves_reason_and_sends_notification(client, monkeypatch):
    tracked = {}

    monkeypatch.setattr(approval_module, 'has_permission', lambda *args, **kwargs: True)
    monkeypatch.setattr(approval_module.db, 'get_next_pending_approver', lambda doc_id: {'user_id': 2})

    def fake_update_doc_app(doc_id, user_id, status, reason=None):
        tracked['doc_id'] = doc_id
        tracked['user_id'] = user_id
        tracked['status'] = status
        tracked['reason'] = reason
        return True

    def fake_update_doc_status(doc_id, status):
        tracked['doc_status'] = status
        return True

    monkeypatch.setattr(approval_module.db, 'update_doc_app', fake_update_doc_app)
    monkeypatch.setattr(approval_module.db, 'update_doc_status', fake_update_doc_status)
    monkeypatch.setattr(approval_module.db, 'get_single_documents', lambda doc_id: SimpleNamespace(creator=1, title='Test doc'))

    def fake_send_email(doc_id, creator_user_id, title, approver_name, action, reason=None):
        tracked['email'] = (doc_id, creator_user_id, title, approver_name, action, reason)
        return True

    monkeypatch.setattr(approval_module.email, 'send_approval_status_email', fake_send_email)

    response = client.post('/p/reject', data={
        'doc_id': '42',
        'reason': '不符合規格',
        'csrf_token': 'token-approval-001',
    }, follow_redirects=True)

    assert response.status_code == 200
    assert tracked['status'] == 2
    assert tracked['reason'] == '不符合規格'
    assert tracked['doc_status'] == 3
    assert tracked['email'][4:] == ('reject', '不符合規格')


def test_w_menu_renders_front_desk_exchange_rate_ui(client, monkeypatch):
    class DummyCurrency:
        def __init__(self, country, buying_rate, selling_rate):
            self.country = country
            self.bank_buying_rate = buying_rate
            self.bank_selling_rate = selling_rate

    monkeypatch.setattr(main, 'update_currency', lambda date: ([
        DummyCurrency('USD', '33.6', '34.1'),
        DummyCurrency('SGD', '24.5', '24.9'),
        DummyCurrency('JPY', '0.245', '0.25'),
        DummyCurrency('EUR', '36.4', '37.0'),
        DummyCurrency('CNY', '4.75', '4.82'),
    ], None))

    response = client.get('/w_menu')

    assert response.status_code == 200
    assert b'Exchange Rates' in response.data
    assert '櫃台收匯價'.encode('utf-8') in response.data
