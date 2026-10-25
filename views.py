"""HTML templates and page rendering helpers."""
from flask import render_template, render_template_string, session

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f4f6fb;--card:#fff;--text:#1f2937;--muted:#6b7280;
--primary:#4f46e5;--border:#e5e7eb;--danger:#ef4444;--success:#10b981}
body{font-family:Segoe UI,system-ui,sans-serif;background:var(--bg);color:var(--text);
font-size:14px;line-height:1.5}
a{text-decoration:none;color:inherit}
.muted{color:var(--muted)}
.sidebar{position:fixed;inset:0 auto 0 0;width:240px;background:#111827;color:#cbd5e1;
display:flex;flex-direction:column;padding:18px 14px}
.brand{font-size:18px;font-weight:700;color:#fff;padding:6px 8px 18px}
.nav{display:flex;flex-direction:column;gap:4px;flex:1}
.nav-item{display:flex;gap:12px;padding:11px 12px;border-radius:10px;font-weight:500}
.nav-item:hover{background:#1f2937;color:#fff}
.nav-item.active{background:var(--primary);color:#fff}
.sidebar-footer{border-top:1px solid #1f2937;padding-top:10px}
.main{margin-left:240px;min-height:100vh}
.topbar{height:64px;background:#fff;border-bottom:1px solid var(--border);display:flex;
align-items:center;justify-content:space-between;padding:0 22px;position:sticky;top:0}
.topbar h1{font-size:17px}
.topbar-right,.user-chip{display:flex;align-items:center;gap:12px}
.user-chip{background:#f3f4f6;padding:6px 12px;border-radius:999px}
.role-badge{background:#eef2ff;color:var(--primary);padding:2px 8px;border-radius:999px}
.hamburger{display:none}
.content{padding:24px}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;
padding:20px;margin-bottom:18px;box-shadow:0 4px 18px rgba(17,24,39,.06)}
.card h3{margin-bottom:16px}
.grid,.stats-grid,.form-grid{display:grid;gap:16px}
.stats-grid{grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.stat-card{background:#fff;border:1px solid var(--border);border-radius:12px;padding:18px}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--border)}
th{font-size:12px;color:var(--muted);text-transform:uppercase}
.btn{display:inline-flex;align-items:center;gap:7px;padding:8px 12px;border:1px solid var(--border);
border-radius:8px;background:#fff;cursor:pointer;font:inherit}
.btn-primary{background:var(--primary);border-color:var(--primary);color:#fff}
.badge{display:inline-block;padding:3px 8px;border-radius:999px;background:#eef2ff}
.badge.ok,.alert.success{color:#047857;background:#d1fae5}
.badge.warn{color:#92400e;background:#fef3c7}
.badge.danger,.alert.error{color:#b91c1c;background:#fee2e2}
.badge.info{color:#1d4ed8;background:#dbeafe}
.alert{padding:10px 14px;border-radius:8px;margin-bottom:12px}
.field{margin-bottom:14px}
label{display:block;margin-bottom:5px;font-weight:600}
input,select{width:100%;padding:9px 10px;border:1px solid #d1d5db;border-radius:7px;font:inherit}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:end;margin-bottom:16px}
.filters .field{min-width:150px;margin:0}
.empty{padding:24px;text-align:center;color:var(--muted)}
.pagination{display:flex;gap:6px;margin-top:16px}
.modal{display:none;position:fixed;inset:0;background:#0008;align-items:center;justify-content:center}
.modal.open{display:flex}
.modal-content{background:#fff;padding:24px;border-radius:12px;max-width:700px;width:95%}
.form-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.login-body{min-height:100vh;display:grid;place-items:center;background:#111827}
.login-card{background:#fff;border-radius:18px;padding:38px 32px;width:100%;max-width:400px}
.login-brand{font-size:26px;text-align:center;margin-bottom:18px}
.login-card h1,.login-card .sub{text-align:center}
.login-card .sub{color:var(--muted);margin-bottom:24px}
.login-hint{margin-top:20px;padding:12px;background:#f3f4f6;text-align:center}
@media(max-width:900px){.sidebar{transform:translateX(-100%);z-index:60}
.sidebar.open{transform:translateX(0)}.main{margin-left:0}.hamburger{display:block}
.content{padding:16px}.form-grid{grid-template-columns:1fr}}
@media print{.sidebar,.topbar,.filters,.no-print,.btn{display:none!important}
.main{margin-left:0}.content{padding:0}.card{box-shadow:none}}
"""

BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} · Smart Attendance</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>""" + CSS + """</style>
</head>
<body>
<aside class="sidebar" id="sidebar">
  <div class="brand"><i class="fa-solid fa-user-graduate"></i> SmartAttend</div>
  <nav class="nav">
    <a class="nav-item {{ 'active' if active=='dashboard' }}" href="{{ url_for('dashboard') }}">Dashboard</a>
    <a class="nav-item {{ 'active' if active=='students' }}" href="{{ url_for('students') }}">Students</a>
    <a class="nav-item {{ 'active' if active=='attendance' }}" href="{{ url_for('attendance') }}">Attendance</a>
    <a class="nav-item {{ 'active' if active=='analytics' }}" href="{{ url_for('analytics') }}">Analytics</a>
    <a class="nav-item {{ 'active' if active=='reports' }}" href="{{ url_for('reports') }}">Reports</a>
    {% if role == 'admin' %}
    <a class="nav-item {{ 'active' if active=='settings' }}" href="{{ url_for('settings') }}">Settings</a>
    {% endif %}
  </nav>
  <div class="sidebar-footer"><a class="nav-item" href="{{ url_for('logout') }}">Logout</a></div>
</aside>
<div class="main">
  <header class="topbar">
    <div style="display:flex;align-items:center;gap:12px">
      <button class="hamburger" onclick="document.getElementById('sidebar').classList.toggle('open')">☰</button>
      <h1>{{ title }}</h1>
    </div>
    <div class="topbar-right"><div class="user-chip">
      <span>{{ username }}</span><span class="role-badge">{{ role }}</span>
    </div></div>
  </header>
  <main class="content">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}<div class="alert {{ cat }}">{{ msg }}</div>{% endfor %}
    {% endwith %}
    {{ body|safe }}
  </main>
</div>
<script>
document.addEventListener('click', function(e) {
  const sidebar = document.getElementById('sidebar');
  if (window.innerWidth <= 900 && sidebar.classList.contains('open')
      && !sidebar.contains(e.target) && !e.target.closest('.hamburger')) {
    sidebar.classList.remove('open');
  }
});
</script>
{{ page_scripts|safe }}
</body>
</html>"""

LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign In · Smart Attendance</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
<style>""" + CSS + """</style>
</head>
<body class="login-body">
  <div class="login-card">
    <div class="login-brand"><i class="fa-solid fa-user-graduate"></i></div>
    <h1>Smart Attendance</h1>
    <p class="sub">Student Attendance &amp; Analytics System</p>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat, msg in messages %}<div class="alert {{ cat }}">{{ msg }}</div>{% endfor %}
    {% endwith %}
    <form method="post" action="{{ url_for('login') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <div class="field"><label for="username">Username</label>
        <input id="username" name="username" required autofocus autocomplete="username"></div>
      <div class="field"><label for="password">Password</label>
        <input id="password" type="password" name="password" required autocomplete="current-password"></div>
      <button class="btn btn-primary w100">Sign In</button>
    </form>
    <div class="login-hint"><strong>Admin</strong> · admin / Admin@123<br>
      <strong>Teacher</strong> · teacher / Teacher@123</div>
  </div>
</body>
</html>"""

REPORT_TYPES = [
    ("daily", "Daily Attendance"),
    ("monthly", "Monthly Summary"),
    ("student", "Student Attendance"),
    ("department", "Department Summary"),
    ("low", "Low Attendance"),
    ("range", "Date Range"),
]


def render_page(title, body_tpl, active="", scripts="", **ctx):
    """Render a body template, then inject it into the shared layout."""
    base_ctx = {
        "title": title,
        "active": active,
        "username": session.get("username"),
        "role": session.get("role"),
    }
    base_ctx.update(ctx)
    body = render_template(body_tpl, **base_ctx)
    page_scripts = render_template(scripts, **base_ctx) if scripts else ""
    return render_template_string(BASE_TEMPLATE, body=body,
                                  page_scripts=page_scripts, **base_ctx)



def render_login():
    return render_template_string(LOGIN_TEMPLATE)
