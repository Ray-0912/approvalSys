# database/models.py
import json
import os

file_path = os.path.join(os.getcwd(), 'static', 'js', 'p_type_data.json')


class User:
    def __init__(self, user_id: int, username: str, first_name: str, last_name: str, email: str,
                 role_id: int, team_id: int, role_name: str, team_name: str, clock_id: str,
                 activation: int = 1) -> None:
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.role_id = role_id
        self.team_id = team_id
        self.role_name = role_name
        self.team_name = team_name
        self.clock_id = clock_id
        self.activation = activation


class Role:
    def __init__(self, role_id: int, name: str) -> None:
        self.role_id = role_id
        self.name = name


class Team:
    def __init__(self, team_id: int, name: str) -> None:
        self.team_id = team_id
        self.name = name


class Document:
    def __init__(self, doc_id: int, creator: int, title: str, doc_type: str, signature_required: int,
                 content: str, status: int, status_remark: str, create_time, last_update,
                 creator_name: str = '') -> None:
        self.doc_id = doc_id
        self.creator = creator
        self.title = title
        self.creator_name = creator_name
        self.doc_type = doc_type
        self.doc_type_cht = get_type_cht(doc_type)
        self.signature_required = signature_required
        self.content = content
        self.status = status
        self.status_remark = status_remark
        self.create_time = create_time
        self.last_update = last_update


class AppRecord:
    def __init__(self, doc_ap_id: int, status: int, approval_time, username: str, create_time, reason: str = None) -> None:
        self.doc_ap_id = doc_ap_id
        self.status = status
        self.approval_time = approval_time
        self.username = username
        self.create_time = create_time
        self.reason = reason


class Currency:
    def __init__(self, date, country: str, bank_buying_rate, bank_selling_rate) -> None:
        self.date = date
        self.country = country
        self.bank_buying_rate = bank_buying_rate
        self.bank_selling_rate = bank_selling_rate


def get_type_cht(type_code: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
        if type_code in data['type']:
            return data['type'][type_code]
        else:
            return 'Not Found'
