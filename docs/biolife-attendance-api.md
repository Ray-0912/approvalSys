# BioLife 打卡系統 API 規格

版本：`v1`

本文整理 BioLife 打卡系統的已知 API，用於本專案的人員、部門、區域、打卡紀錄整合。

## 1. 基本資訊

- Base URL: `http://localhost:8083`
- 驗證方式: `Bearer Token`
- Token 取得方式: `TokenAuth/Authenticate`
- 多數需要授權的 API 都必須在 Header 加上 `Authorization: Bearer <accessToken>`

## 2. 共用約定

### 2.1 Header

登入以外的 API 通常使用：

```http
Authorization: Bearer xxxxxxxxxxxxx
Content-Type: application/json
```

登入介面依你提供的範例，使用：

```http
Content-Type: application/json-patch+json
```

### 2.2 回應格式

此系統回傳格式多為 ABP 風格：

```json
{
  "result": null,
  "targetUrl": null,
  "success": true,
  "error": null,
  "unAuthorizedRequest": false,
  "__abp": true
}
```

若成功，真正資料通常放在 `result` 中。

### 2.3 欄位說明

人員相關常用欄位：

| 欄位 | 說明 |
| --- | --- |
| `pin` | 員工編號 |
| `ssn` | 身分證或自定義編號 |
| `name` | 姓名 |
| `pri` | 權限，`0` 一般員工，`14` 超級管理員 |
| `passwd` | 密碼 |
| `card` | 卡片號碼 |
| `organizationUnitId` | 部門 ID |

## 3. 登入驗證

### 3.1 取得 Token

`POST /api/services/app/TokenAuth/Authenticate`

Request body：

```json
{
  "userNameOrEmailAddress": "admin",
  "password": "123qwe"
}
```

Response 範例：

```json
{
  "result": {
    "accessToken": "xxxxxxxxxxxxx",
    "encryptedAccessToken": "cccccccccc",
    "expireInSeconds": 86400,
    "shouldResetPassword": false,
    "passwordResetCode": null,
    "userId": 2,
    "requiresTwoFactorVerification": false,
    "twoFactorAuthProviders": null,
    "twoFactorRememberClientToken": null,
    "returnUrl": null,
    "refreshToken": "zzzzzzzzz",
    "refreshTokenExpireInSeconds": 31536000
  },
  "targetUrl": null,
  "success": true,
  "error": null,
  "unAuthorizedRequest": false,
  "__abp": true
}
```

### 3.2 後續呼叫方式

取得 `accessToken` 後，放入 Header：

```http
Authorization: Bearer <accessToken>
```

## 4. 人員相關 API

### 4.1 新增人員

`POST /api/services/app/Person/CreatePerson`

```json
{
  "pin": "8654",
  "ssn": null,
  "name": "8456",
  "pri": 0,
  "passwd": null,
  "card": null,
  "organizationUnitId": 1
}
```

### 4.2 讀取人員資料

`GET /api/services/app/Person/GetPersonForEdit?pin=123`

回傳會包含：

```json
{
  "result": {
    "id": 271,
    "pin": "123",
    "ssn": "",
    "name": "123",
    "pri": 0,
    "priName": "0",
    "passwd": "",
    "card": "0008179200",
    "accGroup": 1,
    "useAccGroupTZ": false,
    "timeZone1": 1,
    "timeZone2": 0,
    "timeZone3": 0,
    "organizationUnitId": 1,
    "organizationUnitName": "總公司",
    "gender": 0,
    "title": "",
    "hireDay": null,
    "phone1": "",
    "phone2": ""
  }
}
```

### 4.3 更新人員資料

`PUT /api/services/app/Person/UpdatePerson`

```json
{
  "id": 271,
  "pin": "123",
  "ssn": "",
  "name": "123",
  "pri": 0,
  "passwd": "",
  "card": "0008179200",
  "accGroup": 1,
  "useAccGroupTZ": false,
  "timeZone1": 1,
  "timeZone2": 0,
  "timeZone3": 0,
  "organizationUnitId": 1,
  "gender": 0,
  "title": "",
  "hireDay": null,
  "phone1": "",
  "phone2": ""
}
```

### 4.4 人員離職

`DELETE /api/services/app/Person/LeavePerson?pins=111`

`pins` 可為單一員工編號或多個編號（依實作而定）。

### 4.5 人員復職

`POST /api/services/app/Person/Reinstatement`

```json
{
  "OuId": "1",
  "ZoneIds": ["1", "2"],
  "Pins": ["20", "30"]
}
```

### 4.6 新增人臉照片

`POST /api/services/app/Person/CreateFaces`

```json
[
  {
    "url": "照片網址",
    "pin": "員工編號"
  },
  {
    "url": "照片網址",
    "pin": "員工編號"
  }
]
```

Response 範例：

```json
{
  "result": [
    {
      "status": true,
      "url": "照片網址",
      "pin": "員工編號",
      "message": null
    }
  ],
  "success": true
}
```

### 4.7 上傳人員到區域

`POST /api/services/app/Person/Upload`

```json
{
  "pins": ["1", "2", "3"]
}
```

## 5. 部門相關 API

### 5.1 取得部門清單

`GET /api/services/app/OrganizationUnit/GetOrganizationUnits`

回傳中的 `result.items` 為部門列表。

### 5.2 新增部門

`POST /api/services/app/OrganizationUnit/CreateOrganizationUnit`

```json
{
  "parentId": 1,
  "displayName": "Test123"
}
```

### 5.3 更新部門

`PUT /api/services/app/OrganizationUnit/UpdateOrganizationUnit`

```json
{
  "id": 2,
  "displayName": "Test456"
}
```

### 5.4 刪除部門

`DELETE /api/services/app/OrganizationUnit/DeleteOrganizationUnit?id=2`

## 6. 區域相關 API

### 6.1 取得區域清單

`GET /api/services/app/Zone/GetZonesList`

### 6.2 新增區域

`POST /api/services/app/Zone/CreateZone`

```json
{
  "name": "TestNew",
  "no": "",
  "isSync": true
}
```

### 6.3 讀取區域資料

`GET /api/services/app/Zone/GetZoneForEdit?Id=1`

### 6.4 更新區域

`PUT /api/services/app/Zone/UpdateZone`

```json
{
  "id": 10,
  "name": "1233",
  "no": "1234",
  "isSync": true
}
```

### 6.5 刪除區域

`DELETE /api/services/app/Zone/DeleteZone?Id=123`

### 6.6 區域加入人員

`POST /api/services/app/Zone/ZoneJoinPersons`

```json
{
  "zoneIds": [1],
  "pins": ["8654"]
}
```

### 6.7 區域移除人員

`POST /api/services/app/Zone/ZoneRemovePersons`

```json
{
  "zoneIds": [1],
  "pins": ["8654"]
}
```

## 7. 打卡紀錄查詢

### 7.1 取得打卡紀錄

`GET /api/services/app/AttLog/GetAttLogs`

常用參數：

| 參數 | 說明 |
| --- | --- |
| `page` | 頁數 |
| `MaxResultCount` | 每頁筆數 |
| `Start` | 起始時間 |
| `End` | 結束時間 |
| `Name` | 姓名 |
| `Pin` | 員工編號 |
| `Sort` | 排序，`0` 員工編號，`1` 時間 |
| `SN` | 設備序號，多台用逗號分開 |
| `OrganizationUnitId` | 部門 ID，多部門用逗號分開 |

Response 範例：

```json
{
  "result": {
    "totalCount": 1734,
    "items": [
      {
        "pin": "1",
        "personName": "1",
        "attLogTime": "2020-09-29T16:34:12",
        "status": 0,
        "statusName": "上班簽到",
        "verify": 1,
        "verifyName": "指紋",
        "deviceSn": "AF5Y191360023",
        "deviceName": "測試機",
        "personOrganizationUnitDisplayName": "總公司",
        "personOrganizationUnitId": 1,
        "id": 1708
      }
    ]
  },
  "success": true
}
```

### 7.2 補打卡

`POST /api/services/app/AttLog/SelfAdd`

此 API 用於補登打卡紀錄，請在 Header 先帶入 `Authorization: Bearer <accessToken>`。

Request body：

```json
{
  "pin": "123",
  "status": 0,
  "verify": 16,
  "sn": "1234567890123",
  "attLogTime": "2020-01-10T10:20:30",
  "temperature": 36.8,
  "mask": 1
}
```

欄位說明：

| 欄位 | 說明 |
| --- | --- |
| `pin` | 員工編號 |
| `status` | 打卡狀態 |
| `verify` | 驗證方式 |
| `sn` | 設備序號 |
| `attLogTime` | 打卡時間 |
| `temperature` | 體溫 |
| `mask` | 口罩狀態，`0` 未戴，`1` 有戴 |

`status` 對應：

| 值 | 說明 |
| --- | --- |
| `0` | 上班簽到 |
| `1` | 下班簽到 |
| `2` | 外出 |
| `3` | 外出返回 |
| `4` | 加班簽到 |
| `5` | 加班簽退 |

`verify` 對應：

| 值 | 說明 |
| --- | --- |
| `0` | 密碼 |
| `1` | 指紋 |
| `2` | 卡片 |
| `15` | 臉型 |
| `16` | 人臉 |

預期回應通常仍為 ABP 格式，成功時 `success=true`，失敗則由 `error` 回傳原因。

## 8. 照片查詢

### 8.1 取得打卡照片

`GET /api/services/app/AttPhoto/GetAttPhotos`

參數與打卡紀錄查詢相近，另有：

| 參數 | 說明 |
| --- | --- |
| `Type` | `0` 全部照片，`1` 成功照片，`2` 失敗照片 |

範例：

```http
GET /api/services/app/AttPhoto/GetAttPhotos?page=1&MaxResultCount=50&Start=2021-7-12%200%3A0%3A0&End=2021-7-15%2023%3A59%3A59&OrganizationUnitId=&Pin=&Name=&Sort=0&SN=&Type=0
```

Response 中的 `items` 會包含 `imageUrl`、`attPhotoTime`、`deviceSN` 等欄位。

## 9. 建議使用流程

1. 先呼叫登入 API 取得 `accessToken`。
2. 把 `Authorization: Bearer <accessToken>` 加到後續所有授權 API。
3. 先建立部門與區域，再建立人員。
4. 需要同步區域人員時，先新增人員，再呼叫區域加入或上傳到區域。
5. 需要查詢打卡紀錄或照片時，再使用 `AttLog` / `AttPhoto` API。

## 10. 注意事項

- 你提供的 API 回應多為 ABP 格式，實作時請以 `result` 為主要資料來源。
- `pri = 14` 被視為超級管理員，但實際權限仍應以後端規則為準。
- `GetOrganizationUnits`、`GetZonesList`、`GetAttLogs` 等查詢型 API 可能會依權限過濾資料。
- 若日後官方 API 有版本變更，建議以此文件為基礎做版本化維護。
