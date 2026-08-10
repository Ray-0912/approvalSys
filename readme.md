# Approval System

Approval System 是一套基於 Flask 的內部流程平台，主要涵蓋：

1. 文件簽核（建立、審核、核准、駁回）
2. 人資出勤與排班管理
3. 基礎系統管理（使用者／角色／部門維護）

本 README 內容是根據此儲存庫的實際原始碼分析整理而成。

## 1. 技術堆疊

- 後端：Flask 2.3
- 資料庫：MySQL（mysql-connector-python）
- 驗證與 Session：Flask Session + bcrypt 密碼雜湊
- 多語系：Flask-Babel
- 外部 API：BioLife 出勤 API Client
- 排程：schedule（在應用程式行程內執行執行緒）
- 健康檢查：/healthz

## 2. 核心模組

- `main.py`
  - Flask 應用程式進入點
  - 所有路由與請求流程
  - 匯率更新邏輯
  - 應用程式內排程啟動

- `database/`
  - `__init__.py`：MySQL 連線工廠
  - `queries.py`：使用者、文件、排班、備註等 SQL 操作
  - `models.py`：User/Role/Team/Document/Currency 模型物件
  - `CI_API_Client.py`：BioLife API 封裝（出勤／人員／組織操作）
  - `setup_schedule.py`：排班與班別資料表初始化腳本

- `functions/`
  - `permission.py`：頁面層級權限檢查
  - `email.py`：SMTP 郵件寄送與 HTML 模板整合
  - `human_resource.py`：組織／部門對應與人資輔助函式

- `docs/`
  - `biolife-attendance-api.md`：BioLife 打卡系統 API 規格

- `templates/`, `static/`
  - Jinja 模板與前端資源

- `tests/`
  - Flask 路由 smoke test

## 3. 已實作功能範圍

### 3.1 驗證與使用者

- 登入／登出／註冊
- 個人資料更新
- 密碼重設（含權限保護）

### 3.2 簽核流程（`/p/*`）

- 文件列表（`/p/list`）
- 建立新文件（`/p/new`）
- 編輯待處理文件（`/p/edit/<doc_id>`）
- 搜尋文件（`/p/search`）
- 檢視文件與簽核紀錄（`/p/view/<doc_id>`）
- 核准／駁回／刪除操作

### 3.3 人資與出勤（`/hr/*`）

- 出勤紀錄檢視與主管角色員工篩選
- 出勤摘要計算（起訖時間、工時、遲到判定）
- 班別 CRUD 與排班儲存／查詢
- 部門月備註（查詢／儲存／複製上月）

### 3.4 系統管理（`/sys/*`）

- 設定頁面
- 使用者列表／編輯／儲存（管理員角色）

## 4. 執行行為

- 應用程式綁定：`0.0.0.0:80`
- 除錯模式：當 `APP_ENV` 非 `production` 時啟用
- Session 生命週期：永久 session，一小時有效（在 `after_request` 設定）
- 每日任務：以 daemon thread 在 `23:30` 執行匯率抓取

## 5. 本機開發

## 5.1 需求

- Python 3.10+
- MySQL 資料庫

## 5.2 安裝步驟

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

建立並編輯 `.env`（範例）：

```env
SECRET_KEY=replace-with-your-secret
APP_ENV=development

API_BASE_URL=http://your-bioloife-host:8083
API_USERNAME=your-api-user
API_PASSWORD=your-api-password
```

注意：資料庫與 SMTP 憑證已改為環境變數設定，請先完成 `.env`（可參考 `.env.example`）。

啟動：

```bash
python main.py
```

## 5.3 可選資料庫初始化腳本

```bash
python database/setup_schedule.py
python migrate_db.py
```

## 6. Docker

目前 Docker 行為：

- 基底映像：`python:3.10-slim`
- 安裝 requirements
- 以 `python main.py` 啟動

指令：

```bash
docker build -t approvalsys .
docker run -d -p 80:80 --name approvalsys-app approvalsys
```

## 7. 測試

執行：

```bash
pytest
```

備註：

- 目前測試含路由渲染與核心流程驗證。
- 部分測試可能依賴資料庫狀態或外部服務。

## 8. 專案結構

```text
.
|- main.py
|- config.py
|- database/
|- functions/
|- templates/
|- static/
|- tests/
|- output/
|- translations/
|- requirements.txt
```

## 9. 目前風險與已知缺口

以下為從原始碼觀察到、建議優先處理的項目：

1. 機敏資訊管理風險
  - 若 `.env` 管理不當或外流，仍可能造成憑證風險
  - 建議搭配祕密管理服務與憑證輪替機制

2. 安全控管缺口
   - 多個會改變狀態的路由僅依賴 session，未一致套用 `has_permission`
   - 表單與 JSON POST 路由未見明確 CSRF 防護

3. 維運風險
   - 排程跑在 Web 行程中，多 worker 部署可能造成重複執行

4. 程式品質／正確性問題
   - `database/queries.py` 的 `get_approve_record_all` 有物件建構 typo
   - 部分端點為 stub 或僅部分完成（`/hr/salary/*`、`/hr/new`）

5. 架構可維護性
   - `main.py` 過於集中（路由、服務邏輯、整合邏輯混在同檔）

## 10. 建議下一份文件

請參考 `todolist.md`，內容包含優先級改善項目、執行順序與中長期方向。

另外，BioLife 打卡系統 API 的整理文件請參考 [docs/biolife-attendance-api.md](docs/biolife-attendance-api.md)。