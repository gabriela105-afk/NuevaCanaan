"""Pruebas de las páginas públicas y del formulario de contacto."""

from __future__ import annotations

from app.extensions import db
from app.models import ContactMessage


def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Nueva Canaán" in response.get_data(as_text=True)


def test_public_pages_load(client):
    for path in ("/institucion", "/galeria", "/calendario", "/comunicados", "/contacto", "/login"):
        response = client.get(path)
        assert response.status_code == 200, f"{path} devolvió {response.status_code}"


def test_announcement_list_shows_only_published(client):
    body = client.get("/comunicados").get_data(as_text=True)
    assert "Comunicado público de prueba" in body
    assert "Borrador interno de prueba" not in body


def test_draft_is_not_publicly_accessible(client):
    from app.models import Announcement

    with client.application.app_context():
        draft = Announcement.query.filter_by(status="draft").first()
        draft_id = draft.id
    assert client.get(f"/comunicados/{draft_id}").status_code == 404


def test_contact_form_rejects_invalid_data(app, client):
    with app.app_context():
        before = ContactMessage.query.count()
    response = client.post(
        "/contacto",
        data={"name": "A", "email": "no-es-correo", "subject": "x", "body": "corto"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assert ContactMessage.query.count() == before


def test_contact_form_stores_valid_message(app, client):
    response = client.post(
        "/contacto",
        data={
            "name": "Madre de Prueba",
            "email": "madre@test.local",
            "phone": "70000000",
            "subject": "Consulta sobre inscripciones",
            "body": "Necesito información sobre el proceso de inscripción del próximo año.",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "enviado correctamente" in response.get_data(as_text=True)
    with app.app_context():
        message = ContactMessage.query.filter_by(email="madre@test.local").first()
        assert message is not None
        assert message.is_read is False


def test_contact_honeypot_blocks_submission(app, client):
    with app.app_context():
        before = ContactMessage.query.count()
    client.post(
        "/contacto",
        data={
            "name": "Bot de prueba",
            "email": "bot@test.local",
            "subject": "Spam de prueba",
            "body": "Este mensaje debería ser bloqueado por el campo trampa.",
            "website": "http://spam.example",
        },
        follow_redirects=True,
    )
    with app.app_context():
        assert ContactMessage.query.count() == before


def test_unknown_page_returns_custom_404(client):
    response = client.get("/ruta-que-no-existe")
    assert response.status_code == 404
    assert "Página no encontrada" in response.get_data(as_text=True)


def test_security_headers_present(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_password_is_hashed_in_database(app):
    from app.models import User

    with app.app_context():
        user = User.query.filter_by(email="tutor@test.local").first()
        assert user.password_hash != "ClaveSegura123"
        assert user.password_hash.startswith("pbkdf2:sha256")
        assert user.check_password("ClaveSegura123")
        # La columna no debe contener la contraseña en texto plano
        assert "ClaveSegura123" not in user.password_hash
        db.session.rollback()
