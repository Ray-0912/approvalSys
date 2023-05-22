# database/models.py

class Role:
    def __init__(self, role_id, name):
        self.role_id = role_id
        self.name = name

class Team:
    def __init__(self, team_id, name):
        self.team_id = team_id
        self.name = name

class Document:
    def __init__(self, doc_id, creator, name, doc_type, signature_required, content, status, status_remark, create_time, last_update):
        self.doc_id = doc_id
        self.creator = creator
        self.name = name
        self.doc_type = doc_type
        self.signature_required = signature_required
        self.content = content
        self.status = status
        self.status_remark = status_remark
        self.create_time = create_time
        self.last_update = last_update
