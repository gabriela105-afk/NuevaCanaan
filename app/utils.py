"""Utilidades de texto, fechas y almacenamiento de fotografías."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import sleep

from flask import current_app
from werkzeug.utils import secure_filename

MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def clean(value, max_length: int | None = None, default: str = "") -> str:
    """Normaliza un campo de texto: recorta espacios y limita longitud."""
    if value is None:
        return default
    text = str(value).replace("\x00", "").strip()
    if max_length:
        text = text[:max_length]
    return text or default


def clean_multiline(value, max_length: int | None = None) -> str:
    """Igual que ``clean`` pero conserva los saltos de línea."""
    if value is None:
        return ""
    text = str(value).replace("\x00", "").replace("\r\n", "\n").strip()
    if max_length:
        text = text[:max_length]
    return text


def allowed_extension(filename: str, allowed) -> bool:
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in allowed


def upload_path(relative_path: str) -> Path:
    """Ruta absoluta dentro de UPLOAD_FOLDER, protegida contra recorridos."""
    base = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (base / relative_path).resolve()
    if base != target and base not in target.parents:
        raise ValueError("Ruta de archivo no válida")
    return target


def delete_upload(relative_path: str | None) -> None:
    """Borra una fotografía del disco sin propagar errores de archivo.

    En Windows el archivo puede estar bloqueado unos instantes si el navegador
    lo está descargando; se reintenta antes de registrar la advertencia.
    """
    if not relative_path:
        return
    try:
        path = upload_path(relative_path)
    except ValueError:  # pragma: no cover - ruta manipulada
        current_app.logger.warning("Ruta de archivo no válida: %s", relative_path)
        return
    for _ in range(4):
        try:
            if path.is_file():
                path.unlink()
            return
        except PermissionError:
            sleep(0.1)
        except OSError:  # pragma: no cover - tolerante a fallos de disco
            break
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


def save_image_upload(file_storage, subfolder: str = "posts"):
    """Valida y guarda una fotografía.

    Comprueba extensión, tamaño y firma binaria (sin Pillow). Devuelve
    ``(metadata, error)``; ``metadata`` contiene la ruta relativa a
    ``UPLOAD_FOLDER``, el nombre original, el MIME y el tamaño.
    """
    if file_storage is None or not file_storage.filename:
        return None, None

    display_name = clean(file_storage.filename, 255)
    if not allowed_extension(display_name, current_app.config["ALLOWED_IMAGE_EXTENSIONS"]):
        return None, "Formato no permitido. Use una imagen PNG, JPG o WEBP."

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


def local_datetime(value):
    """Convierte una fecha UTC almacenada a la hora local institucional."""
    if value is None:
        return None
    try:
        offset = int(current_app.config.get("UTC_OFFSET_HOURS", -4))
    except (TypeError, ValueError):  # pragma: no cover
        offset = -4
    return value + timedelta(hours=offset)


def format_datetime(value) -> str:
    """Ej.: ``16/11/2026 10:32`` en hora local."""
    local = local_datetime(value)
    return local.strftime("%d/%m/%Y %H:%M") if local else ""


def format_news_datetime(value) -> str:
    """Ej.: ``16 de noviembre de 2026 · 10:32``."""
    local = local_datetime(value)
    if local is None:
        return ""
    return f"{local.day} de {MONTHS_ES[local.month - 1]} de {local.year} · {local:%H:%M}"


def format_time_ago(value) -> str:
    """Texto relativo para las tarjetas del muro."""
    if value is None:
        return ""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seconds = int((now - value).total_seconds())
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
