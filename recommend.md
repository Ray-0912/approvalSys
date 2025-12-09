# Project Recommendations

Here are several recommendations to improve the security, maintainability, and performance of your Approval System.

## 1. Security Improvements (Critical)

### Fix SQL Injection Vulnerabilities
**Current Issue:** In `database/queries.py`, several functions construct SQL queries using string concatenation.
- `get_in_search_doc`: Concatenates `p_type` and `content`.
  ```python
  query = query + " MATCH(title, content) AGAINST('" + content + "')"
  ```
  If a user enters `' OR 1=1 --`, it could compromise your database.
- `get_30days_doc`: Concatenates `creator`.

**Recommendation:** ALWAYS use parameterized queries.
```python
# Before
query = query + " AND type = " + p_type
cursor.execute(query)

# After
query += " AND type = %s"
params.append(p_type)
cursor.execute(query, tuple(params))
```

### Secure Sensitive Data
**Current Issue:** Secrets are hardcoded in `main.py`.
```python
app.secret_key = 'a3af8aea6ef1c50418b8a1b485ab6582'
```
**Recommendation:** Use Environment Variables.
1. Create a `.env` file (and add it to `.gitignore`).
2. Load it using `python-dotenv`.
```python
# main.py
import os
app.secret_key = os.getenv('SECRET_KEY', 'default-dev-key')
```

## 2. Codebase & Structure

### Ignore Virtual Environment
**Current Issue:** The folder `approval_system` (and `venv`) seems to be a Python virtual environment committed to the repo. This bloats the repo and causes cross-platform issues.
**Recommendation:**
1. Delete `approval_system` and `venv` from the repository (not your local disk, just git).
2. Add them to `.gitignore`.

### .gitignore Setup
Create a `.gitignore` file to prevent committing unwanted files:
```text
__pycache__/
*.pyc
venv/
approval_system/
.env
.idea/
```

## 3. Deployment & Docker

### Improve Docker Setup
**Current Issue:** No `.dockerignore` file. The build context includes everything, including local virtual environments.
**Recommendation:** Add a `.dockerignore` file.
```text
.git
.idea
venv
approval_system
__pycache__
```

### Task Scheduling
**Current Issue:** `schedule_task` runs in a separate thread within the Flask app process. In production with Gunicorn (multiple workers), this will run **multiple times** (once per worker).
**Recommendation:** Run the scheduler as a separate container/process, or use a dedicated task queue like Celery.

## 4. Code Quality

### Error Handling
Add try-except blocks in your routes, especially for database operations and external API calls (`requests.get`), to prevent the server from crashing or showing raw errors to users.

### Testing
Create a proper test suite. `Test.py` is currently a script. Use `pytest` to write unit tests for your database queries and API endpoints.

## 5. HR System Improvements

### Enable Manager/HR View
**Current Issue:** The `hr_clock_record` endpoint currently only allows a user to view their *own* records (`session.get('clock_id')`). HR managers cannot view other employees' attendance.
**Recommendation:**
1. Update `/hr/clockRecordPost` (or create a new endpoint) to accept a `target_user_id`.
2. check permissions (e.g., `has_permission('hr_view_all', ...)`).

### Attendance Calculation
**Current Issue:** The system shows raw clock logs. It does not calculate:
- Work duration (Hours worked).
- Late arrivals or early departures.
- Overtime.
**Recommendation:**
Implement logic to process raw logs:
- Identify the **First Check-in** and **Last Check-out** for each day.
- Calculate `End - Start` duration.
- Compare with scheduled shift times to flag "Late" or "Early Leave".

### Enhanced UI
**Current Issue:** The UI is basic and doesn't support selecting different employees.
**Recommendation:**
- Add an "Employee Selector" dropdown for HR users.
- Use a summary table (One row per day) instead of a log table (One row per punch).
