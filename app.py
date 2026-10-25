#!/usr/bin/env python3
"""Application entry point for the Smart Attendance MVC application.

Run locally with: python app.py
"""
import os

from flask import Flask

from controllers import csrf_token, register_routes
from models import DB_PATH, init_app as init_models, init_db


def create_app():
    app = Flask(__name__)
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        secret_key = "dev-insecure-key-please-set-SECRET_KEY-env-var"
        print("[WARNING] SECRET_KEY environment variable not set. "
              "Using an insecure development key. Set SECRET_KEY before deploying.")
    app.secret_key = secret_key
    init_models(app)
    app.jinja_env.globals["csrf_token"] = csrf_token
    register_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        init_db()
    print("=" * 62)
    print(" Smart Student Attendance & Analytics System")
    print("=" * 62)
    print(f" Database : {DB_PATH}")
    print(" Admin    : admin / Admin@123")
    print(" Teacher  : teacher / Teacher@123")
    print(" URL      : http://127.0.0.1:5000")
    print("=" * 62)
    app.run(host="127.0.0.1", port=5000, debug=True)
