"""Configuración central de la plataforma institucional Nueva Canaán.

Todos los valores sensibles se leen de variables de entorno.
Ver `.env.example` para el listado completo.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
    - Producción: PostgreSQL en Supabase mediante ``DATABASE_URL``.
    - También se admite un archivo SQLite en un disco persistente de Render,
      por ejemplo ``sqlite:////var/data/nueva_canaan.db``.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(INSTANCE_DIR / 'nueva_canaan.db').as_posix()}"
    return normalize_database_url(url)


# Driver de PostgreSQL usado por defecto (psycopg 3, ver requirements.txt).
POSTGRES_DRIVER = "psycopg"

# Parámetros de conexión que otros clientes (Prisma, PgBouncer, etc.) añaden a la
# URL y que el driver de Python no entiende.
_UNSUPPORTED_QUERY_KEYS = {"pgbouncer", "connection_limit", "pool_timeout", "schema"}

# Hosts que no usan TLS (desarrollo local).
_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "host.docker.internal"}


def is_postgres_uri(uri: str) -> bool:
    """Indica si la URI corresponde a PostgreSQL."""
    return (uri or "").strip().lower().startswith(("postgres://", "postgresql://"))


def normalize_database_url(url: str, default_driver: str = POSTGRES_DRIVER) -> str:
    """Normaliza una URL de base de datos para que SQLAlchemy la entienda.

    - ``postgres://`` (esquema antiguo de Render/Heroku) → ``postgresql+psycopg://``.
    - ``postgresql://`` sin driver → ``postgresql+<default_driver>://``.
    - Añade ``sslmode=require`` en hosts remotos como Supabase (se puede desactivar
      con la variable de entorno ``DATABASE_SSLMODE=disable``).
    - Elimina parámetros que sólo entienden otros clientes.

    Las URL que no son de PostgreSQL (por ejemplo SQLite) se devuelven sin cambios.
    """
    url = (url or "").strip()
    if not url or not is_postgres_uri(url):
        return url

    scheme, _, rest = url.partition("://")
    if "+" not in scheme:
        scheme = f"postgresql+{default_driver}"
    parts = urlsplit(f"{scheme}://{rest}")

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _UNSUPPORTED_QUERY_KEYS
    ]
    sslmode = (os.getenv("DATABASE_SSLMODE") or "require").strip().lower()
    has_ssl_option = any(key.lower() in {"sslmode", "ssl"} for key, _ in query)
    is_remote_host = (parts.hostname or "").lower() not in _LOCAL_HOSTS
    if not has_ssl_option and sslmode not in {"", "disable"} and is_remote_host:
        query.append(("sslmode", sslmode))

    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def mask_database_uri(uri: str) -> str:
    """Devuelve la URI sin la contraseña, para registros y mensajes de consola.

    Se usa al iniciar la aplicación: en los logs de Render queda constancia de a
    qué base de datos se está conectando, sin exponer la clave de Supabase.
    """
    uri = (uri or "").strip()
    if not uri:
        return "(sin definir)"
    scheme, separator, rest = uri.partition("://")
    if not separator or "@" not in rest:
        return uri
    credentials, _, host = rest.rpartition("@")
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


def _engine_options(uri: str) -> dict:
    """Opciones del motor de SQLAlchemy según el tipo de base de datos.

    En PostgreSQL se limita el tamaño del pool: Supabase (plan gratuito) cierra
    las conexiones inactivas y tiene un número máximo de clientes reducido.
    """
    if uri.startswith("sqlite"):
        return {"pool_pre_ping": True}

    options: dict = {
        "pool_pre_ping": True,
        "pool_recycle": _env_int("DB_POOL_RECYCLE", 280),
        "pool_size": _env_int("DB_POOL_SIZE", 4),
        "max_overflow": _env_int("DB_MAX_OVERFLOW", 2),
        "pool_timeout": _env_int("DB_POOL_TIMEOUT", 30),
    }
    if "+psycopg:" in uri and ":6543" in uri:
        # Puerto 6543 = "Transaction pooler" de Supabase: no admite sentencias
        # preparadas, así que se desactivan en el driver.
        options["connect_args"] = {"prepare_threshold": 0}
    return options


_DATABASE_URI = _database_uri()



class Config:
    """Configuración base compartida."""

    # --- Núcleo -------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion")
    DEBUG = False
    TESTING = False
    PREFERRED_URL_SCHEME = "https"

    # --- Base de datos ------------------------------------------------
    SQLALCHEMY_DATABASE_URI = _DATABASE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(_DATABASE_URI)

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

    # --- NUEVA CANAÁN NOTICIAS ------------------------------------------
    NEWS_PER_PAGE = _env_int("NEWS_PER_PAGE", 6)
    NEWS_COMMENTS_PER_PAGE = _env_int("NEWS_COMMENTS_PER_PAGE", 15)
    # Desfase horario usado para mostrar las fechas del muro (Bolivia = -4).
    UTC_OFFSET_HOURS = _env_int("UTC_OFFSET_HOURS", -4)

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
