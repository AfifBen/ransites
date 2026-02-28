import hmac
import secrets
import json
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import current_app, flash, jsonify, redirect, request, session, url_for
from flask_login import current_user


def _safe_relation_ids(user_obj, relation_name):
    # Keep app usable when a new relation table exists in code but not yet in DB.
    try:
        return {obj.id for obj in getattr(user_obj, relation_name, [])}
    except Exception:
        return set()


def append_audit_event(action, entity, status="SUCCESS", message="", username_override=None):
    # Write lightweight user audit events to instance/audit_events.json.
    try:
        username = username_override
        if not username:
            username = (
                getattr(current_user, "username", None)
                if getattr(current_user, "is_authenticated", False)
                else "anonymous"
            )
        reports_dir = Path(current_app.instance_path) / "import_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        out_path = reports_dir / "audit_events.json"
        index_path = reports_dir / "import_reports_index.json"
        now_iso = datetime.utcnow().isoformat()
        safe_action = str(action or "").strip().lower()
        safe_entity = str(entity or "").strip().lower()
        safe_status = str(status or "SUCCESS").strip().upper()
        safe_message = str(message or "")
        safe_username = str(username or "unknown")
        rows = []
        if out_path.exists():
            try:
                rows = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception:
                rows = []
        rows.append(
            {
                "created_at": now_iso,
                "username": safe_username,
                "action": safe_action,
                "entity": safe_entity,
                "status": safe_status,
                "message": safe_message,
            }
        )
        rows = rows[-5000:]
        out_path.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")

        # Also append as generic admin log entry so it appears in Administration > Import Logs.
        idx_rows = []
        if index_path.exists():
            try:
                idx_rows = json.loads(index_path.read_text(encoding="utf-8"))
            except Exception:
                idx_rows = []
        idx_rows.append(
            {
                "id": f"audit_{safe_action}_{int(datetime.utcnow().timestamp() * 1000)}",
                "created_at": now_iso,
                "entity": safe_entity or "system",
                "import_kind": safe_action,
                "source_file": "",
                "status": safe_status,
                "message": safe_message,
                "failed_rows_count": 0,
                "report_path": "",
                "log_source": "audit",
                "username": safe_username,
            }
        )
        idx_rows = idx_rows[-10000:]
        index_path.write_text(json.dumps(idx_rows, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception:
        # Audit logging must never break business flow.
        pass


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

    commune_ids = _safe_relation_ids(current_user, "assigned_communes")
    wilaya_ids = _safe_relation_ids(current_user, "assigned_wilayas")
    site_ids = _safe_relation_ids(current_user, "assigned_sites")

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

    site_ids = _safe_relation_ids(current_user, "assigned_sites")
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
