# Approval System

A Flask-based web application for managing document approvals, human resources, and personnel scheduling.

## Features
- **User Authentication**: Login, Register, Role-based access control (RBAC).
- **Document Approval Workflow**: Create, edit, approve, and reject documents (`/p/...` routes).
- **Human Resources Integration**: Manage employees, departments, and scheduling (`/hr/...` routes).
- **Notifications**: Email notifications for approvals (via `functions.email`).
- **Dashboard**: Front desk wheel menu with currency rates updated daily.
- **Multilingual Support**: Internationalization via `Flask-Babel`.

## Prerequisites
- Python 3.10+
- MySQL Database

## Setup Instructions

### 1. Local Development
1. **Clone the repository** (if applicable).
2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Environment Configuration**:
   - Ensure your MySQL database is running.
   - Configure database connection settings in `database/__init__.py` or `config.py` (Note: Currently looking for settings in `database` package).
5. **Run the application**:
   ```bash
   python main.py
   ```
   The app will start on `http://localhost:80` (requires Admin privileges for port 80, or change port in `main.py`).

### 2. Docker Deployment
The project includes a `Dockerfile` for easy deployment.

1. **Build the image**:
   ```bash
   docker build -t approval-system .
   ```
2. **Run the container**:
   ```bash
   docker run -d -p 80:80 --name approval-app approval-system
   ```

## Project Structure
- `main.py`: Application entry point and route definitions.
- `database/`: Database models, API clients, and query logic.
- `functions/`: Helper functions for permissions, email, and HR logic.
- `templates/`: HTML templates (Jinja2).
- `static/`: Static assets (CSS, JS, images).
- `translations/`: Locale files for Flask-Babel.

## Scheduled Tasks
The application runs a daily task at 23:30 to update currency rates.
*Note: In production with multiple workers, this may execute multiple times. Consider moving to a separate worker.*