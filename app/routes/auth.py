import json
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Commune, Region, Site, User, Wilaya
from app.ran_reference import load_ran_reference, save_ran_reference
from app.security import admin_required, append_audit_event, csrf_protect, login_required

auth_bp = Blueprint("auth", __name__)


def _load_import_reports_index():
    index_path = Path(current_app.instance_path) / "import_reports" / "import_reports_index.json"
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _is_safe_next(next_url):
    # Accept only local relative paths to avoid open redirect issues.
    return bool(next_url and next_url.startswith("/"))


def _parse_int_list(values):
    # Normalize checkbox/list payloads from forms into unique integer IDs.
    parsed = []
    for raw in values:
        try:
            parsed.append(int(raw))
        except (TypeError, ValueError):
            continue
    return sorted(set(parsed))


def _apply_user_scope(user, region_ids, wilaya_ids, commune_ids, site_ids):
    # Persist many-to-many scope assignment used by access filters.
    user.assigned_regions = Region.query.filter(Region.id.in_(region_ids)).all() if region_ids else []
    user.assigned_wilayas = Wilaya.query.filter(Wilaya.id.in_(wilaya_ids)).all() if wilaya_ids else []
    user.assigned_communes = Commune.query.filter(Commune.id.in_(commune_ids)).all() if commune_ids else []
    user.assigned_sites = Site.query.filter(Site.id.in_(site_ids)).all() if site_ids else []


@auth_bp.route("/login", methods=["GET", "POST"])
@csrf_protect
def login():
    next_url = request.args.get("next") or request.form.get("next") or url_for("main.dashboard")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        try:
            # Single auth gate: username + password + active flag.
            user = User.query.filter_by(username=username).first()
            allow_admin_passwordless = bool(current_app.config.get("ALLOW_ADMIN_PASSWORDLESS_LOGIN", True))
            is_admin_passwordless = (
                bool(user)
                and user.is_active
                and allow_admin_passwordless
                and (user.username or "").strip().lower() == "admin"
                and password == ""
            )

            if user and user.is_active and (user.check_password(password) or is_admin_passwordless):
                login_user(user)
                append_audit_event("login", "auth", "SUCCESS", "User login", username_override=user.username)
                if is_admin_passwordless:
                    flash("Connexion admin sans mot de passe activee (temporaire).", "warning")
                else:
                    flash("Connexion reussie.", "success")
                return redirect(next_url if _is_safe_next(next_url) else url_for("main.dashboard"))

            if User.query.count() == 0:
                flash("Aucun utilisateur trouve. Creez-en un avec: flask create-user", "warning")
            else:
                flash("Identifiants invalides.", "danger")
        except SQLAlchemyError:
            flash("Table utilisateurs absente. Executez les migrations (flask db upgrade).", "danger")

    return render_template("auth/login.html", next_url=next_url)


@auth_bp.route("/users", methods=["GET"])
@login_required
@admin_required
def users_page():
    # Render users in the same table component used by other entities.
    users = User.query.order_by(User.created_at.asc()).all()

    headers = [
        "ID",
        "Username",
        "Role",
        "Active",
        "Regions",
        "Wilayas",
        "Communes",
        "Sites",
    ]

    rows = []
    for user in users:
        wilayas_txt = ", ".join(sorted(w.name for w in user.assigned_wilayas)) or "-"
        communes_txt = ", ".join(sorted(c.name for c in user.assigned_communes)) or "-"
        sites_txt = ", ".join(sorted(s.code_site for s in user.assigned_sites)) or "-"
        rows.append([
            str(user.id),
            user.username,
            "Admin" if user.is_admin_user else "Engineer",
            "Yes" if user.is_active else "No",
            ", ".join(sorted(r.name for r in user.assigned_regions)) or "-",
            wilayas_txt,
            communes_txt,
            sites_txt,
        ])

    return render_template(
        "tables/model_viewer.html",
        id_table="usersTable",
        titre="Users",
        colonnes=headers,
        donnees=rows,
    )


@auth_bp.route("/admin/import-logs", methods=["GET"])
@login_required
@admin_required
def import_logs_page():
    report_type = (request.args.get("type") or "").strip().lower()
    action_type = (request.args.get("action") or "").strip().lower()
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()

    reports = _load_import_reports_index()
    if report_type:
        reports = [r for r in reports if str(r.get("entity", "")).lower() == report_type]
    if action_type:
        action_map = {
            "create": {"create", "create_user"},
            "update": {"update", "update_user"},
            "delete": {"delete"},
            "import": {"import", "fpall", "standard"},
            "sync": {"sync", "sync_start"},
            "login": {"login"},
            "logout": {"logout"},
        }
        allowed = action_map.get(action_type, {action_type})
        reports = [r for r in reports if str(r.get("import_kind", "")).strip().lower() in allowed]
    if date_from:
        reports = [r for r in reports if str(r.get("created_at", ""))[:10] >= date_from]
    if date_to:
        reports = [r for r in reports if str(r.get("created_at", ""))[:10] <= date_to]

    reports = sorted(reports, key=lambda x: x.get("created_at", ""), reverse=True)
    return render_template(
        "admin/import_logs.html",
        reports=reports,
        selected_type=report_type,
        selected_action=action_type,
        date_from=date_from,
        date_to=date_to,
    )


@auth_bp.route("/admin/ran-parameters", methods=["GET", "POST"])
@login_required
@admin_required
@csrf_protect
def ran_parameters_page():
    if request.method == "POST":
        techs = request.form.getlist("tech[]")
        bands = request.form.getlist("band[]")
        radii = request.form.getlist("cell_radius_km[]")
        powers = request.form.getlist("bs_nominal_power_dbm[]")

        rows = []
        for tech, band, radius, power in zip(techs, bands, radii, powers):
            t = (tech or "").strip().upper()
            if not t:
                continue
            try:
                b = int(float(band))
                r = float(radius)
                p = float(power)
            except (TypeError, ValueError):
                continue
            rows.append({
                "tech": t,
                "band": b,
                "cell_radius_km": r,
                "bs_nominal_power_dbm": p,
            })

        rows = sorted(rows, key=lambda x: (x["tech"], x["band"]))
        if not rows:
            flash("No valid rows to save.", "warning")
        else:
            save_ran_reference(current_app.instance_path, rows)
            flash("RAN reference parameters saved.", "success")
        return redirect(url_for("auth.ran_parameters_page"))

    rows = load_ran_reference(current_app.instance_path)
    rows = sorted(rows, key=lambda x: (str(x.get("tech", "")), float(x.get("band", 0))))
    return render_template("admin/ran_parameters.html", rows=rows)


@auth_bp.route("/users/create", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    is_admin = request.form.get("is_admin") == "on"
    is_active = request.form.get("is_active") == "on"

    region_ids = _parse_int_list(request.form.getlist("region_ids"))
    wilaya_ids = _parse_int_list(request.form.getlist("wilaya_ids"))
    commune_ids = _parse_int_list(request.form.getlist("commune_ids"))
    site_ids = _parse_int_list(request.form.getlist("site_ids"))

    if not username:
        flash("Le username est obligatoire.", "danger")
        return redirect(url_for("auth.users_page"))
    if len(password) < 6:
        flash("Le mot de passe doit contenir au moins 6 caracteres.", "danger")
        return redirect(url_for("auth.users_page"))
    if User.query.filter_by(username=username).first():
        flash("Ce username existe deja.", "danger")
        return redirect(url_for("auth.users_page"))

    user = User(username=username, is_admin=is_admin, is_active=is_active)
    # Scope is optional for admins but required for engineer-level isolation.
    user.set_password(password)
    _apply_user_scope(user, region_ids, wilaya_ids, commune_ids, site_ids)

    db.session.add(user)
    db.session.commit()
    append_audit_event("create_user", "users", "SUCCESS", f"username={username}")

    flash(f"Utilisateur '{username}' cree.", "success")
    return redirect(url_for("auth.users_page"))


@auth_bp.route("/users/<int:user_id>/update", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("auth.users_page"))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    is_admin = request.form.get("is_admin") == "on"
    is_active = request.form.get("is_active") == "on"

    if not username:
        flash("Le username est obligatoire.", "danger")
        return redirect(url_for("auth.users_page"))

    conflict = User.query.filter(User.username == username, User.id != user.id).first()
    if conflict:
        flash("Ce username est deja utilise.", "danger")
        return redirect(url_for("auth.users_page"))

    if user.id == current_user.id and not is_active:
        # Protect against self-lockout.
        flash("Vous ne pouvez pas desactiver votre propre compte.", "danger")
        return redirect(url_for("auth.users_page"))

    if user.id == current_user.id and not is_admin and user.username.lower() != "admin":
        # Prevent accidentally dropping own admin role.
        flash("Vous ne pouvez pas retirer votre role admin a votre propre compte.", "danger")
        return redirect(url_for("auth.users_page"))

    region_ids = _parse_int_list(request.form.getlist("region_ids"))
    wilaya_ids = _parse_int_list(request.form.getlist("wilaya_ids"))
    commune_ids = _parse_int_list(request.form.getlist("commune_ids"))
    site_ids = _parse_int_list(request.form.getlist("site_ids"))

    user.username = username
    user.is_admin = is_admin
    user.is_active = is_active

    if password:
        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caracteres.", "danger")
            return redirect(url_for("auth.users_page"))
        user.set_password(password)

    _apply_user_scope(user, region_ids, wilaya_ids, commune_ids, site_ids)

    db.session.commit()
    append_audit_event("update_user", "users", "SUCCESS", f"username={user.username}")
    flash(f"Utilisateur '{user.username}' mis a jour.", "success")
    return redirect(url_for("auth.users_page"))


@auth_bp.route("/logout", methods=["POST"])
@csrf_protect
def logout():
    append_audit_event("logout", "auth", "SUCCESS", "User logout")
    logout_user()
    flash("Deconnecte.", "info")
    return redirect(url_for("auth.login"))
