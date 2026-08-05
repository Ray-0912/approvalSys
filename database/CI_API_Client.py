# API for BioLife

# pin 員工編號
# ssn 身分證(自定義編號)
# name 姓名
# pri 權限 0一般員工 14超級管理員
# passwd 密碼
# card 卡片
# organizationUnitId 部門ID

import os
import requests
import time
import logging
from datetime import datetime

logger = logging.getLogger('approval_system.bioloife')

class APIClient:
    def __init__(self):
        self.base_url = os.getenv("API_BASE_URL", "http://192.168.1.100:8083")
        self.username = os.getenv("API_USERNAME", "admin")
        self.password = os.getenv("API_PASSWORD", "123qwe")
        self.token = None
        self.max_retries = 3
        # self.authenticate()  # Lazy authentication: called on first request

    def authenticate(self):
        url = f"{self.base_url}/api/services/app/TokenAuth/Authenticate"
        data = {"userNameOrEmailAddress": self.username, "password": self.password}
        headers = {"Content-Type": "application/json"}

        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, json=data, headers=headers, timeout=5)
                response.raise_for_status()
                if response.status_code == 200:
                    self.token = response.json().get("result", {}).get("accessToken")
                    if not self.token:
                        raise ValueError("Failed to retrieve token")
                    return
            except requests.RequestException as e:
                time.sleep(2 ** attempt)
        raise Exception(f"Authentication failed after {self.max_retries} attempts")

    def _get_headers(self):
        if not self.token:
            self.authenticate()
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    # Person Management
    def create_person(self, pin, name, organization_unit_id, pri=0, ssn=None, passwd=None, card=None):
        if not pin or not isinstance(pin, str) or not pin.isdigit():
            raise ValueError("Invalid PIN format: PIN must be a numeric string")
        if not organization_unit_id or not isinstance(organization_unit_id, int):
            raise ValueError("Invalid organization unit ID")

        person_data = {
            "pin": pin,
            "ssn": ssn,
            "name": name,
            "pri": pri,
            "passwd": passwd,
            "card": card,
            "organizationUnitId": organization_unit_id
        }

        return self._post("/api/services/app/Person/CreatePerson", person_data)

    # 取得員工資料，pin = 員工編號，EX: pin=10001
    def get_person_for_edit(self, pin):
        return self._get(f"/api/services/app/Person/GetPersonForEdit?pin={pin}")

    def get_all_biolife_persons(self):
        """Fetch all persons across all known org units; returns list of {pin, name, org_unit_id} dicts."""
        ALL_ORG_IDS = "7,8,9,10,12,13,14,15,16,17,18,19"
        result = self._get("/api/services/app/Person/GetPersons",
                           {"organizationUnitId": ALL_ORG_IDS, "MaxResultCount": 1000, "page": 1})
        items = ((result or {}).get('result') or {}).get('items') or []
        return [
            {
                'pin': str(p.get('pin', '')),
                'name': p.get('name', ''),
                'org_unit_id': p.get('organizationUnitId') or p.get('organizationunitid') or p.get('orgUnitId'),
            }
            for p in items if p.get('pin')
        ]

    # 取得員工資料(Multiple),EX: organization unit id : 8,13(櫃台)
    def get_persons(self, organization_unit_id, Name=None, page = 1):
        search_data = {
            "organizationUnitId" : organization_unit_id,
            "Name" : Name,
            "page" : page
        }
        return self._get(f"/api/services/app/Person/GetPersons", search_data)

    # 取得某OG下員工的最新未用的PIN
    def get_latest_person_pin(self, organization_unit_id):
        parent_og_id = '0'
        organization_unit_ids = 0
        if organization_unit_id==7 or organization_unit_id==12:
            parent_og_id = '1'
            organization_unit_ids = "7,12"
        elif organization_unit_id==8 or organization_unit_id==13:
            parent_og_id = '2'
            organization_unit_ids = "8,13"
        elif organization_unit_id==9 or organization_unit_id==14:
            parent_og_id = '3'
            organization_unit_ids = "9,14"
        elif organization_unit_id==10 or organization_unit_id==15:
            parent_og_id = '4'
            organization_unit_ids = "10,15"
        elif organization_unit_id==16 or organization_unit_id==17:
            parent_og_id = '5'
            organization_unit_ids = "16,17"
        elif organization_unit_id==18 or organization_unit_id==19:
            parent_og_id = '6'
            organization_unit_ids = "18,19"

        get_og_persons = self.get_persons(organization_unit_id=organization_unit_ids)
        if not get_og_persons['result']['items']:
            return parent_og_id+'0001'
        else:
            count = get_og_persons['result']['totalCount']-1
            last_pin = get_og_persons['result']['items'][count]['pin']

            return int(last_pin)+1

    # 如果沒有打卡紀錄時，可以直接調用這個function給網頁使用
    def get_employee_info(self, pin):
        employee_info = self._get(f"/api/services/app/Person/GetPersonForEdit?pin={pin}")

        if not employee_info or 'result' not in employee_info:
            return None

        employee_data = employee_info['result']
        return {
            "pin": employee_data.get('pin'),
            "name": employee_data.get('name')
        }

    # 更新員工資料，person_data = 員工資料，EX:
    def update_person(self, name, pin, email=None):
        if not pin or not isinstance(pin, str):
            raise ValueError("Invalid PIN: Must be a string")
        if not name or not isinstance(name, str):
            raise ValueError("Invalid name: Must be a string")
        if email is not None and not isinstance(email, str):
            raise ValueError("Invalid email: Must be a string")

        person_data = {
            "name": name,
            "pin": pin,
            "email": email
        }

        return self._put("/api/services/app/Person/UpdatePerson", person_data)

    # 員工離職
    def leave_person(self, pins):
        return self._delete(f"/api/services/app/Person/LeavePerson?pins={pins}")

    # 員工復職
    def reinstate_person(self, pin, effective_date, reason):
        if not pin or not isinstance(pin, str):
            raise ValueError("Invalid PIN: Must be a string")
        if not effective_date or not isinstance(effective_date, str):
            raise ValueError("Invalid effective date: Must be a string in 'YYYY-MM-DD' format")
        if not reason or not isinstance(reason, str):
            raise ValueError("Invalid reason: Must be a string")

        reinstatement_data = {
            "pin": pin,
            "effectiveDate": effective_date,
            "reason": reason
        }

        return self._post("/api/services/app/Person/Reinstatement", reinstatement_data)

    def create_faces(self, faces_data):
        return self._post("/api/services/app/Person/CreateFaces", faces_data)

    # 更新員工區域(ZONE)，pins_data = 更新資料，EX:
    def upload_persons_to_zone(self, pins, zone_id):
        if not pins or not isinstance(pins, list) or not all(isinstance(pin, str) for pin in pins):
            raise ValueError("Invalid pins: Must be a list of string PINs")
        if not zone_id or not isinstance(zone_id, (str, int)):
            raise ValueError("Invalid zone ID")

        pins_data = {
            "pins": pins,
            "zoneId": str(zone_id)
        }

        return self._post("/api/services/app/Person/Upload", pins_data)

    # Zone Management
    # 取得所有Zone資訊
    def get_zones_list(self):
        return self._get("/api/services/app/Zone/GetZonesList")

    # 創建新的Zone，
    def create_zone(self, name, description=None, parent_id=None):
        if not name or not isinstance(name, str):
            raise ValueError("Invalid zone name")

        zone_data = {
            "name": name,
            "description": description,
            "parentId": parent_id
        }

        return self._post("/api/services/app/Zone/CreateZone", zone_data)

    # 取得特定Zone資訊，EX: zone_id = 1
    def get_zone_for_edit(self, zone_id):
        return self._get(f"/api/services/app/Zone/GetZoneForEdit?Id={zone_id}")

    # 更新Zone資訊
    def update_zone(self, zone_id, name, description=None):
        if not zone_id or not isinstance(zone_id, int):
            raise ValueError("Invalid zone ID")
        if not name or not isinstance(name, str):
            raise ValueError("Invalid zone name")

        zone_data = {
            "id": zone_id,
            "name": name,
            "description": description
        }

        return self._put("/api/services/app/Zone/UpdateZone", zone_data)

    # 刪除特定Zone，EX: zone_id = 1
    def delete_zone(self, zone_id):
        return self._delete(f"/api/services/app/Zone/DeleteZone?Id={zone_id}")

    # 新增人員至特定Zone
    def zone_join_persons(self, zone_id, pins):
        if not zone_id or not isinstance(zone_id, int):
            raise ValueError("Invalid zone ID")
        if not pins or not isinstance(pins, list) or not all(isinstance(pin, str) and pin.isdigit() for pin in pins):
            raise ValueError("Invalid pins list")

        zone_data = {
            "zoneId": zone_id,
            "pins": pins
        }

        return self._post("/api/services/app/Zone/ZoneJoinPersons", zone_data)

    # 刪除人員從特定Zone
    def zone_remove_persons(self, zone_id, pins):
        if not zone_id or not isinstance(zone_id, int):
            raise ValueError("Invalid zone ID")
        if not pins or not isinstance(pins, list) or not all(isinstance(pin, str) and pin.isdigit() for pin in pins):
            raise ValueError("Invalid pins list")

        zone_data = {
            "zoneId": zone_id,
            "pins": pins
        }

        return self._post("/api/services/app/Zone/ZoneRemovePersons", zone_data)

    # Organization Unit Management(OG)
    # 取得所有OG資訊
    def get_organization_units(self):
        return self._get("/api/services/app/OrganizationUnit/GetOrganizationUnits")

    # 新增OG
    def create_organization_unit(self, display_name, parent_id=None):
        if not display_name or not isinstance(display_name, str):
            raise ValueError("Invalid display name for organization unit")

        unit_data = {
            "displayName": display_name,
            "parentId": parent_id
        }

        return self._post("/api/services/app/OrganizationUnit/CreateOrganizationUnit", unit_data)

    # 更新OG
    def update_organization_unit(self, unit_id, display_name, parent_id=None):
        if not unit_id or not isinstance(unit_id, int):
            raise ValueError("Invalid organization unit ID")
        if not display_name or not isinstance(display_name, str):
            raise ValueError("Invalid display name for organization unit")

        unit_data = {
            "id": unit_id,
            "displayName": display_name,
            "parentId": parent_id
        }

        return self._put("/api/services/app/OrganizationUnit/UpdateOrganizationUnit", unit_data)

    # 刪除OG，EX: unit_id = 104
    def delete_organization_unit(self, unit_id):
        return self._delete(f"/api/services/app/OrganizationUnit/DeleteOrganizationUnit?id={unit_id}")

    # Attendance Management
    # 查詢打卡紀錄
    def get_att_logs(self, pin, start_date=None, end_date=None, page=1, max_result_count=500):
        if not pin or not isinstance(pin, str) or not pin.isdigit():
            raise ValueError("Invalid PIN format: PIN must be a numeric string")

        if not start_date:
            start_date = datetime.today().replace(day=1)
        if not end_date:
            end_date = datetime.today()

        query_params = {
            "page": page,
            "MaxResultCount": max_result_count,
            "Start": start_date.strftime("%Y-%m-%d 00:00:00"),
            "End": end_date.strftime("%Y-%m-%d 23:59:59"),
            "v": int(datetime.now().timestamp() * 1000),
            "Pin": pin,
        }
        return self._get("/api/services/app/AttLog/GetAttLogs", query_params)

    # 查詢打卡紀錄的照片
    def get_att_photos(self, query_params):
        return self._get("/api/services/app/AttPhoto/GetAttPhotos", query_params)

    # 補打卡
    def self_add_att_log(self, pin, status, att_log_time, verify=0, sn='Ne11111111111', temperature=36, mask=0):
        #"status": 0,  # 上班簽到 (0:上班, 1:下班, 2:外出, 3:外出返回, 4:加班簽到, 5:加班簽退)
        #"verify": 0,  # 驗證方式 (0:密碼, 1:指紋, 2:卡片, 15:臉型, 16:人臉)
        #sample:"attLogTime": "2025-02-03T10:20:30"
        if not pin or not isinstance(pin, str):
            raise ValueError("Invalid PIN: Must be a string")
        if not isinstance(status, int) or status not in range(6):
            raise ValueError("Invalid status: Must be an integer between 0 and 5")
        if not isinstance(verify, int):
            raise ValueError("Invalid verify: Must be an integer")
        if not sn or not isinstance(sn, str):
            raise ValueError("Invalid SN: Must be a string")
        if not att_log_time or not isinstance(att_log_time, str):
            raise ValueError("Invalid att_log_time: Must be a string")
        if temperature is not None and not isinstance(temperature, (int, float)):
            raise ValueError("Invalid temperature: Must be a number")
        if mask is not None and mask not in (0, 1):
            raise ValueError("Invalid mask: Must be 0 or 1")

        att_log_data = {
            "pin": pin,
            "status": status,
            "verify": verify,
            "sn": sn,
            "attLogTime": att_log_time,
            "temperature": temperature,
            "mask": mask
        }

        return self._post("/api/services/app/AttLog/SelfAdd", att_log_data)

    # Generic HTTP Methods
    def _get(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, headers=self._get_headers(), params=params, timeout=5)
        return self._handle_response(response)

    def _post(self, endpoint, data):
        url = f"{self.base_url}{endpoint}"
        response = requests.post(url, json=data, headers=self._get_headers(), timeout=5)
        return self._handle_response(response)

    def _put(self, endpoint, data):
        url = f"{self.base_url}{endpoint}"
        response = requests.put(url, json=data, headers=self._get_headers(), timeout=5)
        return self._handle_response(response)

    def _delete(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        response = requests.delete(url, headers=self._get_headers(), timeout=5)
        return self._handle_response(response)

    def _handle_response(self, response):
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            logger.warning('BioLife API unauthorized, refreshing token')
            self.authenticate()
        elif response.status_code == 403:
            logger.warning('BioLife API forbidden: status=403')
            raise PermissionError("Forbidden: You don't have permission to access this resource.")
        elif response.status_code == 500:
            logger.error('BioLife API internal server error: status=500')
            raise RuntimeError("Internal Server Error")
        else:
            logger.error('BioLife API unexpected status: %s', response.status_code)
            response.raise_for_status()