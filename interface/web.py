# interface/web.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask import session
from access_control.auth import authenticate_admin, login_admin, logout_admin, is_logged_in
from access_control.auth import login_required

web_bp = Blueprint("web", __name__)


@web_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        next_url = request.args.get("next") or url_for("web.index")

        if authenticate_admin(username, password):
            login_admin()
            flash("Zalogowano pomyślnie.", "success")
            return redirect(next_url)
        else:
            flash("Nieprawidłowy login lub hasło.", "danger")

    return render_template("login.html")


@web_bp.route("/logout")
def logout():
    logout_admin()
    flash("Wylogowano.", "info")
    return redirect(url_for("web.login"))


@web_bp.route("/")
@login_required
def index():
    # Strona z mapą – /static/js/main.js ogarnia mapę
    return render_template("index.html", user=session.get("user"))
