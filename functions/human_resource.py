from database.CI_API_Client import APIClient

# API client for bioLife

def hr_new_person_result(pin, name, og_id, ssn):
    client = APIClient()
    try:
        client.create_person(pin=pin, name=name, organization_unit_id=og_id, ssn=ssn)
        return 1
    except Exception as e:
        print("新增人員資訊時發生錯誤:", e)
        return 0

def check_organization_id(og, dep):
    if og == 'new_garden':
        match dep:
            case 'manage':
                return 7
            case 'front':
                return 8
            case 'housekeeping':
                return 9
            case 'marketing':
                return 16
            case 'finance':
                return 10
            case 'restaurant':
                return 18
    elif og == "new_dev":
        match dep:
            case 'manage':
                return 12
            case 'front':
                return 13
            case 'housekeeping':
                return 14
            case 'marketing':
                return 17
            case 'finance':
                return 15
            case 'restaurant':
                return 19

def check_team_id(team_id):
    # 庭園/開發
    if team_id == 7 or team_id == 12:
        return 0 # 管理
    elif team_id == 8 or team_id == 13:
        return 1 # 櫃台
    elif team_id == 9 or team_id == 14:
        return 2 # 房務
    elif team_id == 10 or team_id == 15:
        return 3 # 會計
    elif team_id == 16 or team_id == 17:
        return 4 # 業務
    elif team_id == 18 or team_id == 19:
        return 5 # 餐飲
    else:
        return 6

def get_og_string(og, dep):
    if og == 'new_garden':
        match dep:
            case 'manage':
                return "庭園 管理部"
            case 'front':
                return "庭園 櫃台部"
            case 'housekeeping':
                return "庭園 房務部"
            case 'marketing':
                return "庭園 業務部"
            case 'finance':
                return "庭園 會計部"
            case 'restaurant':
                return "庭園 餐飲部"
    elif og == "new_dev":
        match dep:
            case 'manage':
                return "開發 管理部"
            case 'front':
                return "開發 櫃台部"
            case 'housekeeping':
                return "開發 房務部"
            case 'marketing':
                return "開發 業務部"
            case 'finance':
                return "開發 會計部"
            case 'restaurant':
                return "開發 餐飲部"