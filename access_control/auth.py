# access_control/auth.py
from functools import wraps
from typing import Callable, Any

from flask import session, redirect, url_for, request, current_app, flash
from core.config import Config


def authenticate_admin(username: str, password: str) -> bool:
    """Sprawdza poświadczenia admina względem Config."""
    return (
        username == Config.ADMIN_USERNAME
        and password == Config.ADMIN_PASSWORD
    )


def login_admin() -> None:
    """Zapisz info o zalogowanym adminie w sesji."""
    session["user"] = Config.ADMIN_USERNAME


def logout_admin() -> None:
    session.pop("user", None)


def is_logged_in() -> bool:
    return session.get("user") == Config.ADMIN_USERNAME


def login_required(view_func: Callable) -> Callable:
    """Dekorator wymagający zalogowania admina."""

    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any):
        if not is_logged_in():
            flash("Zaloguj się, aby uzyskać dostęp.", "warning")
            # zapamiętaj gdzie chciał iść
            next_url = request.path
            return redirect(url_for("web.login", next=next_url))
        return view_func(*args, **kwargs)

    return wrapper
