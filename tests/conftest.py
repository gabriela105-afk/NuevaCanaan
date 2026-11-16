"""Configuración común de las pruebas (pytest)."""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db
from app.models import Admin

TEST_PASSWORD = "clave-solo-para-pruebas-123"
TEST_EMAIL = "admin@test.local"


@pytest.fixture()
def app(tmp_path):
    """Aplicación con base SQLite temporal y una cuenta administradora."""
    application = create_app(
        "testing",
        overrides={
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "WTF_CSRF_ENABLED": False,
            "SERVER_NAME": "localhost",
            "PREFERRED_URL_SCHEME": "http",
            "SECRET_KEY": "clave-de-pruebas",
        },
    )

    with application.app_context():
        db.create_all()
        admin = Admin(email=TEST_EMAIL, name="Admin de Pruebas")
        admin.set_password(TEST_PASSWORD)
        db.session.add(admin)
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth_client(client):
    """Cliente con la sesión del administrador ya iniciada."""
    response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 302
    return client
