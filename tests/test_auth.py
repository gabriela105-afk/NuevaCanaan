"""Pruebas de autenticación, sesiones y bloqueo por intentos fallidos."""

from __future__ import annotations

from app.models import User


def login(client, email="tutor@test.local", password="ClaveSegura123"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def test_login_success_redirects_to_dashboard(client):
    response = login(client)
    assert response.status_code == 302
    assert "/portal" in response.headers["Location"]


def test_login_wrong_password_shows_error(client):
    response = client.post(
        "/login",
        data={"email": "tutor@test.local", "password": "incorrecta"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "incorrectos" in response.get_data(as_text=True)


def test_login_unknown_email_does_not_reveal_existence(client):
    response = client.post(
        "/login",
        data={"email": "desconocido@test.local", "password": "cualquiera"},
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    # Mismo mensaje genérico que con una contraseña incorrecta: no se revela
    # si el correo está registrado.
    assert "Correo electrónico o contraseña incorrectos." in body
    assert "no está registrado" not in body
    assert "no existe una cuenta" not in body


def test_private_route_requires_login(client):
    response = client.get("/portal/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_rejects_open_redirect(client):
    response = client.post(
        "/login?next=https://sitio-malicioso.example",
        data={
            "email": "tutor@test.local",
            "password": "ClaveSegura123",
            "next": "https://sitio-malicioso.example",
        },
    )
    assert response.status_code == 302
    assert "sitio-malicioso" not in response.headers["Location"]


def test_logout_is_post_only(client):
    login(client)
    assert client.get("/logout").status_code == 405
    response = client.post("/logout", follow_redirects=True)
    assert response.status_code == 200
    assert "Sesión finalizada" in response.get_data(as_text=True)


def test_account_locks_after_repeated_failures(app, client):
    for _ in range(app.config["LOGIN_MAX_ATTEMPTS"]):
        client.post(
            "/login",
            data={"email": "tutor@test.local", "password": "mala"},
            follow_redirects=True,
        )
    with app.app_context():
        user = User.query.filter_by(email="tutor@test.local").first()
        assert user.is_locked is True
        assert user.failed_login_attempts >= app.config["LOGIN_MAX_ATTEMPTS"]

    response = client.post(
        "/login",
        data={"email": "tutor@test.local", "password": "ClaveSegura123"},
    )
    assert response.status_code == 429


def test_inactive_user_cannot_login(app, client):
    with app.app_context():
        user = User.query.filter_by(email="tutor2@test.local").first()
        user.is_active = False
        app.extensions["sqlalchemy"].session.commit()

    response = client.post(
        "/login",
        data={"email": "tutor2@test.local", "password": "ClaveSegura123"},
        follow_redirects=True,
    )
    assert "desactivada" in response.get_data(as_text=True)


def test_change_password_flow(client):
    login(client)
    response = client.post(
        "/cambiar-contrasena",
        data={
            "current_password": "ClaveSegura123",
            "new_password": "NuevaClave456",
            "confirm_password": "NuevaClave456",
        },
        follow_redirects=True,
    )
    assert "actualizada correctamente" in response.get_data(as_text=True)

    client.post("/logout")
    response = client.post(
        "/login",
        data={"email": "tutor@test.local", "password": "NuevaClave456"},
    )
    assert response.status_code == 302


def test_change_password_requires_current_password(client):
    login(client)
    response = client.post(
        "/cambiar-contrasena",
        data={
            "current_password": "equivocada",
            "new_password": "NuevaClave456",
            "confirm_password": "NuevaClave456",
        },
        follow_redirects=True,
    )
    assert "contraseña actual no es correcta" in response.get_data(as_text=True)
