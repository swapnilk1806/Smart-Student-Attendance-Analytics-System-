"""SQLite data access and initialization for Smart Attendance."""
import os
import random
import sqlite3
from datetime import date, timedelta

from flask import current_app, g
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "attendance.db")
SEED_DEMO_DATA = True
DEFAULT_LATE_CREDIT = "0.5"


def init_app(app):
    app.config.setdefault("DATABASE", DB_PATH)
    app.teardown_appcontext(close_db)


def get_db():
    """Return a request-scoped SQLite connection with FK enforcement on."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db(db_path=DB_PATH):
    """Create tables, indexes and seed defaults. Safe to run repeatedly."""
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        username      TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role          TEXT NOT NULL CHECK (role IN ('admin','teacher')),
        full_name     TEXT,
        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS departments (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        code TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS students (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        reg_no          TEXT NOT NULL UNIQUE,
        full_name       TEXT NOT NULL,
        email           TEXT,
        phone           TEXT,
        department_id   INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
        class_name      TEXT NOT NULL,
        gender          TEXT,
        enrollment_date TEXT,
        created_at      TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_students_dept  ON students(department_id);
    CREATE INDEX IF NOT EXISTS idx_students_class ON students(class_name);
    CREATE INDEX IF NOT EXISTS idx_students_name  ON students(full_name);

    CREATE TABLE IF NOT EXISTS attendance (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        date       TEXT NOT NULL,
        status     TEXT NOT NULL CHECK (status IN ('Present','Absent','Late')),
        marked_by  TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (student_id, date)
    );
    CREATE INDEX IF NOT EXISTS idx_att_date    ON attendance(date);
    CREATE INDEX IF NOT EXISTS idx_att_student ON attendance(student_id);

    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # ---- Default accounts -------------------------------------------------
    if not cur.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
            ("admin", generate_password_hash("Admin@123"), "admin", "System Administrator"),
        )
    if not cur.execute("SELECT 1 FROM users WHERE username='teacher'").fetchone():
        cur.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES (?,?,?,?)",
            ("teacher", generate_password_hash("Teacher@123"), "teacher", "Demo Teacher"),
        )

    # ---- Default settings -------------------------------------------------
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('late_credit', ?)",
                (DEFAULT_LATE_CREDIT,))

    # ---- Departments ------------------------------------------------------
    depts = [("Computer Science", "CSE"), ("Information Technology", "IT"),
             ("Electronics", "ECE"), ("Mechanical", "ME"), ("Civil", "CE")]
    for name, code in depts:
        cur.execute("INSERT OR IGNORE INTO departments (name, code) VALUES (?,?)", (name, code))

    # ---- Optional demo data ----------------------------------------------
    if SEED_DEMO_DATA:
        if cur.execute("SELECT COUNT(*) c FROM students").fetchone()[0] == 0:
            rnd = random.Random(42)
            names = [
                "Aarav Sharma", "Diya Patel", "Rohan Mehta", "Ananya Iyer",
                "Kabir Singh", "Ishita Nair", "Arjun Rao", "Meera Joshi",
                "Vivaan Gupta", "Sara Khan", "Aditya Verma", "Neha Reddy",
                "Rahul Das", "Priya Menon", "Karan Malhotra", "Tanya Bose",
                "Yash Chauhan", "Riya Kapoor", "Nikhil Jain", "Pooja Desai",
            ]
            dept_rows = cur.execute("SELECT id FROM departments ORDER BY id").fetchall()
            classes = ["FY-A", "SY-A", "TY-A", "LY-A"]
            genders = ["Male", "Female"]
            for i, nm in enumerate(names, start=1):
                dep = dept_rows[(i - 1) % len(dept_rows)][0]
                cur.execute("""
                    INSERT INTO students
                        (reg_no, full_name, email, phone, department_id,
                         class_name, gender, enrollment_date)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    f"REG{2024000 + i}",
                    nm,
                    nm.lower().replace(" ", ".") + "@example.edu",
                    f"9{rnd.randint(100000000, 999999999)}",
                    dep,
                    classes[(i - 1) % len(classes)],
                    genders[i % 2],
                    (date.today() - timedelta(days=rnd.randint(200, 600))).isoformat(),
                ))

            # ~3 weeks of attendance on weekdays
            student_ids = [r[0] for r in cur.execute("SELECT id FROM students").fetchall()]
            today = date.today()
            for back in range(20, -1, -1):
                d = today - timedelta(days=back)
                if d.weekday() >= 5:          # skip weekends
                    continue
                for sid in student_ids:
                    roll = rnd.random()
                    if roll < 0.78:
                        status = "Present"
                    elif roll < 0.90:
                        status = "Late"
                    else:
                        status = "Absent"
                    cur.execute("""
                        INSERT OR IGNORE INTO attendance (student_id, date, status, marked_by)
                        VALUES (?,?,?,?)
                    """, (sid, d.isoformat(), status, "seed"))

    con.commit()
    con.close()

def get_setting(key, default=None):
    try:
        row = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    except Exception:
        return default

def set_setting(key, value):
    db = get_db()
    db.execute("INSERT INTO settings (key, value) VALUES (?,?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    db.commit()

def get_late_credit():
    """Fraction of a Present credited for a Late record (0.0 – 1.0)."""
    try:
        v = float(get_setting("late_credit", DEFAULT_LATE_CREDIT))
        return max(0.0, min(1.0, v))
    except (TypeError, ValueError):
        return float(DEFAULT_LATE_CREDIT)

def compute_student_stats(dept_id=None, start=None, end=None):
    """Return per-student attendance stats honouring the Late credit rule."""
    db = get_db()
    late_credit = get_late_credit()

    join_extra, params = "", []
    if start:
        join_extra += " AND a.date >= ?"
        params.append(start)
    if end:
        join_extra += " AND a.date <= ?"
        params.append(end)

    where, wparams = "", []
    if dept_id:
        where = " WHERE s.department_id = ?"
        wparams.append(dept_id)

    sql = f"""
        SELECT s.id, s.reg_no, s.full_name, s.class_name,
               d.name AS dept, d.id AS dept_id,
               COUNT(a.id) AS total,
               COALESCE(SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END),0) AS present,
               COALESCE(SUM(CASE WHEN a.status='Late'    THEN 1 ELSE 0 END),0) AS late,
               COALESCE(SUM(CASE WHEN a.status='Absent'  THEN 1 ELSE 0 END),0) AS absent
        FROM students s
        JOIN departments d ON d.id = s.department_id
        LEFT JOIN attendance a ON a.student_id = s.id {join_extra}
        {where}
        GROUP BY s.id
        ORDER BY s.full_name
    """
    rows = db.execute(sql, params + wparams).fetchall()

    out = []
    for r in rows:
        total = r["total"] or 0
        credits = r["present"] + r["late"] * late_credit
        pct = round(credits / total * 100, 2) if total else 0.0
        out.append({
            "id": r["id"], "reg_no": r["reg_no"], "full_name": r["full_name"],
            "class_name": r["class_name"], "dept": r["dept"], "dept_id": r["dept_id"],
            "total": total, "present": r["present"], "late": r["late"],
            "absent": r["absent"], "credits": credits, "pct": pct,
        })
    return out
