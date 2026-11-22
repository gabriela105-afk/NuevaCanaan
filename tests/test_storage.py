"""Pruebas del almacenamiento Supabase y de la migración de columnas."""

from __future__ import annotations

import base64
import io

import pytest
from sqlalchemy import inspect, text

from app import storage
from app.extensions import db
from app.models import PostImage
from app.schema import ensure_schema

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z4QAAAABJRU5ErkJggg=="
)

SUPABASE_CONFIG = {
    "STORAGE_BACKEND": "supabase",
    "SUPABASE_URL": "https://proyecto.supabase.co",
    "SUPABASE_SERVICE_KEY": "clave-de-prueba",
    "SUPABASE_STORAGE_BUCKET": "nueva-canaan",
    "SUPABASE_STORAGE_PREFIX": "",
    "SUPABASE_STORAGE_PUBLIC": True,
    "SUPABASE_TIMEOUT": 5,
}


def test_supabase_upload_uses_bucket_and_stores_relative_path(app, monkeypatch):
    calls = []

    def fake_request(method, url, headers=None, data=None, timeout=None):
        calls.append({"method": method, "url": url, "headers": headers, "data": data})
        return 200, b"{}"

    monkeypatch.setattr(storage, "_http_request", fake_request)

    with app.app_context():
        app.config.update(SUPABASE_CONFIG)
        stored = storage.store_bytes(
            PNG_BYTES, "foto escolar.png", "posts", "image/png", extension="png"
        )

    assert stored.storage == "supabase"
    assert stored.path.startswith("posts/foto_escolar-")
    assert stored.path.endswith(".png")
    assert stored.url == (
        "https://proyecto.supabase.co/storage/v1/object/public/"
        f"nueva-canaan/{stored.path}"
    )
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == (
        "https://proyecto.supabase.co/storage/v1/object/"
        f"nueva-canaan/{stored.path}"
    )
    assert calls[0]["headers"]["Authorization"] == "Bearer clave-de-prueba"
    assert calls[0]["headers"]["apikey"] == "clave-de-prueba"
    assert calls[0]["data"] == PNG_BYTES


@pytest.mark.parametrize(
    ("configured_url", "expected_base"),
    [
        ("https://proyecto.supabase.co", "https://proyecto.supabase.co"),
        ("https://proyecto.supabase.co/", "https://proyecto.supabase.co"),
        ("https://proyecto.supabase.co/rest/v1", "https://proyecto.supabase.co"),
        ("https://proyecto.supabase.co/rest/v1/", "https://proyecto.supabase.co"),
        (
            "https://proyecto.supabase.co/storage/v1/object",
            "https://proyecto.supabase.co",
        ),
        (
            "https://api.example.com/supabase",
            "https://api.example.com/supabase",
        ),
    ],
)
def test_supabase_url_is_normalized_to_project_root(configured_url, expected_base):
    assert storage._normalize_supabase_url(configured_url) == expected_base


def test_invalid_supabase_url_reports_a_clear_error():
    with pytest.raises(storage.StorageError, match="no es una URL válida"):
        storage._normalize_supabase_url("proyecto.supabase.co")


@pytest.mark.parametrize(
    "configured_url",
    [
        "https://proyecto.supabase.co/rest/v1",
        "https://proyecto.supabase.co/rest/v1/",
        "https://proyecto.supabase.co/storage/v1",
    ],
)
def test_upload_url_ignores_api_suffix_in_supabase_url(
    app, monkeypatch, configured_url
):
    calls = []

    def fake_request(method, url, headers=None, data=None, timeout=None):
        calls.append({"method": method, "url": url})
        return 200, b"{}"

    monkeypatch.setattr(storage, "_http_request", fake_request)

    with app.app_context():
        app.config.update(SUPABASE_CONFIG)
        app.config["SUPABASE_URL"] = configured_url
        stored = storage.store_bytes(
            PNG_BYTES, "foto.png", "posts", "image/png", extension="png"
        )

    assert calls[0]["url"] == (
        "https://proyecto.supabase.co/storage/v1/object/"
        f"nueva-canaan/{stored.path}"
    )
    assert stored.url == (
        "https://proyecto.supabase.co/storage/v1/object/public/"
        f"nueva-canaan/{stored.path}"
    )


def test_bucket_name_is_stripped_of_surrounding_slashes(app, monkeypatch):
    calls = []

    def fake_request(method, url, headers=None, data=None, timeout=None):
        calls.append({"method": method, "url": url})
        return 200, b"{}"

    monkeypatch.setattr(storage, "_http_request", fake_request)

    with app.app_context():
        app.config.update(SUPABASE_CONFIG)
        app.config["SUPABASE_STORAGE_BUCKET"] = "/nueva-canaan/"
        stored = storage.store_bytes(
            PNG_BYTES, "foto.png", "posts", "image/png", extension="png"
        )

    assert calls[0]["url"] == (
        "https://proyecto.supabase.co/storage/v1/object/"
        f"nueva-canaan/{stored.path}"
    )


def test_private_bucket_stores_no_public_url_and_signs_on_display(app, monkeypatch):
    calls = []

    def fake_request(method, url, headers=None, data=None, timeout=None):
        calls.append({"method": method, "url": url})
        if "/object/sign/" in url:
            signed_path = url.split("/object/sign/", 1)[1]
            payload = (
                '{"signedURL":"/object/sign/'
                + signed_path
                + '?token=token-de-prueba"}'
            ).encode("utf-8")
            return 200, payload
        return 200, b"{}"

    monkeypatch.setattr(storage, "_http_request", fake_request)

    with app.app_context():
        app.config.update(SUPABASE_CONFIG)
        app.config["SUPABASE_STORAGE_PUBLIC"] = False
        stored = storage.store_bytes(
            PNG_BYTES, "foto.png", "posts", "image/png", extension="png"
        )
        assert stored.url is None
        url = storage.display_url(stored.storage, stored.path)

    assert url == (
        "https://proyecto.supabase.co/storage/v1/object/sign/nueva-canaan/"
        f"{stored.path}?token=token-de-prueba"
    )
    assert calls[-1]["method"] == "POST"
    assert calls[-1]["url"] == (
        "https://proyecto.supabase.co/storage/v1/object/sign/"
        f"nueva-canaan/{stored.path}"
    )


def test_supabase_error_is_reported_instead_of_saving_locally(app, monkeypatch):
    def fake_request(method, url, headers=None, data=None, timeout=None):
        return 400, b'{"message":"Bucket not found"}'

    monkeypatch.setattr(storage, "_http_request", fake_request)

    with app.app_context():
        app.config.update(SUPABASE_CONFIG)
        with pytest.raises(storage.StorageError, match="Bucket not found"):
            storage.store_bytes(PNG_BYTES, "foto.png", "posts", "image/png")


def test_postgrest_invalid_path_error_explains_url_configuration(app, monkeypatch):
    def fake_request(method, url, headers=None, data=None, timeout=None):
        return (
            400,
            b'{"code":"PGRST125","message":"Invalid path specified in request URL"}',
        )

    monkeypatch.setattr(storage, "_http_request", fake_request)

    with app.app_context():
        app.config.update(SUPABASE_CONFIG)
        with pytest.raises(storage.StorageError, match="sin /rest/v1"):
            storage.store_bytes(PNG_BYTES, "foto.png", "posts", "image/png")


def test_publish_stores_supabase_metadata_and_image_redirects(
    auth_client, app, monkeypatch
):
    def fake_request(method, url, headers=None, data=None, timeout=None):
        return 200, b"{}"

    monkeypatch.setattr(storage, "_http_request", fake_request)

    with app.app_context():
        app.config.update(SUPABASE_CONFIG)

    response = auth_client.post(
        "/publicar",
        data={
            "body": "Noticia con fotografía permanente",
            "photos": (io.BytesIO(PNG_BYTES), "portada.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Publicación creada correctamente" in response.get_data(as_text=True)

    with app.app_context():
        image = PostImage.query.one()
        assert image.storage == "supabase"
        assert image.path.startswith("posts/portada-")
        assert image.url.startswith(
            "https://proyecto.supabase.co/storage/v1/object/public/nueva-canaan/"
        )
        assert image.is_available is True
        image_id = image.id

    redirect_response = auth_client.get(f"/imagenes/{image_id}")
    assert redirect_response.status_code == 302
    assert redirect_response.headers["Location"] == image.url


def test_ensure_schema_adds_columns_without_deleting_existing_rows(app):
    with app.app_context():
        db.drop_all()
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE post_images ("
                    "id INTEGER PRIMARY KEY, "
                    "post_id INTEGER NOT NULL, "
                    "path VARCHAR(255) NOT NULL, "
                    "name VARCHAR(255), "
                    "mime VARCHAR(120), "
                    "size INTEGER, "
                    "position INTEGER NOT NULL DEFAULT 0, "
                    "created_at DATETIME NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO post_images "
                    "(id, post_id, path, position, created_at) "
                    "VALUES (1, 1, 'posts/antigua.jpg', 0, CURRENT_TIMESTAMP)"
                )
            )

        additions = ensure_schema()
        assert set(additions) == {"storage", "url"}

        columns = {c["name"] for c in inspect(db.engine).get_columns("post_images")}
        assert {"storage", "url"} <= columns
        row = db.session.execute(
            text("SELECT path, storage FROM post_images WHERE id = 1")
        ).one()
        assert row.path == "posts/antigua.jpg"
        assert row.storage == "local"
