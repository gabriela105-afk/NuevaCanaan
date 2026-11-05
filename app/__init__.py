"""Fábrica de la aplicación Flask (patrón application factory + blueprints)."""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, g, redirect, render_template, request, url_for
from flask_login import current_user, logout_user
from flask_wtf.csrf import CSRFError
from markupsafe import Markup, escape
from sqlalchemy.exc import OperationalError, ProgrammingError

from config import INSTANCE_DIR, get_config, mask_database_uri
from .extensions import csrf, db, login_manager, migrate
from .models import (
    ANNOUNCEMENT_CATEGORY_LABELS,
    ANNOUNCEMENT_STATUS_LABELS,
    ASSIGNMENT_KIND_LABELS,
    ATTENDANCE_STATUS_LABELS,
    AUDIENCE_LABELS,
    ENROLLMENT_STATUS_LABELS,
    EVENT_CATEGORY_LABELS,
    NEWS_CATEGORY_LABELS,
    NEWS_COMMENT_STATUS_LABELS,
    NEWS_STATUS_LABELS,
    PRIORITY_LABELS,
    ROLE_LABELS,
    Message,
    Notification,
    User,
)
from .utils import (
    format_bytes,
    format_date,
    format_datetime,
    format_long_date,
    format_news_datetime,
    format_short_date,
    format_time_ago,
    load_settings,
    pending_settings,
)

BASE_DIR = Path(__file__).resolve().parent


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    """Crea y configura la instancia de Flask.

    ``overrides`` permite ajustar la configuración (usado por las pruebas
    automatizadas) antes de inicializar las extensiones.
    """
    load_dotenv()

    app = Flask(__name__, instance_path=str(INSTANCE_DIR), instance_relative_config=False)
    app.config.from_object(get_config(config_name))
    if overrides:
        app.config.update(overrides)

    _configure_logging(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_template_helpers(app)
    _register_hooks(app)

    from .cli import register_cli

    register_cli(app)

    app.logger.info(
        "Plataforma Nueva Canaán iniciada (entorno=%s, depuración=%s)",
        os.getenv("FLASK_ENV", "development"),
        app.config["DEBUG"],
    )
    # Deja constancia en los logs de Render de qué base de datos se está usando
    # (SQLite efímero o PostgreSQL de Supabase), sin mostrar la contraseña.
    app.logger.info(
        "Base de datos en uso: %s",
        mask_database_uri(app.config["SQLALCHEMY_DATABASE_URI"]),
    )
    return app


# ---------------------------------------------------------------------------
# Configuración interna
# ---------------------------------------------------------------------------
def _configure_logging(app: Flask) -> None:
    logging.basicConfig(
        level=logging.DEBUG if app.config["DEBUG"] else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # Los logs de producción se envían a la salida estándar (Render los captura).
    app.logger.setLevel(logging.DEBUG if app.config["DEBUG"] else logging.INFO)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return {"error": "Autenticación requerida"}, 401
        flash("Debe iniciar sesión para acceder a esta sección.", "warning")
        return redirect(url_for("auth.login", next=request.path))


def _register_blueprints(app: Flask) -> None:
    from .admin.routes import admin_bp
    from .announcements.routes import announcements_bp
    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .messages.routes import messages_bp
    from .news.routes import news_bp
    from .news_admin.routes import news_admin_bp
    from .parents.routes import parents_bp
    from .teachers.routes import teachers_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(announcements_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(parents_bp)
    app.register_blueprint(teachers_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(news_admin_bp)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        app.logger.warning("CSRF rechazado en %s: %s", request.path, error.description)
        flash(
            "El formulario expiró o la solicitud no es válida. Vuelva a intentarlo.",
            "error",
        )
        return render_template("errors/400.html", reason=error.description), 400

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html", reason=None), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(error):
        limit = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        flash(f"El archivo enviado supera el límite permitido ({limit} MB).", "error")
        return render_template("errors/413.html", limit=limit), 413

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        app.logger.exception("Error interno no controlado: %s", error)
        return render_template("errors/500.html"), 500


def _register_template_helpers(app: Flask) -> None:
    """Filtros y variables disponibles en todas las plantillas Jinja2."""

    app.jinja_env.filters["date"] = format_date
    app.jinja_env.filters["datetime"] = format_datetime
    app.jinja_env.filters["longdate"] = format_long_date
    app.jinja_env.filters["shortdate"] = format_short_date
    app.jinja_env.filters["filesize"] = format_bytes
    app.jinja_env.filters["newsdate"] = format_news_datetime
    app.jinja_env.filters["timeago"] = format_time_ago

    @app.template_filter("nl2br")
    def nl2br(value):
        if not value:
            return ""
        return Markup("<br>".join(str(escape(value)).split("\n")))

    @app.template_filter("initials")
    def initials_filter(value):
        parts = [p for p in str(value or "").split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or "?"

    @app.context_processor
    def inject_globals():
        from .utils import SETTING_DEFAULTS

        settings = dict(SETTING_DEFAULTS)
        try:
            settings = load_settings()
            g.settings = settings
        except (OperationalError, ProgrammingError):
            # Base de datos aún no inicializada: se usan los valores base.
            db.session.rollback()
        except Exception:  # pragma: no cover - contexto degradado
            db.session.rollback()
            app.logger.exception("No se pudieron cargar los ajustes institucionales")

        unread_notifications = 0
        unread_messages = 0
        pending: list[str] = []
        if current_user.is_authenticated:
            try:
                unread_notifications = Notification.query.filter_by(
                    user_id=current_user.id, read_at=None
                ).count()
                unread_messages = Message.query.filter_by(
                    recipient_id=current_user.id, read_at=None
                ).count()
            except (OperationalError, ProgrammingError):
                db.session.rollback()
            if current_user.is_staff:
                pending = pending_settings(settings)

        return {
            "institution": settings,
            "current_year": date.today().year,
            "unread_notifications": unread_notifications,
            "unread_messages": unread_messages,
            "pending_institution_data": pending,
            "ROLE_LABELS": ROLE_LABELS,
            "ANNOUNCEMENT_CATEGORY_LABELS": ANNOUNCEMENT_CATEGORY_LABELS,
            "ANNOUNCEMENT_STATUS_LABELS": ANNOUNCEMENT_STATUS_LABELS,
            "PRIORITY_LABELS": PRIORITY_LABELS,
            "EVENT_CATEGORY_LABELS": EVENT_CATEGORY_LABELS,
            "ATTENDANCE_STATUS_LABELS": ATTENDANCE_STATUS_LABELS,
            "ASSIGNMENT_KIND_LABELS": ASSIGNMENT_KIND_LABELS,
            "AUDIENCE_LABELS": AUDIENCE_LABELS,
            "ENROLLMENT_STATUS_LABELS": ENROLLMENT_STATUS_LABELS,
            "NEWS_CATEGORY_LABELS": NEWS_CATEGORY_LABELS,
            "NEWS_STATUS_LABELS": NEWS_STATUS_LABELS,
            "NEWS_COMMENT_STATUS_LABELS": NEWS_COMMENT_STATUS_LABELS,
        }


def _register_hooks(app: Flask) -> None:
    from flask import session

    @app.before_request
    def enforce_active_user():
        session.permanent = True
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            flash("Su cuenta está desactivada. Comuníquese con la institución.", "error")

    @app.after_request
    def security_headers(response):
        for header, value in app.config["SECURITY_HEADERS"].items():
            response.headers.setdefault(header, value)
        if current_user.is_authenticated:
            response.headers.setdefault("Cache-Control", "no-store, max-age=0")
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

