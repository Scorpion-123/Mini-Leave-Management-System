import streamlit as st
import sqlite3
from datetime import date
import pandas as pd
from contextlib import closing

DB_PATH = st.secrets.get("DB_PATH", "leave_mgmt.sqlite3")

st.set_page_config(page_title="Leave Management System", page_icon="🗓️", layout="wide")

# ---------------------- DB helpers ----------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with closing(get_conn()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                department TEXT NOT NULL,
                joining_date DATE NOT NULL,
                leave_balance INTEGER NOT NULL DEFAULT 24,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS leave_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_leave_emp ON leave_requests(employee_id);
            CREATE INDEX IF NOT EXISTS idx_leave_status ON leave_requests(status);
            """
        )

def days_inclusive(start: date, end: date) -> int:
    return (end - start).days + 1

def list_employees(q: str | None = None) -> pd.DataFrame:
    with closing(get_conn()) as conn:
        if q:
            df = pd.read_sql_query(
                "SELECT * FROM employees WHERE LOWER(name) LIKE ? OR LOWER(email) LIKE ? ORDER BY id DESC",
                conn, params=[f"%{q.lower()}%", f"%{q.lower()}%"]
            )
        else:
            df = pd.read_sql_query("SELECT * FROM employees ORDER BY id DESC", conn)
    return df

def get_employee(emp_id: int):
    with closing(get_conn()) as conn:
        cur = conn.execute("SELECT * FROM employees WHERE id = ?", (emp_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

def add_employee(name, email, department, joining_date, leave_balance=24):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "INSERT INTO employees (name, email, department, joining_date, leave_balance) VALUES (?, ?, ?, ?, ?)",
            (name, email, department, joining_date.isoformat(), int(leave_balance))
        )

def has_overlap(conn, employee_id: int, start_date: date, end_date: date) -> bool:
    cur = conn.execute(
        """
        SELECT 1 FROM leave_requests
        WHERE employee_id = ?
          AND status IN ('PENDING','APPROVED')
          AND start_date <= ?
          AND end_date >= ?
        LIMIT 1
        """,
        (employee_id, end_date.isoformat(), start_date.isoformat())
    )
    return cur.fetchone() is not None

def apply_leave(employee_id: int, start_date: date, end_date: date, reason: str | None):
    with closing(get_conn()) as conn, conn:
        emp_cur = conn.execute("SELECT joining_date, leave_balance FROM employees WHERE id = ?", (employee_id,))
        emp = emp_cur.fetchone()
        if not emp:
            raise ValueError("Employee not found")
        joining_date = date.fromisoformat(emp[0])
        balance = int(emp[1])

        if end_date < start_date:
            raise ValueError("End date cannot be before start date")
        if start_date < joining_date:
            raise ValueError("Cannot apply for leave before joining date")

        if has_overlap(conn, employee_id, start_date, end_date):
            raise ValueError("Overlapping leave request exists (pending or approved)")

        req_days = days_inclusive(start_date, end_date)
        if req_days <= 0:
            raise ValueError("Invalid duration")
        if req_days > balance:
            raise ValueError("Insufficient leave balance")

        conn.execute(
            "INSERT INTO leave_requests (employee_id, start_date, end_date, reason, status) VALUES (?, ?, ?, ?, 'PENDING')",
            (employee_id, start_date.isoformat(), end_date.isoformat(), reason)
        )

def list_leaves(employee_id: int | None = None, status: str | None = None) -> pd.DataFrame:
    with closing(get_conn()) as conn:
        q = "SELECT * FROM leave_requests"
        params = []
        clauses = []
        if employee_id is not None:
            clauses.append("employee_id = ?")
            params.append(employee_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC"
        return pd.read_sql_query(q, conn, params=params)

def update_leave_status(leave_id: int, new_status: str):
    with closing(get_conn()) as conn, conn:
        cur = conn.execute("SELECT employee_id, start_date, end_date, status FROM leave_requests WHERE id = ?", (leave_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Leave request not found")
        employee_id = row[0]
        start_date = date.fromisoformat(row[1])
        end_date = date.fromisoformat(row[2])
        curr_status = row[3]
        if curr_status != "PENDING":
            raise ValueError("Only pending requests can be updated")

        if new_status == "APPROVED":
            cur2 = conn.execute("SELECT leave_balance FROM employees WHERE id = ?", (employee_id,))
            bal = int(cur2.fetchone()[0])
            needed = days_inclusive(start_date, end_date)
            if needed > bal:
                raise ValueError("Insufficient balance at approval time")
            conn.execute("UPDATE employees SET leave_balance = leave_balance - ? WHERE id = ?", (needed, employee_id))

        conn.execute("UPDATE leave_requests SET status = ? WHERE id = ?", (new_status, leave_id))

def get_balance(emp_id: int) -> int:
    with closing(get_conn()) as conn:
        cur = conn.execute("SELECT leave_balance FROM employees WHERE id = ?", (emp_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Employee not found")
        return int(row[0])

# ---------------------- UI ----------------------
init_db()
st.title("🗓️ Mini Leave Management System")

colA, colB, colC = st.columns(3)
with colA:
    try:
        df_emp = list_employees()
        st.metric("Employees", len(df_emp))
    except Exception:
        st.metric("Employees", 0)
with colB:
    try:
        df_pending = list_leaves(status="PENDING")
        st.metric("Pending Requests", len(df_pending))
    except Exception:
        st.metric("Pending Requests", 0)
with colC:
    try:
        df_approved = list_leaves(status="APPROVED")
        st.metric("Approved (All-time)", len(df_approved))
    except Exception:
        st.metric("Approved (All-time)", 0)

st.divider()

tab_add, tab_apply, tab_review, tab_balance, tab_admin = st.tabs(
    ["➕ Add Employee", "📝 Apply Leave", "✅ Approve / ❌ Reject", "📊 Balance & History", "⚙️ Admin / Data"]
)

with tab_add:
    st.subheader("Add a New Employee")
    with st.form("add_emp_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Full Name", placeholder="Jane Doe", max_chars=80)
            dept = st.selectbox("Department", ["Engineering", "Product", "HR", "Sales", "Marketing", "Finance", "Operations"])
            joining = st.date_input("Joining Date", value=date.today())
        with c2:
            email = st.text_input("Email", placeholder="jane.doe@company.com", max_chars=120)
            balance = st.number_input("Initial Leave Balance", min_value=0, max_value=365, value=24, step=1)
        submitted = st.form_submit_button("Create Employee")
        if submitted:
            try:
                if not name or not email or not dept:
                    st.error("Please fill all required fields.")
                else:
                    add_employee(name, email, dept, joining, int(balance))
                    st.success(f"Employee '{name}' created successfully.")
            except sqlite3.IntegrityError:
                st.error("Email already exists. Please use a unique email.")
            except Exception as e:
                st.error(str(e))

    st.write("")
    st.markdown("#### All Employees")
    q = st.text_input("Search by name or email", key="emp_search")
    st.dataframe(list_employees(q), use_container_width=True)

with tab_apply:
    st.subheader("Apply for Leave")
    with st.form("apply_leave_form", clear_on_submit=True):
        emp_id = st.number_input("Employee ID", min_value=1, step=1)
        c1, c2 = st.columns(2)
        with c1:
            start = st.date_input("Start Date", value=date.today())
        with c2:
            end = st.date_input("End Date", value=date.today())
        reason = st.text_area("Reason (optional)", placeholder="Family function / Medical / Vacation / ...", height=100)
        submitted2 = st.form_submit_button("Submit Leave Application")
        if submitted2:
            try:
                apply_leave(int(emp_id), start, end, reason.strip() or None)
                st.success("Leave application submitted successfully.")
            except Exception as e:
                st.error(str(e))

with tab_review:
    st.subheader("Pending Leave Requests")
    df = list_leaves(status="PENDING")
    if df.empty:
        st.info("No pending requests.")
    else:
        for _, r in df.iterrows():
            with st.expander(f"Request #{r['id']}  •  Emp {r['employee_id']}  •  {r['start_date']} → {r['end_date']}"):
                st.write(pd.DataFrame([r]))
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("✅ Approve", key=f"approve_{r['id']}"):
                        try:
                            update_leave_status(int(r["id"]), "APPROVED")
                            st.success("Approved.")
                        except Exception as e:
                            st.error(str(e))
                with c2:
                    if st.button("❌ Reject", key=f"reject_{r['id']}"):
                        try:
                            update_leave_status(int(r["id"]), "REJECTED")
                            st.success("Rejected.")
                        except Exception as e:
                            st.error(str(e))
                with c3:
                    st.caption("Requested days: **{}**".format((pd.to_datetime(r['end_date']) - pd.to_datetime(r['start_date'])).days + 1))

    st.markdown("---")
    st.subheader("All Leave Requests (Filter)")
    f1, f2 = st.columns(2)
    with f1:
        filt_emp = st.text_input("Filter by Employee ID (optional)")
    with f2:
        filt_status = st.selectbox("Status", ["", "PENDING", "APPROVED", "REJECTED"], index=0)
    emp_filter = int(filt_emp) if (filt_emp.strip().isdigit()) else None
    status_filter = filt_status if filt_status else None
    st.dataframe(list_leaves(emp_filter, status_filter), use_container_width=True)

with tab_balance:
    st.subheader("Check Leave Balance & History")
    emp_id2 = st.number_input("Employee ID", min_value=1, step=1, key="bal_emp")
    if st.button("Get Balance & History"):
        try:
            bal = get_balance(int(emp_id2))
            st.success(f"Employee {int(emp_id2)} has **{bal}** days remaining.")
            st.markdown("#### Leave History")
            st.dataframe(list_leaves(int(emp_id2), None), use_container_width=True)
        except Exception as e:
            st.error(str(e))

with tab_admin:
    st.subheader("Admin / Data Utilities")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Initialize / Migrate DB"):
            init_db()
            st.success("Database initialized / migrated.")
    with c2:
        with closing(get_conn()) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM employees")
            n_emp = cur.fetchone()[0]
            cur = conn.execute("SELECT COUNT(*) FROM leave_requests")
            n_leave = cur.fetchone()[0]
        st.metric("Employees", n_emp)
        st.metric("Leave Requests", n_leave)
    with c3:
        st.caption("Download DB")
        try:
            with open(DB_PATH, "rb") as f:
                st.download_button("⬇️ Download SQLite DB", data=f, file_name="leave_mgmt.sqlite3")
        except FileNotFoundError:
            st.info("DB file not found yet. It will be created automatically once you add data.")

st.divider()
st.caption("Made with ❤️ by Ankit Dey :)")
