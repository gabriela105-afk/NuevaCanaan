"""Almacenamiento permanente de archivos institucionales.

En producción las fotografías se guardan en **Supabase Storage** porque el
sistema de archivos de Render es efímero: se borra en cada despliegue, reinicio
o suspensión del servicio gratuito. En desarrollo, cuando no hay credenciales,
se usa ``UPLOAD_FOLDER`` (comportamiento histórico).

La base de datos guarda siempre ``storage`` (``supabase`` o ``local``), la ruta
interna (``path``) y, cuando el bucket es público, la URL de lectura (``url``).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from flask import current_app
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

STORAGE_SUPABASE = "supabase"
STORAGE_LOCAL = "local"


class StorageError(RuntimeError):
    """Configuración incompleta o error de comunicación con el almacenamiento."""


@dataclass(frozen=True)
class StoredFile:
    """Resultado de guardar un archivo (listo para la base de datos)."""

    storage: str
    path: str
    url: str | None
    name: str
    mime: str
    size: int
    extension: str

    def as_metadata(self) -> dict:
        return {
            "storage": self.storage,
            "path": self.path,
            "url": self.url,
            "name": self.name,
            "mime": self.mime,
            "size": self.size,
            "extension": self.extension,
        }


def _config(key: str, default=None):
    return current_app.config.get(key, default)


def supabase_configured() -> bool:
    """¿Están definidas la URL, la clave y el bucket de Supabase?"""
    return bool(
        _config("SUPABASE_URL")
        and _config("SUPABASE_SERVICE_KEY")
        and _config("SUPABASE_STORAGE_BUCKET")
    )


def active_backend() -> str:
    """Backend efectivo: ``supabase`` o ``local``."""
    configured = str(_config("STORAGE_BACKEND", "auto") or "auto").strip().lower()
    if configured == STORAGE_LOCAL:
        return STORAGE_LOCAL
    if configured == STORAGE_SUPABASE:
        return STORAGE_SUPABASE
    return STORAGE_SUPABASE if supabase_configured() else STORAGE_LOCAL


def _supabase_credentials() -> tuple[str, str, str]:
    if not supabase_configured():
        raise StorageError(
            "Supabase Storage no está configurado. Defina SUPABASE_URL, "
            "SUPABASE_SERVICE_KEY y SUPABASE_STORAGE_BUCKET (ver .env.example)."
        )
    base = str(_config("SUPABASE_URL")).rstrip("/")
    key = str(_config("SUPABASE_SERVICE_KEY"))
    bucket = str(_config("SUPABASE_STORAGE_BUCKET"))
    if not bucket:
        raise StorageError("SUPABASE_STORAGE_BUCKET está vacío.")
    return base, key, bucket


def _object_name(path: str) -> str:
    """Ruta interna dentro del bucket (incluye el prefijo configurado)."""
    prefix = str(_config("SUPABASE_STORAGE_PREFIX", "") or "").strip("/")
    clean_path = str(path or "").strip("/")
    return f"{prefix}/{clean_path}" if prefix else clean_path


def _quote(value: str) -> str:
    return urlparse.quote(value, safe="/")


def public_url(path: str) -> str:
    """URL pública de lectura del objeto (requiere bucket público)."""
    base, _key, bucket = _supabase_credentials()
    return (
        f"{base}/storage/v1/object/public/{_quote(bucket)}/"
        f"{_quote(_object_name(path))}"
    )


def _http_request(method: str, url: str, headers: dict | None = None,
                  data: bytes | None = None, timeout: int | None = None):
    """Ejecuta una petición HTTP y devuelve ``(status, body)``.

    Los errores HTTP se devuelven como respuesta para que el llamador decida;
    los errores de red se convierten en :class:`StorageError`.
    """
    request = urlrequest.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlrequest.urlopen(
            request, timeout=timeout or int(_config("SUPABASE_TIMEOUT", 20))
        ) as response:
            return response.status, response.read()
    except urlerror.HTTPError as error:
        return error.code, error.read()
    except (urlerror.URLError, TimeoutError, OSError) as error:
        raise StorageError(f"No se pudo conectar con Supabase Storage: {error}") from error


def _error_message(body: bytes, status: int) -> str:
    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        text = body.decode("utf-8", "replace").strip()
        return text[:300] or f"Supabase Storage respondió HTTP {status}."
    if isinstance(payload, dict):
        return str(
            payload.get("message")
            or payload.get("error")
            or payload.get("statusCode")
            or f"HTTP {status}"
        )[:300]
    return f"Supabase Storage respondió HTTP {status}."


def _auth_headers(extra: dict | None = None) -> dict:
    _base, key, _bucket = _supabase_credentials()
    headers = {"Authorization": f"Bearer {key}", "apikey": key}
    if extra:
        headers.update(extra)
    return headers


def store_bytes(data: bytes, filename: str, subfolder: str, mime: str,
                extension: str | None = None) -> StoredFile:
    """Guarda ``data`` en el backend activo y devuelve sus metadatos."""
    if not data:
        raise StorageError("El archivo está vacío.")

    display_name = (filename or "archivo").strip()[:255]
    ext = (extension or "").strip().lower()
    if not ext and "." in display_name:
        ext = display_name.rsplit(".", 1)[1].lower()
    ext = ext or "bin"

    safe_base = secure_filename(display_name.rsplit(".", 1)[0])[:40] or "archivo"
    stored_name = f"{safe_base}-{uuid.uuid4().hex[:10]}.{ext}"
    relative_path = f"{subfolder.strip('/')}/{stored_name}" if subfolder else stored_name

    if active_backend() == STORAGE_LOCAL:
        target = local_file(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        logger.info("Archivo guardado localmente: %s", relative_path)
        return StoredFile(
            storage=STORAGE_LOCAL,
            path=relative_path,
            url=None,
            name=display_name,
            mime=mime,
            size=len(data),
            extension=ext,
        )

    base, _key, bucket = _supabase_credentials()
    object_name = _object_name(relative_path)
    endpoint = f"{base}/storage/v1/object/{_quote(bucket)}/{_quote(object_name)}"
    status, body = _http_request(
        "POST",
        endpoint,
        headers=_auth_headers(
            {
                "Content-Type": mime or "application/octet-stream",
                "Cache-Control": "public, max-age=31536000",
                "x-upsert": "true",
            }
        ),
        data=data,
    )
    if status not in (200, 201):
        raise StorageError(
            "No se pudo subir la fotografía a Supabase Storage: "
            f"{_error_message(body, status)}"
        )

    is_public = bool(_config("SUPABASE_STORAGE_PUBLIC", True))
    url = public_url(relative_path) if is_public else None
    logger.info("Archivo guardado en Supabase Storage: %s", object_name)
    return StoredFile(
        storage=STORAGE_SUPABASE,
        path=relative_path,
        url=url,
        name=display_name,
        mime=mime,
        size=len(data),
        extension=ext,
    )


def delete_object(storage: str | None, path: str | None) -> None:
    """Elimina un archivo del backend indicado (tolera archivos ya ausentes)."""
    if not path:
        return
    if (storage or STORAGE_LOCAL) == STORAGE_LOCAL:
        try:
            target = local_file(path)
        except ValueError:
            logger.warning("Ruta local no válida al eliminar: %s", path)
            return
        try:
            if target.is_file():
                target.unlink()
        except OSError:  # pragma: no cover - disco no disponible
            logger.warning("No se pudo borrar el archivo local %s", path)
        return

    try:
        base, _key, bucket = _supabase_credentials()
    except StorageError:
        logger.warning("No se puede borrar en Supabase (sin credenciales): %s", path)
        return
    endpoint = f"{base}/storage/v1/object/{_quote(bucket)}/{_quote(_object_name(path))}"
    try:
        status, body = _http_request("DELETE", endpoint, headers=_auth_headers())
    except StorageError:  # pragma: no cover - red no disponible
        logger.warning("No se pudo borrar el objeto remoto %s", path)
        return
    if status not in (200, 204, 404):
        logger.warning(
            "Supabase no eliminó %s: %s", path, _error_message(body, status)
        )


def signed_url(path: str, expires_in: int = 3600) -> str | None:
    """URL firmada para buckets privados."""
    try:
        base, _key, bucket = _supabase_credentials()
    except StorageError:
        return None
    endpoint = (
        f"{base}/storage/v1/object/sign/{_quote(bucket)}/"
        f"{_quote(_object_name(path))}"
    )
    body = json.dumps({"expiresIn": max(60, int(expires_in))}).encode("utf-8")
    status, payload = _http_request(
        "POST",
        endpoint,
        headers=_auth_headers({"Content-Type": "application/json"}),
        data=body,
    )
    if status not in (200, 201):
        logger.warning(
            "No se pudo firmar la URL de %s: %s", path, _error_message(payload, status)
        )
        return None
    try:
        signed = json.loads(payload.decode("utf-8", "replace"))
    except ValueError:
        return None
    relative = signed.get("signedURL") or signed.get("signedUrl")
    if not relative:
        return None
    if relative.startswith("http"):
        return relative
    if relative.startswith("/storage/v1"):
        return f"{base}{relative}"
    return f"{base}/storage/v1/{relative.lstrip('/')}"


def display_url(storage: str | None, path: str | None, url: str | None = None,
                expires_in: int = 3600) -> str | None:
    """URL utilizable en el navegador (pública, firmada o ``None`` si es local)."""
    if not path:
        return None
    if (storage or STORAGE_LOCAL) != STORAGE_SUPABASE:
        return None
    if url:
        return url
    if bool(_config("SUPABASE_STORAGE_PUBLIC", True)):
        try:
            return public_url(path)
        except StorageError:
            return None
    return signed_url(path, expires_in)


def local_file(relative_path: str) -> Path:
    """Ruta absoluta dentro de ``UPLOAD_FOLDER``, protegida contra recorridos."""
    base = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (base / relative_path).resolve()
    if base != target and base not in target.parents:
        raise ValueError("Ruta de archivo no válida")
    return target


def storage_status() -> dict:
    """Diagnóstico del backend, sin exponer la clave de servicio."""
    backend = active_backend()
    status: dict = {
        "backend": backend,
        "configured": supabase_configured(),
        "bucket": _config("SUPABASE_STORAGE_BUCKET"),
        "prefix": _config("SUPABASE_STORAGE_PREFIX") or "",
        "public": bool(_config("SUPABASE_STORAGE_PUBLIC", True)),
        "probe": None,
    }
    if backend != STORAGE_SUPABASE:
        status["probe"] = "Se está usando el disco local (modo desarrollo)."
        return status

    try:
        base, _key, bucket = _supabase_credentials()
    except StorageError as error:
        status["probe"] = str(error)
        return status

    endpoint = f"{base}/storage/v1/bucket/{_quote(bucket)}"
    try:
        code, body = _http_request("GET", endpoint, headers=_auth_headers())
    except StorageError as error:
        status["probe"] = f"Error de red: {error}"
        return status
    if code == 200:
        status["probe"] = "Bucket accesible."
    elif code in (401, 403):
        status["probe"] = (
            "Credenciales rechazadas. Use la clave «service_role» del proyecto."
        )
    elif code == 404:
        status["probe"] = (
            f"El bucket «{bucket}» no existe. Créelo en Supabase → Storage."
        )
    else:
        status["probe"] = _error_message(body, code)
    return status
