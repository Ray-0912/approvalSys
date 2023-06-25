# database/models.py
import json
import os

file_path = os.path.join(os.getcwd(), 'static', 'js', 'p_type_data.json')


class User:
    def __init__(self, user_id, username, first_name, last_name, role_id, team_id, role_name, team_name):
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.role_id = role_id
        self.team_id = team_id
        self.role_id = role_id
        self.role_name = role_name
        self.team_name = team_name


class Role:
    def __init__(self, role_id, name):
        self.role_id = role_id
        self.name = name


class Team:
    def __init__(self, team_id, name):
        self.team_id = team_id
        self.name = name


class Document:
    def __init__(self, doc_id, creator, title, doc_type, signature_required, content, status, status_remark,
                 create_time, last_update, creator_name=''):
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


def get_type_cht(type_code):
    with open(file_path) as file:
        data = json.load(file)
        if type_code in data['type']:
            return data['type'][type_code]
        else:
            return 'Not Found'
