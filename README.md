# Streamlit Leave Management System (Standalone)

A full-fledged **Streamlit + SQLite3** MVP for a 50-employee startup.

## Features
- Add employees (name, email, department, joining date, initial balance)
- Apply for leave (with validation and overlap checks)
- Approve / Reject leave (balance deducted on approval)
- View balance and employee leave history
- Admin utilities: DB init/migration, quick stats, DB download

## Edge Cases Handled
- Applying before joining date
- End date before start date (invalid range)
- Overlapping requests (pending/approved)
- Insufficient leave balance on application
- Employee not found
- Balance re-validated at approval time
- Non-positive duration protection

## How to Run
```bash
pip install streamlit pandas
streamlit run app.py
```
The app creates/uses `leave_mgmt.sqlite3` in the working directory. To change DB path, create `.streamlit/secrets.toml`:
```toml
DB_PATH = "path/to/leave_mgmt.sqlite3"
```

## High-Level System Design
```
[ Streamlit Frontend + Business Logic ]
          |
          v
[ SQLite3 Database (employees, leave_requests) ]
```

- **APIs & DB Interaction**: Streamlit app directly runs SQL queries against SQLite (no separate API layer). The UI writes/reads via parameterized SQL and enforces business rules in Python before DB writes.
- **Schema**
  - `employees(id, name, email UNIQUE, department, joining_date, leave_balance)`
  - `leave_requests(id, employee_id FK, start_date, end_date, reason, status, created_at)`
- **Core Business Rules**
  - Overlap detection against `PENDING` + `APPROVED`
  - Leave balance deducted on **approval**
  - Inclusive day counting

## Scaling: 50 → 500 Employees
- **Database**: move from SQLite to **PostgreSQL**; add indices on `status`, `employee_id`, and `(employee_id, start_date, end_date)`.
- **Service Layer**: introduce a **FastAPI** backend for clean separation, validation, and authentication (JWT, roles).
- **Concurrency**: use connection pooling (e.g., `asyncpg`), and deploy behind a reverse proxy.
- **Caching**: cache frequent reads (employee profile, balances).
- **Observability**: add audit logs, metrics, and tracing.
- **Security**: role-based access control (HR vs Employee), SSO (Okta/Azure AD).
- **Availability**: nightly backups, migration strategy, and read replicas if needed.

## Notes
- Inclusive day counting used for leave duration.
- Weekends/holidays not excluded (can be added by hooking a calendar table).
- Deleting an employee cascades to their leave requests (FK with `ON DELETE CASCADE`).
