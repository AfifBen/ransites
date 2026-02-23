import os
import secrets

import click
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from app.security import generate_csrf_token

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Veuillez vous connecter pour continuer."
login_manager.login_message_category = "warning"


def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///radio.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    app.jinja_env.add_extension("jinja2.ext.do")
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from app import models  # noqa: F401
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.cli.command("create-user")
    @click.option("--username", prompt=True, help="Nom d'utilisateur")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Mot de passe")
    @click.option("--admin/--no-admin", default=False, help="Creer le compte avec droits administrateur.")
    def create_user(username, password, admin):
        existing = db.session.query(User).filter_by(username=username).first()
        if existing:
            raise click.ClickException(f"L'utilisateur '{username}' existe deja.")

        user = User(username=username, is_admin=admin)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        role = "admin" if admin else "engineer"
        click.echo(f"Utilisateur '{username}' cree ({role}).")

    from app.routes.list_data import list_bp
    app.register_blueprint(list_bp, url_prefix="/")

    from app.routes.main import main_bp
    app.register_blueprint(main_bp)

    from app.routes.import_data import import_bp
    app.register_blueprint(import_bp, url_prefix="/import")

    from app.routes.delete_data import delete_bp
    app.register_blueprint(delete_bp)

    from app.routes.edit_data import edit_data_bp
    app.register_blueprint(edit_data_bp)

    from app.routes.helpers import helper_bp
    app.register_blueprint(helper_bp)

    from app.routes.doc_data import doc_bp
    app.register_blueprint(doc_bp)

    from app.routes.add_data import add_data_bp
    app.register_blueprint(add_data_bp)

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    return app
