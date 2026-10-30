"""Configuración central de la plataforma institucional Nueva Canaán.

Todos los valores sensibles se leen de variables de entorno.
Ver `.env.example` para el listado completo.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

# Las clases de configuración se evalúan al importar este módulo, por lo que el
# archivo `.env` debe cargarse antes de leer cualquier variable de entorno.
# (En Render las variables llegan por el entorno del proceso y esto no molesta.)
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _database_uri() -> str:
    """Devuelve la URI de base de datos configurada.

    - Local / por defecto: SQLite dentro de ``instance/`` (no versionado en Git).
    - Render: definir ``DATABASE_URL`` apuntando a la ruta del disco persistente,
      por ejemplo ``sqlite:////var/data/nueva_canaan.db``.
    - PostgreSQL: definir ``DATABASE_URL`` con el DSN provisto por el proveedor.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(INSTANCE_DIR / 'nueva_canaan.db').as_posix()}"
    # Render / Heroku entregan el esquema antiguo "postgres://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    """Configuración base compartida."""

    # --- Núcleo -------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion")
    DEBUG = False
    TESTING = False
    PREFERRED_URL_SCHEME = "https"

    # --- Base de datos ------------------------------------------------
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Sesiones y cookies -------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_env_int("SESSION_HOURS", 8))

    # --- CSRF / formularios --------------------------------------------
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # la sesión controla la expiración

    # --- Subidas de archivos -------------------------------------------
    MAX_CONTENT_LENGTH = _env_int("MAX_UPLOAD_MB", 8) * 1024 * 1024
    MAX_ATTACHMENT_MB = _env_int("MAX_ATTACHMENT_MB", 5)
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(INSTANCE_DIR / "uploads"))
    ALLOWED_ATTACHMENT_EXTENSIONS = {
        "pdf", "png", "jpg", "jpeg", "webp", "txt", "docx", "xlsx",
    }
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # --- Seguridad de acceso -------------------------------------------
    LOGIN_MAX_ATTEMPTS = _env_int("LOGIN_MAX_ATTEMPTS", 5)
    LOGIN_LOCK_MINUTES = _env_int("LOGIN_LOCK_MINUTES", 15)
    PASSWORD_MIN_LENGTH = _env_int("PASSWORD_MIN_LENGTH", 8)
    PASSWORD_MAX_LENGTH = 128

    # --- Identidad institucional (los textos viven en la BD) ------------
    INSTITUTION_NAME = "Colegio Técnico Humanístico Nueva Canaán"
    INSTITUTION_SHORT_NAME = "Nueva Canaán"
    INSTITUTION_LOGO = os.getenv("INSTITUTION_LOGO", "img/logo.svg")
    INSTITUTION_COVER = os.getenv("INSTITUTION_COVER", "img/portada.svg")
    INSTITUTION_FAVICON = os.getenv("INSTITUTION_FAVICON", "img/logo.svg")

    # --- Paginación -----------------------------------------------------
    ITEMS_PER_PAGE = _env_int("ITEMS_PER_PAGE", 10)

    # --- Correo (opcional, NO configurado por defecto) --------------------
    MAIL_ENABLED = _env_bool("MAIL_ENABLED", False)

    # --- Cabeceras de seguridad -----------------------------------------
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    }


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    # En producción las cookies sólo viajan por HTTPS (Render sirve HTTPS).
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    SERVER_NAME = "localhost"
    PREFERRED_URL_SCHEME = "http"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SECRET_KEY = "clave-solo-para-pruebas"


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config(name: str | None = None):
    """Devuelve la clase de configuración solicitada (o la del entorno)."""
    if name:
        return CONFIG_MAP.get(name, DevelopmentConfig)
    env_name = os.getenv("FLASK_ENV", "").strip().lower()
    if not env_name:
        env_name = "production" if os.getenv("RENDER") else "development"
    return CONFIG_MAP.get(env_name, DevelopmentConfig)
