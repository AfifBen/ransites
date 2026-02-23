from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Commune, Site, User, Wilaya
from app.security import admin_required, csrf_protect, login_required

auth_bp = Blueprint("auth", __name__)


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


def _apply_user_scope(user, wilaya_ids, commune_ids, site_ids):
    # Persist many-to-many scope assignment used by access filters.
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
            if user and user.check_password(password) and user.is_active:
                login_user(user)
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


@auth_bp.route("/users/create", methods=["POST"])
@login_required
@admin_required
@csrf_protect
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    is_admin = request.form.get("is_admin") == "on"
    is_active = request.form.get("is_active") == "on"

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
    _apply_user_scope(user, wilaya_ids, commune_ids, site_ids)

    db.session.add(user)
    db.session.commit()

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

    _apply_user_scope(user, wilaya_ids, commune_ids, site_ids)

    db.session.commit()
    flash(f"Utilisateur '{user.username}' mis a jour.", "success")
    return redirect(url_for("auth.users_page"))


@auth_bp.route("/logout", methods=["POST"])
@csrf_protect
def logout():
    logout_user()
    flash("Deconnecte.", "info")
    return redirect(url_for("auth.login"))
