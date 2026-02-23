import hmac
import secrets
from functools import wraps

from flask import flash, jsonify, redirect, request, session, url_for
from flask_login import current_user


def generate_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf_token():
    sent_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    session_token = session.get("_csrf_token")
    return bool(session_token and sent_token and hmac.compare_digest(session_token, sent_token))


def is_authenticated():
    return bool(current_user.is_authenticated)


def is_admin_user():
    return bool(is_authenticated() and getattr(current_user, "is_admin_user", False))


def get_accessible_commune_ids():
    if not is_authenticated():
        return set()
    if is_admin_user():
        return None

    commune_ids = {c.id for c in getattr(current_user, "assigned_communes", [])}
    wilaya_ids = {w.id for w in getattr(current_user, "assigned_wilayas", [])}
    site_ids = {s.id for s in getattr(current_user, "assigned_sites", [])}

    if wilaya_ids:
        from app import db
        from app.models import Commune

        rows = db.session.query(Commune.id).filter(Commune.wilaya_id.in_(list(wilaya_ids))).all()
        commune_ids.update(row[0] for row in rows)

    if site_ids:
        from app import db
        from app.models import Site

        rows = db.session.query(Site.commune_id).filter(Site.id.in_(list(site_ids))).all()
        commune_ids.update(row[0] for row in rows if row[0] is not None)

    return commune_ids


def get_accessible_site_ids():
    if not is_authenticated():
        return set()
    if is_admin_user():
        return None

    from app import db
    from app.models import Site

    site_ids = {s.id for s in getattr(current_user, "assigned_sites", [])}
    commune_ids = get_accessible_commune_ids() or set()

    if commune_ids:
        rows = db.session.query(Site.id).filter(Site.commune_id.in_(list(commune_ids))).all()
        site_ids.update(row[0] for row in rows)

    return site_ids


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_admin_user():
            return view(*args, **kwargs)
        flash("Acces reserve aux administrateurs.", "danger")
        return redirect(url_for("main.dashboard"))

    return wrapped


def _unauthorized_response():
    if request.path.startswith(("/delete_items", "/update_item", "/add_item", "/import/", "/get_item")):
        return jsonify({"success": False, "message": "Authentification requise."}), 401
    return redirect(url_for("auth.login", next=request.path))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_authenticated():
            return view(*args, **kwargs)
        flash("Veuillez vous connecter pour continuer.", "warning")
        return _unauthorized_response()

    return wrapped


def csrf_protect(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if not validate_csrf_token():
                if request.path.startswith(("/delete_items", "/update_item", "/add_item", "/import/")):
                    return jsonify({"success": False, "message": "Token CSRF invalide."}), 400
                flash("Token CSRF invalide.", "danger")
                return redirect(request.referrer or url_for("main.dashboard"))
        return view(*args, **kwargs)

    return wrapped
