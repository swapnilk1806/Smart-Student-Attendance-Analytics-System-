"""Request handlers for Smart Attendance."""
import io
import re
import csv
import sqlite3
import secrets
from datetime import datetime, date, timedelta
from functools import wraps
from flask import request, session, redirect, url_for, flash, Response
from werkzeug.security import check_password_hash

from models import (
    compute_student_stats,
    get_db,
    get_late_credit,
    set_setting,
)
from views import REPORT_TYPES, render_login, render_page

VALID_STATUSES = ("Present", "Absent", "Late")


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]

def csrf_valid():
    token = session.get("csrf_token")
    sent = request.form.get("csrf_token", "")
    return bool(token) and bool(sent) and secrets.compare_digest(token, sent)

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "error")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Administrator access required for that action.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped

def safe_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def valid_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False

def index():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        if not csrf_valid():
            flash("Your session expired. Please try again.", "error")
            return redirect(url_for("login"))
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            csrf_token()
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
        return redirect(url_for("login"))

    return render_login()

def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))

@login_required
def dashboard():
    db = get_db()
    late_credit = get_late_credit()
    today = date.today().isoformat()

    total_students = db.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]
    total_departments = db.execute("SELECT COUNT(*) c FROM departments").fetchone()["c"]
    total_records = db.execute("SELECT COUNT(*) c FROM attendance").fetchone()["c"]

    t = db.execute("""
        SELECT COALESCE(SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END),0) p,
               COALESCE(SUM(CASE WHEN status='Late'    THEN 1 ELSE 0 END),0) l,
               COALESCE(SUM(CASE WHEN status='Absent'  THEN 1 ELSE 0 END),0) a
        FROM attendance WHERE date = ?
    """, (today,)).fetchone()
    today_present, today_late, today_absent = t["p"], t["l"], t["a"]

    ov = db.execute("""
        SELECT COUNT(*) total,
               COALESCE(SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END),0) p,
               COALESCE(SUM(CASE WHEN status='Late'    THEN 1 ELSE 0 END),0) l,
               COALESCE(SUM(CASE WHEN status='Absent'  THEN 1 ELSE 0 END),0) a
        FROM attendance
    """).fetchone()
    overall_pct = round(
        (ov["p"] + ov["l"] * late_credit) / ov["total"] * 100, 1
    ) if ov["total"] else 0.0

    # Doughnut — overall status split
    doughnut = [ov["p"], ov["l"], ov["a"]]

    # Monthly trend (last 6 months with data)
    mrows = db.execute("""
        SELECT substr(date,1,7) AS ym, COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END),0) p,
               COALESCE(SUM(CASE WHEN status='Late'    THEN 1 ELSE 0 END),0) l
        FROM attendance GROUP BY ym ORDER BY ym DESC LIMIT 6
    """).fetchall()
    mrows = list(reversed(mrows))
    month_labels = [r["ym"] for r in mrows]
    month_pct = [round((r["p"] + r["l"] * late_credit) / r["total"] * 100, 1)
                 if r["total"] else 0 for r in mrows]

    # Weekly — last 7 calendar days
    days = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    per_day = {}
    for r in db.execute("""
        SELECT date, status, COUNT(*) c FROM attendance
        WHERE date >= ? GROUP BY date, status
    """, (days[0],)).fetchall():
        per_day.setdefault(r["date"], {})[r["status"]] = r["c"]
    week_labels = [d[5:] for d in days]
    week_present = [per_day.get(d, {}).get("Present", 0) for d in days]
    week_late = [per_day.get(d, {}).get("Late", 0) for d in days]
    week_absent = [per_day.get(d, {}).get("Absent", 0) for d in days]

    # Department distribution
    drows = db.execute("""
        SELECT d.name, COUNT(s.id) c
        FROM departments d LEFT JOIN students s ON s.department_id = d.id
        GROUP BY d.id ORDER BY d.name
    """).fetchall()
    dept_labels = [r["name"] for r in drows]
    dept_counts = [r["c"] for r in drows]

    body = 'dashboard.html'

    scripts = 'dashboard_scripts.html'

    return render_page("Dashboard", body, active="dashboard", scripts=scripts,
                       total_students=total_students,
                       total_departments=total_departments,
                       total_records=total_records,
                       today_present=today_present,
                       today_absent=today_absent,
                       today_late=today_late,
                       overall_pct=overall_pct,
                       late_credit=late_credit,
                       doughnut=doughnut,
                       month_labels=month_labels, month_pct=month_pct,
                       week_labels=week_labels, week_present=week_present,
                       week_late=week_late, week_absent=week_absent,
                       dept_labels=dept_labels, dept_counts=dept_counts)

@login_required
def students():
    db = get_db()
    q = (request.args.get("q") or "").strip()
    dept = (request.args.get("dept") or "").strip()
    klass = (request.args.get("class") or "").strip()
    page = max(1, safe_int(request.args.get("page"), 1) or 1)
    per_page = 10

    where, params = [], []
    if q:
        where.append("(s.full_name LIKE ? OR s.reg_no LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if dept:
        where.append("s.department_id = ?")
        params.append(safe_int(dept))
    if klass:
        where.append("s.class_name = ?")
        params.append(klass)
    wsql = ("WHERE " + " AND ".join(where)) if where else ""

    total = db.execute(f"SELECT COUNT(*) c FROM students s {wsql}", params).fetchone()["c"]
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    rows = db.execute(f"""
        SELECT s.*, d.name AS dept_name, d.code AS dept_code
        FROM students s JOIN departments d ON d.id = s.department_id
        {wsql}
        ORDER BY s.full_name
        LIMIT ? OFFSET ?
    """, params + [per_page, offset]).fetchall()

    departments = db.execute("SELECT * FROM departments ORDER BY name").fetchall()
    classes = [r["class_name"] for r in
               db.execute("SELECT DISTINCT class_name FROM students ORDER BY class_name")]
    page_links = list(range(max(1, page - 2), min(total_pages, page + 2) + 1))

    body = 'students.html'

    scripts = 'students_scripts.html'

    return render_page("Students", body, active="students", scripts=scripts,
                       rows=rows, total=total, page=page, total_pages=total_pages,
                       page_links=page_links, q=q, dept=dept, klass=klass,
                       departments=departments, classes=classes)

def _collect_student_form():
    return {
        "reg_no": (request.form.get("reg_no") or "").strip(),
        "full_name": (request.form.get("full_name") or "").strip(),
        "email": (request.form.get("email") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "department_id": safe_int(request.form.get("department_id")),
        "class_name": (request.form.get("class_name") or "").strip(),
        "gender": (request.form.get("gender") or "").strip(),
        "enrollment_date": (request.form.get("enrollment_date") or "").strip(),
    }

def _validate_student(data, exclude_id=None):
    db = get_db()
    errors = []
    if not data["reg_no"]:
        errors.append("Registration number is required.")
    if not data["full_name"]:
        errors.append("Full name is required.")
    if not data["department_id"]:
        errors.append("Department is required.")
    elif not db.execute("SELECT 1 FROM departments WHERE id=?",
                        (data["department_id"],)).fetchone():
        errors.append("Selected department does not exist.")
    if not data["class_name"]:
        errors.append("Class / Year is required.")
    if data["email"] and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", data["email"]):
        errors.append("Email address is not valid.")
    if data["enrollment_date"] and not valid_date(data["enrollment_date"]):
        errors.append("Enrollment date must be YYYY-MM-DD.")
    if data["reg_no"]:
        if exclude_id:
            dup = db.execute("SELECT 1 FROM students WHERE reg_no=? AND id<>?",
                             (data["reg_no"], exclude_id)).fetchone()
        else:
            dup = db.execute("SELECT 1 FROM students WHERE reg_no=?",
                             (data["reg_no"],)).fetchone()
        if dup:
            errors.append(f"Registration number '{data['reg_no']}' already exists.")
    return errors

@admin_required
def students_add():
    if not csrf_valid():
        flash("Invalid session token. Please retry.", "error")
        return redirect(url_for("students"))
    data = _collect_student_form()
    errors = _validate_student(data)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("students"))

    db = get_db()
    try:
        db.execute("""
            INSERT INTO students
              (reg_no, full_name, email, phone, department_id,
               class_name, gender, enrollment_date)
            VALUES (?,?,?,?,?,?,?,?)
        """, (data["reg_no"], data["full_name"], data["email"], data["phone"],
              data["department_id"], data["class_name"], data["gender"],
              data["enrollment_date"] or None))
        db.commit()
        flash(f"Student '{data['full_name']}' added successfully.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Could not add student: duplicate registration number.", "error")
    except sqlite3.Error as exc:
        db.rollback()
        flash(f"Database error: {exc}", "error")
    return redirect(url_for("students"))

@admin_required
def students_edit(student_id):
    if not csrf_valid():
        flash("Invalid session token. Please retry.", "error")
        return redirect(url_for("students"))
    db = get_db()
    existing = db.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    if not existing:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    data = _collect_student_form()
    errors = _validate_student(data, exclude_id=student_id)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("students"))

    try:
        db.execute("""
            UPDATE students SET reg_no=?, full_name=?, email=?, phone=?,
                   department_id=?, class_name=?, gender=?, enrollment_date=?
            WHERE id=?
        """, (data["reg_no"], data["full_name"], data["email"], data["phone"],
              data["department_id"], data["class_name"], data["gender"],
              data["enrollment_date"] or None, student_id))
        db.commit()
        flash("Student updated successfully.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Update failed: duplicate registration number.", "error")
    except sqlite3.Error as exc:
        db.rollback()
        flash(f"Database error: {exc}", "error")
    return redirect(url_for("students"))

@admin_required
def students_delete(student_id):
    if not csrf_valid():
        flash("Invalid session token. Please retry.", "error")
        return redirect(url_for("students"))
    db = get_db()
    row = db.execute("SELECT full_name FROM students WHERE id=?", (student_id,)).fetchone()
    if not row:
        flash("Student not found.", "error")
        return redirect(url_for("students"))
    try:
        db.execute("DELETE FROM students WHERE id=?", (student_id,))
        db.commit()
        flash(f"Student '{row['full_name']}' deleted.", "success")
    except sqlite3.Error as exc:
        db.rollback()
        flash(f"Could not delete student: {exc}", "error")
    return redirect(url_for("students"))

@login_required
def attendance():
    db = get_db()
    sel_date = request.args.get("date") or date.today().isoformat()
    if not valid_date(sel_date):
        sel_date = date.today().isoformat()
    dept = safe_int(request.args.get("department"))
    klass = (request.args.get("class") or "").strip()

    where, params = ["1=1"], [sel_date]
    if dept:
        where.append("s.department_id = ?")
        params.append(dept)
    if klass:
        where.append("s.class_name = ?")
        params.append(klass)

    rows = db.execute(f"""
        SELECT s.id, s.reg_no, s.full_name, s.class_name,
               d.name AS dept_name, d.code AS dept_code,
               a.status AS current_status
        FROM students s
        JOIN departments d ON d.id = s.department_id
        LEFT JOIN attendance a ON a.student_id = s.id AND a.date = ?
        WHERE {' AND '.join(where)}
        ORDER BY s.class_name, s.full_name
    """, params).fetchall()

    departments = db.execute("SELECT * FROM departments ORDER BY name").fetchall()
    classes = [r["class_name"] for r in
               db.execute("SELECT DISTINCT class_name FROM students ORDER BY class_name")]

    marked = sum(1 for r in rows if r["current_status"])

    body = 'attendance.html'

    scripts = 'attendance_scripts.html'

    return render_page("Attendance", body, active="attendance", scripts=scripts,
                       rows=rows, departments=departments, classes=classes,
                       sel_date=sel_date, dept=dept, klass=klass, marked=marked)

@login_required
def attendance_save():
    if not csrf_valid():
        flash("Invalid session token. Please retry.", "error")
        return redirect(url_for("attendance"))

    sel_date = (request.form.get("date") or "").strip()
    if not valid_date(sel_date):
        flash("A valid attendance date is required.", "error")
        return redirect(url_for("attendance"))

    dept = request.form.get("department") or ""
    klass = request.form.get("class") or ""

    entries = []
    for key in request.form:
        if key.startswith("status_"):
            sid = safe_int(key[len("status_"):])
            status = request.form.get(key)
            if sid and status in VALID_STATUSES:
                entries.append((sid, status))

    if not entries:
        flash("No attendance entries were submitted.", "error")
        return redirect(url_for("attendance", date=sel_date, department=dept, **{"class": klass}))

    db = get_db()
    try:
        for sid, status in entries:
            db.execute("""
                INSERT INTO attendance (student_id, date, status, marked_by)
                VALUES (?,?,?,?)
                ON CONFLICT(student_id, date)
                DO UPDATE SET status = excluded.status, marked_by = excluded.marked_by
            """, (sid, sel_date, status, session.get("username", "system")))
        db.commit()
        flash(f"Attendance saved for {len(entries)} student(s) on {sel_date}.", "success")
    except sqlite3.IntegrityError as exc:
        db.rollback()
        flash(f"Save failed (integrity): {exc}", "error")
    except sqlite3.Error as exc:
        db.rollback()
        flash(f"Save failed: {exc}", "error")

    return redirect(url_for("attendance", date=sel_date, department=dept, **{"class": klass}))

@login_required
def attendance_history(student_id):
    db = get_db()
    student = db.execute("""
        SELECT s.*, d.name AS dept_name FROM students s
        JOIN departments d ON d.id = s.department_id WHERE s.id=?
    """, (student_id,)).fetchone()
    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    late_credit = get_late_credit()
    records = db.execute("""
        SELECT date, status, marked_by FROM attendance
        WHERE student_id=? ORDER BY date DESC
    """, (student_id,)).fetchall()

    total = len(records)
    present = sum(1 for r in records if r["status"] == "Present")
    late = sum(1 for r in records if r["status"] == "Late")
    absent = sum(1 for r in records if r["status"] == "Absent")
    pct = round((present + late * late_credit) / total * 100, 2) if total else 0.0

    if pct >= 85:
        risk_cls, risk_txt = "ok", "Good Standing"
    elif pct >= 75:
        risk_cls, risk_txt = "warn", "Watch List"
    else:
        risk_cls, risk_txt = "danger", "At Risk (<75%)"

    body = 'attendance_history.html'

    return render_page("Attendance History", body, active="students",
                       student=student, records=records, total=total,
                       present=present, late=late, absent=absent, pct=pct,
                       risk_cls=risk_cls, risk_txt=risk_txt)

@login_required
def analytics():
    db = get_db()
    late_credit = get_late_credit()

    start = request.args.get("start") or ""
    end = request.args.get("end") or ""
    dept = safe_int(request.args.get("department"))
    if start and not valid_date(start):
        start = ""
    if end and not valid_date(end):
        end = ""

    stats = compute_student_stats(dept, start or None, end or None)
    departments = db.execute("SELECT * FROM departments ORDER BY name").fetchall()

    active = [s for s in stats if s["total"] > 0]
    low = [s for s in active if s["pct"] < 75]
    mid = [s for s in active if 75 <= s["pct"] <= 85]
    high = [s for s in active if s["pct"] > 85]

    total_sessions = sum(s["total"] for s in stats)
    total_credits = sum(s["credits"] for s in stats)
    overall_pct = round(total_credits / total_sessions * 100, 2) if total_sessions else 0.0

    top10 = sorted(active, key=lambda s: (-s["pct"], -s["total"]))[:10]

    dept_map = {}
    for s in stats:
        d = dept_map.setdefault(s["dept"], {
            "dept": s["dept"], "students": 0, "sessions": 0,
            "credits": 0.0, "present": 0, "late": 0, "absent": 0})
        d["students"] += 1
        d["sessions"] += s["total"]
        d["credits"] += s["credits"]
        d["present"] += s["present"]
        d["late"] += s["late"]
        d["absent"] += s["absent"]
    dept_stats = []
    for d in dept_map.values():
        d["pct"] = round(d["credits"] / d["sessions"] * 100, 2) if d["sessions"] else 0.0
        dept_stats.append(d)
    dept_stats.sort(key=lambda x: x["dept"])

    body = 'analytics.html'

    return render_page("Analytics", body, active="analytics",
                       stats=stats, departments=departments,
                       start=start, end=end, dept=dept,
                       late_credit=late_credit, overall_pct=overall_pct,
                       low=low, mid=mid, high=high, top10=top10,
                       dept_stats=dept_stats)

def build_report(rtype, args):
    """Return (title, headers, rows) for the requested report type."""
    db = get_db()
    late_credit = get_late_credit()

    if rtype == "daily":
        d = args.get("date") or date.today().isoformat()
        if not valid_date(d):
            d = date.today().isoformat()
        title = f"Daily Attendance Report - {d}"
        headers = ["Reg No", "Student Name", "Department", "Class", "Status", "Marked By"]
        rows = [[r["reg_no"], r["full_name"], r["dept_name"], r["class_name"],
                 r["status"], r["marked_by"] or ""]
                for r in db.execute("""
                    SELECT s.reg_no, s.full_name, d.name AS dept_name, s.class_name,
                           a.status, a.marked_by
                    FROM attendance a
                    JOIN students s ON s.id = a.student_id
                    JOIN departments d ON d.id = s.department_id
                    WHERE a.date = ? ORDER BY s.full_name
                """, (d,)).fetchall()]
        return title, headers, rows

    if rtype == "monthly":
        month = args.get("month") or date.today().strftime("%Y-%m")
        title = f"Monthly Attendance Report - {month}"
        headers = ["Reg No", "Student Name", "Department", "Class",
                   "Present", "Late", "Absent", "Sessions", "Attendance %"]
        rows = db.execute("""
            SELECT s.reg_no, s.full_name, d.name AS dept_name, s.class_name,
                   COALESCE(SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END),0) p,
                   COALESCE(SUM(CASE WHEN a.status='Late'    THEN 1 ELSE 0 END),0) l,
                   COALESCE(SUM(CASE WHEN a.status='Absent'  THEN 1 ELSE 0 END),0) ab,
                   COUNT(a.id) total
            FROM students s
            JOIN departments d ON d.id = s.department_id
            LEFT JOIN attendance a ON a.student_id = s.id AND substr(a.date,1,7) = ?
            GROUP BY s.id ORDER BY s.full_name
        """, (month,)).fetchall()
        out = []
        for r in rows:
            pct = round((r["p"] + r["l"] * late_credit) / r["total"] * 100, 2) if r["total"] else 0.0
            out.append([r["reg_no"], r["full_name"], r["dept_name"], r["class_name"],
                        r["p"], r["l"], r["ab"], r["total"], pct])
        return title, headers, out

    if rtype == "student":
        sid = safe_int(args.get("student_id"))
        if not sid:
            return "Student Report", ["Info"], [["Please select a student."]]
        stu = db.execute("""
            SELECT s.*, d.name AS dept_name FROM students s
            JOIN departments d ON d.id = s.department_id WHERE s.id=?
        """, (sid,)).fetchone()
        if not stu:
            return "Student Report", ["Info"], [["Student not found."]]
        title = f"Student Attendance Report - {stu['full_name']} ({stu['reg_no']})"
        headers = ["Date", "Status", "Marked By"]
        rows = [[r["date"], r["status"], r["marked_by"] or ""]
                for r in db.execute("""
                    SELECT date, status, marked_by FROM attendance
                    WHERE student_id=? ORDER BY date DESC
                """, (sid,)).fetchall()]
        return title, headers, rows

    if rtype == "department":
        start = args.get("start") or ""
        end = args.get("end") or ""
        title = "Department-wise Attendance Report"
        if start or end:
            title += f" ({start or '…'} to {end or '…'})"
        headers = ["Department", "Students", "Present", "Late", "Absent",
                   "Sessions", "Attendance %"]
        stats = compute_student_stats(None, start or None, end or None)
        agg = {}
        for s in stats:
            d = agg.setdefault(s["dept"], {"students": 0, "sessions": 0, "credits": 0.0,
                                           "present": 0, "late": 0, "absent": 0})
            d["students"] += 1
            d["sessions"] += s["total"]
            d["credits"] += s["credits"]
            d["present"] += s["present"]
            d["late"] += s["late"]
            d["absent"] += s["absent"]
        rows = []
        for name in sorted(agg):
            d = agg[name]
            pct = round(d["credits"] / d["sessions"] * 100, 2) if d["sessions"] else 0.0
            rows.append([name, d["students"], d["present"], d["late"], d["absent"],
                         d["sessions"], pct])
        return title, headers, rows

    if rtype == "low":
        title = "Low Attendance Report (below 75%)"
        headers = ["Reg No", "Student Name", "Department", "Class",
                   "Present", "Late", "Absent", "Sessions", "Attendance %"]
        stats = compute_student_stats(None, None, None)
        rows = [[s["reg_no"], s["full_name"], s["dept"], s["class_name"],
                 s["present"], s["late"], s["absent"], s["total"], s["pct"]]
                for s in sorted(stats, key=lambda x: x["pct"])
                if s["total"] > 0 and s["pct"] < 75]
        return title, headers, rows

    # default: date range
    start = args.get("start") or (date.today() - timedelta(days=30)).isoformat()
    end = args.get("end") or date.today().isoformat()
    if not valid_date(start):
        start = (date.today() - timedelta(days=30)).isoformat()
    if not valid_date(end):
        end = date.today().isoformat()
    title = f"Date-range Attendance Report ({start} to {end})"
    headers = ["Reg No", "Student Name", "Department", "Class",
               "Present", "Late", "Absent", "Sessions", "Attendance %"]
    stats = compute_student_stats(None, start, end)
    rows = [[s["reg_no"], s["full_name"], s["dept"], s["class_name"],
             s["present"], s["late"], s["absent"], s["total"], s["pct"]]
            for s in stats]
    return title, headers, rows

@login_required
def reports():
    db = get_db()
    rtype = request.args.get("type") or "daily"
    if rtype not in [t[0] for t in REPORT_TYPES]:
        rtype = "daily"

    title, headers, rows = build_report(rtype, request.args)
    students_list = db.execute(
        "SELECT id, reg_no, full_name FROM students ORDER BY full_name").fetchall()

    # Preserve current filters on export link
    qs = "&".join(f"{k}={v}" for k, v in request.args.items() if k != "type")

    body = 'reports.html'

    return render_page("Reports", body, active="reports",
                       report_types=REPORT_TYPES, rtype=rtype,
                       report_title=title, headers=headers, rows=rows,
                       students_list=students_list, request=request)

@login_required
def reports_export():
    rtype = request.args.get("type") or "daily"
    if rtype not in [t[0] for t in REPORT_TYPES]:
        rtype = "daily"

    title, headers, rows = build_report(rtype, request.args)

    buf = io.StringIO()
    buf.write("\ufeff")          # BOM so Excel opens UTF-8 correctly
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(r)

    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_")[:60] or "report"
    filename = f"{safe_name}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@admin_required
def settings():
    db = get_db()
    if request.method == "POST":
        if not csrf_valid():
            flash("Invalid session token. Please retry.", "error")
            return redirect(url_for("settings"))
        raw = (request.form.get("late_credit") or "").strip()
        try:
            val = float(raw)
            if not 0.0 <= val <= 1.0:
                raise ValueError
            set_setting("late_credit", f"{val:g}")
            flash("Settings saved.", "success")
        except ValueError:
            flash("Late credit must be a number between 0.0 and 1.0.", "error")
        return redirect(url_for("settings"))

    late_credit = get_late_credit()
    users = db.execute("SELECT id, username, role, full_name, created_at "
                       "FROM users ORDER BY id").fetchall()

    body = 'settings.html'

    return render_page("Settings", body, active="settings",
                       late_credit=late_credit, users=users)

def not_found(e):
    if session.get("user_id"):
        flash("Page not found.", "error")
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

def server_error(e):
    return ("<h2 style='font-family:sans-serif;padding:30px'>"
            "500 — Internal Server Error</h2>"
            "<p style='font-family:sans-serif;padding:0 30px'>"
            "Please check the console for details.</p>"), 500



def register_routes(app):
    app.add_url_rule(r'/', endpoint='index', view_func=index)
    app.add_url_rule(r'/login', endpoint='login', view_func=login, methods=['GET', 'POST'])
    app.add_url_rule(r'/logout', endpoint='logout', view_func=logout)
    app.add_url_rule(r'/dashboard', endpoint='dashboard', view_func=dashboard)
    app.add_url_rule(r'/students', endpoint='students', view_func=students)
    app.add_url_rule(r'/students/add', endpoint='students_add', view_func=students_add, methods=['POST'])
    app.add_url_rule(r'/students/edit/<int:student_id>', endpoint='students_edit', view_func=students_edit, methods=['POST'])
    app.add_url_rule(r'/students/delete/<int:student_id>', endpoint='students_delete', view_func=students_delete, methods=['POST'])
    app.add_url_rule(r'/attendance', endpoint='attendance', view_func=attendance)
    app.add_url_rule(r'/attendance/save', endpoint='attendance_save', view_func=attendance_save, methods=['POST'])
    app.add_url_rule(r'/attendance/history/<int:student_id>', endpoint='attendance_history', view_func=attendance_history)
    app.add_url_rule(r'/analytics', endpoint='analytics', view_func=analytics)
    app.add_url_rule(r'/reports', endpoint='reports', view_func=reports)
    app.add_url_rule(r'/reports/export', endpoint='reports_export', view_func=reports_export)
    app.add_url_rule(r'/settings', endpoint='settings', view_func=settings, methods=['GET', 'POST'])
    app.register_error_handler(404, not_found)
    app.register_error_handler(500, server_error)
