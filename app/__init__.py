"""Fábrica de la aplicación Flask del muro institucional Nueva Canaán."""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

from flask import Flask, render_template, request
from flask_login import current_user

from config import INSTANCE_DIR, get_config, mask_database_uri

from .extensions import csrf, db, login_manager
from .models import Admin
from .routes import main
from .utils import format_datetime, format_time_ago


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    """Crea y configura la instancia de Flask.

    ``overrides`` permite ajustar la configuración en las pruebas antes de
    inicializar las extensiones.
    """
    app = Flask(
        __name__,
        instance_path=str(INSTANCE_DIR),
        instance_relative_config=False,
    )
    app.config.from_object(get_config(config_name))
    if overrides:
        app.config.update(overrides)

    _configure_logging(app)
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(Admin, int(user_id))
        except (TypeError, ValueError):
            return None

    app.register_blueprint(main)

    @app.template_filter("fecha")
    def fecha_filter(value):
        return format_datetime(value)

    @app.template_filter("timeago")
    def timeago_filter(value):
        return format_time_ago(value)

    @app.context_processor
    def inject_globals():
        return {
            "current_year": date.today().year,
            "institution_name": app.config["INSTITUTION_SHORT_NAME"],
        }

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def request_too_large(_error):
        max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return render_template("errors/413.html", max_mb=max_mb), 413

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

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

    from .cli import register_cli

    register_cli(app)

    app.logger.info(
        "Muro Nueva Canaán iniciado (entorno=%s, depuración=%s)",
        "producción" if os.getenv("RENDER") else "desarrollo",
        app.config["DEBUG"],
    )
    app.logger.info(
        "Base de datos en uso: %s",
        mask_database_uri(app.config["SQLALCHEMY_DATABASE_URI"]),
    )
    return app


def _configure_logging(app: Flask) -> None:
    logging.basicConfig(
        level=logging.DEBUG if app.config["DEBUG"] else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app.logger.setLevel(logging.DEBUG if app.config["DEBUG"] else logging.INFO)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
