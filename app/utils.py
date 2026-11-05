"""Utilidades transversales: autorización, validación, archivos y avisos."""

from __future__ import annotations

import os
import re
import uuid
from datetime import date, datetime, time, timedelta
from functools import wraps
from pathlib import Path

from flask import abort, current_app, flash, redirect, request, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from .extensions import db
from .models import (
    AuditLog,
    InstitutionSetting,
    Notification,
    User,
    utcnow,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

WEEKDAYS_ES = [
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
]


# ---------------------------------------------------------------------------
# Autorización
# ---------------------------------------------------------------------------
def role_required(*roles: str):
    """Restringe una vista a los roles indicados (verificado en el servidor)."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.full_path))
            if current_user.role not in roles:
                current_app.logger.warning(
                    "Acceso denegado: usuario=%s rol=%s ruta=%s",
                    current_user.id,
                    current_user.role,
                    request.path,
                )
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


staff_required = role_required("admin", "direction")
admin_required = role_required("admin")


def dashboard_url(user: User) -> str:
    """URL del panel correspondiente al rol del usuario."""
    return url_for(user.dashboard_endpoint)


def client_ip() -> str:
    """IP del cliente respetando el proxy de Render."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:60]
    return (request.remote_addr or "")[:60]


# ---------------------------------------------------------------------------
# Limpieza y validación de datos
# ---------------------------------------------------------------------------
def clean(value, max_length: int | None = None, default: str = "") -> str:
    """Normaliza un campo de texto: recorta espacios y limita longitud."""
    if value is None:
        return default
    text = str(value).replace("\x00", "").strip()
    if max_length:
        text = text[:max_length]
    return text or default


def clean_multiline(value, max_length: int | None = None) -> str:
    """Igual que ``clean`` pero conserva saltos de línea."""
    if value is None:
        return ""
    text = str(value).replace("\x00", "").replace("\r\n", "\n").strip()
    if max_length:
        text = text[:max_length]
    return text


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value or ""))


def validate_password(password: str, confirmation: str) -> list[str]:
    """Reglas mínimas de contraseña. Devuelve la lista de errores."""
    errors: list[str] = []
    minimum = current_app.config.get("PASSWORD_MIN_LENGTH", 8)
    maximum = current_app.config.get("PASSWORD_MAX_LENGTH", 128)
    if not password:
        errors.append("La contraseña es obligatoria.")
        return errors
    if len(password) < minimum:
        errors.append(f"La contraseña debe tener al menos {minimum} caracteres.")
    if len(password) > maximum:
        errors.append(f"La contraseña no puede superar {maximum} caracteres.")
    if password != confirmation:
        errors.append("Las contraseñas no coinciden.")
    if password and password.strip().lower() in {"12345678", "password", "contrasena"}:
        errors.append("La contraseña es demasiado débil, elija otra.")
    return errors


def parse_date(value: str | None, field: str = "fecha") -> tuple[date | None, str | None]:
    """Convierte 'YYYY-MM-DD' en fecha. Devuelve (valor, error)."""
    if not value:
        return None, None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date(), None
    except ValueError:
        return None, f"El campo {field} no tiene un formato válido (AAAA-MM-DD)."


def parse_time(value: str | None) -> tuple[time | None, str | None]:
    if not value:
        return None, None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).time(), None
        except ValueError:
            continue
    return None, "La hora no tiene un formato válido (HH:MM)."


def parse_float(value, field: str = "número") -> tuple[float | None, str | None]:
    if value in (None, ""):
        return None, None
    try:
        return float(str(value).replace(",", ".")), None
    except ValueError:
        return None, f"El campo {field} debe ser numérico."


def parse_int(value, field: str = "número") -> tuple[int | None, str | None]:
    if value in (None, ""):
        return None, None
    try:
        return int(str(value)), None
    except ValueError:
        return None, f"El campo {field} debe ser un número entero."


def choices(value: str, allowed, fallback: str | None = None) -> str | None:
    """Devuelve ``value`` si pertenece a ``allowed``; si no, ``fallback``."""
    return value if value in allowed else fallback


# ---------------------------------------------------------------------------
# Archivos subidos
# ---------------------------------------------------------------------------
def allowed_extension(filename: str, allowed) -> bool:
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in allowed


def save_upload(file_storage, subfolder: str = "announcements"):
    """Valida y guarda un archivo subido con nombre aleatorio y seguro.

    Devuelve ``(metadata, error)``. ``metadata`` contiene ``path`` (relativa a
    UPLOAD_FOLDER), ``name``, ``mime`` y ``size``.
    """
    if file_storage is None or not file_storage.filename:
        return None, None

    allowed = current_app.config["ALLOWED_ATTACHMENT_EXTENSIONS"]
    display_name = clean(file_storage.filename, 255)
    if not allowed_extension(display_name, allowed):
        return None, "Formato de archivo no permitido. Use PDF, imágenes, DOCX, XLSX o TXT."

    max_bytes = current_app.config["MAX_ATTACHMENT_MB"] * 1024 * 1024
    data = file_storage.read()
    if not data:
        return None, "El archivo está vacío."
    if len(data) > max_bytes:
        return None, (
            "El archivo supera el tamaño máximo permitido "
            f"({current_app.config['MAX_ATTACHMENT_MB']} MB)."
        )

    extension = display_name.rsplit(".", 1)[1].lower()
    safe_base = secure_filename(display_name.rsplit(".", 1)[0])[:40] or "archivo"
    stored_name = f"{safe_base}-{uuid.uuid4().hex[:10]}.{extension}"

    folder = Path(current_app.config["UPLOAD_FOLDER"]) / subfolder
    folder.mkdir(parents=True, exist_ok=True)
    (folder / stored_name).write_bytes(data)

    return (
        {
            "path": f"{subfolder}/{stored_name}",
            "name": display_name,
            "mime": file_storage.mimetype or "application/octet-stream",
            "size": len(data),
        },
        None,
    )


def upload_path(relative_path: str) -> Path:
    """Ruta absoluta dentro de UPLOAD_FOLDER, protegida contra recorridos."""
    base = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (base / relative_path).resolve()
    if base != target and base not in target.parents:
        raise ValueError("Ruta de archivo no válida")
    return target


def delete_upload(relative_path: str | None) -> None:
    if not relative_path:
        return
    try:
        path = upload_path(relative_path)
        if path.is_file():
            path.unlink()
    except (ValueError, OSError):  # pragma: no cover - tolerante a fallos de disco
        current_app.logger.warning("No se pudo borrar el archivo %s", relative_path)


def _image_format(data: bytes) -> str | None:
    """Detecta el formato real de una imagen por su firma binaria."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def save_image_upload(file_storage, subfolder: str = "noticias"):
    """Valida y guarda una fotografía subida desde el panel.

    Comprueba la extensión, el tamaño y la firma binaria del archivo (sin
    dependencias externas como Pillow). Devuelve ``(metadata, error)`` con la
    misma estructura que :func:`save_upload`.
    """
    if file_storage is None or not file_storage.filename:
        return None, None

    display_name = clean(file_storage.filename, 255)
    if not allowed_extension(display_name, current_app.config["ALLOWED_IMAGE_EXTENSIONS"]):
        return None, "Formato de imagen no permitido. Use PNG, JPG o WEBP."

    max_mb = current_app.config["MAX_ATTACHMENT_MB"]
    data = file_storage.read()
    if not data:
        return None, "La imagen está vacía."
    if len(data) > max_mb * 1024 * 1024:
        return None, f"La imagen supera el tamaño máximo permitido ({max_mb} MB)."

    detected = _image_format(data)
    if detected is None:
        return None, "El archivo no parece una imagen válida (PNG, JPG o WEBP)."

    extension = "jpg" if detected == "jpeg" else detected
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "webp": "image/webp",
    }[extension]

    safe_base = secure_filename(display_name.rsplit(".", 1)[0])[:40] or "foto"
    stored_name = f"{safe_base}-{uuid.uuid4().hex[:10]}.{extension}"

    folder = Path(current_app.config["UPLOAD_FOLDER"]) / subfolder
    folder.mkdir(parents=True, exist_ok=True)
    (folder / stored_name).write_bytes(data)

    return (
        {
            "path": f"{subfolder}/{stored_name}",
            "name": display_name,
            "mime": mime,
            "size": len(data),
            "extension": extension,
        },
        None,
    )


# ---------------------------------------------------------------------------
# Notificaciones internas
# ---------------------------------------------------------------------------
def notify(target_user, title: str, body: str = "", link: str | None = None,
           category: str = "general") -> None:
    """Crea una notificación interna para un usuario."""
    if target_user is None:
        return
    db.session.add(
        Notification(
            user_id=target_user.id,
            title=clean(title, 180, "Notificación"),
            body=clean_multiline(body, 400) or None,
            link=(link or "")[:255] or None,
            category=category,
        )
    )


def notify_many(users, title: str, body: str = "", link: str | None = None,
                category: str = "general") -> int:
    count = 0
    for user in users:
        notify(user, title, body, link, category)
        count += 1
    return count


def notify_announcement(announcement) -> int:
    """Notifica a los usuarios que pueden ver un comunicado recién publicado."""
    link = url_for("announcements.detail", announcement_id=announcement.id)
    body = announcement.summary or (
        announcement.body[:200] + "…" if len(announcement.body) > 200 else announcement.body
    )
    total = 0
    for user in User.query.filter(User.is_active.is_(True)).all():
        if user.is_staff:
            continue
        if announcement.is_visible_to(user):
            notify(
                user,
                f"Nuevo comunicado: {announcement.title}",
                body,
                link,
                category="announcement",
            )
            total += 1
    return total


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------
def record_audit(action: str, entity: str | None = None, entity_id: int | None = None,
                 details: str | None = None) -> None:
    """Añade un registro de auditoría a la sesión (no hace commit)."""
    actor_id = current_user.id if current_user.is_authenticated else None
    actor_name = current_user.full_name if current_user.is_authenticated else None
    db.session.add(
        AuditLog(
            actor_id=actor_id,
            actor_name=(actor_name or "")[:160] or None,
            action=clean(action, 80, "accion"),
            entity=clean(entity, 60)[:60] or None,
            entity_id=entity_id,
            details=clean_multiline(details, 400) or None,
            ip_address=client_ip(),
        )
    )


# ---------------------------------------------------------------------------
# Formato de fechas y textos
# ---------------------------------------------------------------------------
def format_date(value, fmt: str = "%d/%m/%Y") -> str:
    return value.strftime(fmt) if value else ""


def format_datetime(value, fmt: str = "%d/%m/%Y %H:%M") -> str:
    return value.strftime(fmt) if value else ""


def format_long_date(value) -> str:
    if not value:
        return ""
    return f"{value.day} de {MONTHS_ES[value.month - 1]} de {value.year}"


def format_short_date(value) -> str:
    if not value:
        return ""
    return f"{value.day:02d} {MONTHS_ES[value.month - 1][:3].capitalize()} {value.year}"


def format_bytes(size: int | None) -> str:
    if not size:
        return "—"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


# ---------------------------------------------------------------------------
# Fechas locales de NUEVA CANAÁN NOTICIAS
# ---------------------------------------------------------------------------
def local_datetime(value):
    """Convierte una fecha UTC almacenada a la hora local institucional.

    El desfase se configura con ``UTC_OFFSET_HOURS`` (por defecto -4, hora de
    Bolivia). Se evita ``zoneinfo`` para no exigir la base de datos de zonas
    horarias en Windows ni en Render.
    """
    if value is None:
        return None
    try:
        offset = int(current_app.config.get("UTC_OFFSET_HOURS", -4))
    except (TypeError, ValueError):  # pragma: no cover - configuración inválida
        offset = -4
    return value + timedelta(hours=offset)


def format_news_datetime(value) -> str:
    """Ej.: ``5 de noviembre de 2026 · 10:32``."""
    local = local_datetime(value)
    if local is None:
        return ""
    return f"{local.day} de {MONTHS_ES[local.month - 1]} de {local.year} · {local:%H:%M}"


def format_time_ago(value) -> str:
    """Texto relativo para las tarjetas del muro (``Hace 5 minutos``)."""
    if value is None:
        return ""
    seconds = int((datetime.utcnow() - value).total_seconds())
    if seconds < 60:
        return "Hace un momento"
    minutes = seconds // 60
    if minutes < 60:
        return f"Hace {minutes} minuto{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    if hours < 24:
        return f"Hace {hours} hora{'s' if hours != 1 else ''}"
    days = hours // 24
    if days == 1:
        return "Ayer"
    if days < 7:
        return f"Hace {days} días"
    return format_news_datetime(value).split(" · ")[0]


# ---------------------------------------------------------------------------
# Ajustes institucionales
# ---------------------------------------------------------------------------
SETTING_DEFAULTS: dict[str, str] = {
    "nombre_colegio": "Colegio Técnico Humanístico Nueva Canaán",
    "lema": "",
    "mensaje_bienvenida": (
        "Bienvenidos a la plataforma digital del Colegio Técnico Humanístico "
        "Nueva Canaán, un espacio de comunicación entre la institución y las familias."
    ),
    "presentacion": "",
    "mision": "",
    "vision": "",
    "historia": "",
    "valores": "",
    "direccion": "",
    "telefono": "",
    "telefono_alterno": "",
    "correo": "",
    "horario_atencion": "",
    "facebook": "",
    "instagram": "",
    "director": "",
    "nombre_portal": "Nueva Canaán Noticias",
    "portal_lema": "Noticias, actividades y logros de nuestra comunidad educativa",
    "nota_privacidad": (
        "Esta plataforma no publica listas de estudiantes, calificaciones ni datos "
        "personales. La información académica sólo está disponible para los tutores "
        "autorizados mediante credenciales personales."
    ),
}

SETTING_LABELS: dict[str, str] = {
    "nombre_colegio": "Nombre oficial del establecimiento",
    "lema": "Lema institucional",
    "mensaje_bienvenida": "Mensaje de bienvenida",
    "presentacion": "Presentación del establecimiento",
    "mision": "Misión",
    "vision": "Visión",
    "historia": "Reseña histórica",
    "valores": "Valores institucionales",
    "direccion": "Dirección",
    "telefono": "Teléfono",
    "telefono_alterno": "Teléfono alterno / WhatsApp institucional",
    "correo": "Correo electrónico institucional",
    "horario_atencion": "Horario de atención",
    "facebook": "Página de Facebook",
    "instagram": "Cuenta de Instagram",
    "director": "Autoridad máxima (nombre y cargo)",
    "nombre_portal": "Nombre del portal de noticias",
    "portal_lema": "Lema del portal de noticias",
    "nota_privacidad": "Nota de privacidad",
}

# Datos obligatorios que la institución debe completar desde el panel
REQUIRED_SETTINGS = ("direccion", "telefono", "correo", "horario_atencion")


def load_settings() -> dict[str, str]:
    """Ajustes institucionales combinados con los valores por defecto."""
    values = dict(SETTING_DEFAULTS)
    for row in InstitutionSetting.query.all():
        if row.value is not None:
            values[row.key] = row.value
    return values


def save_settings(data: dict[str, str]) -> None:
    for key in SETTING_DEFAULTS:
        if key in data:
            InstitutionSetting.set(key, clean_multiline(data.get(key), 4000))


def pending_settings(values: dict[str, str]) -> list[str]:
    """Etiquetas de los datos institucionales obligatorios aún vacíos."""
    return [SETTING_LABELS[k] for k in REQUIRED_SETTINGS if not values.get(k)]


# ---------------------------------------------------------------------------
# Galería institucional (archivos presentes en static/img/galeria)
# ---------------------------------------------------------------------------
GALLERY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


def gallery_images() -> list[dict]:
    """Lista las imágenes institucionales disponibles en la galería."""
    folder = Path(current_app.static_folder or "") / "img" / "galeria"
    if not folder.is_dir():
        return []
    items = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file() and path.suffix.lower() in GALLERY_EXTENSIONS:
            items.append(
                {
                    "filename": f"img/galeria/{path.name}",
                    "name": path.stem.replace("_", " ").replace("-", " ").capitalize(),
                }
            )
    return items


