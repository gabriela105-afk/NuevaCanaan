"""Pruebas del flujo mínimo: muro público, acceso, publicación y borrado."""

from __future__ import annotations

import base64
import io
from datetime import timedelta
from pathlib import Path

from app.extensions import db
from app.models import Post, utcnow
from tests.conftest import TEST_EMAIL, TEST_PASSWORD

# PNG 1x1 transparente: sirve para comprobar la firma binaria y el envío.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z4QAAAABJRU5ErkJggg=="
)


def _publish(client, body="", files=None):
    data = {"body": body}
    if files:
        data["photos"] = files
    return client.post(
        "/publicar",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_muro_publico_sin_iniciar_sesion(app, client):
    with app.app_context():
        db.session.add(Post(body="Noticia visible para todos"))
        db.session.commit()

    response = client.get("/")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Noticia visible para todos" in text
    assert "Iniciar sesión" in text
    assert "Publicar como" not in text


def test_login_rechaza_credenciales_incorrectas(client):
    response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": "contraseña-incorrecta"},
    )

    assert response.status_code == 200
    assert "incorrectos" in response.get_data(as_text=True)


def test_login_correcto_muestra_cuadro_de_publicacion(client):
    response = client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Publicar como" in response.get_data(as_text=True)


def test_publicar_requiere_sesion(client):
    response = client.post("/publicar", data={"body": "Sin sesión"})

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_publica_con_varias_fotografias(auth_client, app):
    response = _publish(
        auth_client,
        body="Noticia con dos fotografías",
        files=[
            (io.BytesIO(PNG_BYTES), "foto-uno.png"),
            (io.BytesIO(PNG_BYTES), "foto-dos.png"),
        ],
    )
    text = response.get_data(as_text=True)

    assert "Publicación creada correctamente" in text
    assert "Noticia con dos fotografías" in text

    with app.app_context():
        post = Post.query.one()
        assert post.body == "Noticia con dos fotografías"
        assert len(post.images) == 2
        assert [image.position for image in post.images] == [0, 1]
        paths = [Path(app.config["UPLOAD_FOLDER"]) / image.path for image in post.images]
        assert all(path.is_file() for path in paths)
        image_id = post.images[0].id

    image_response = auth_client.get(f"/imagenes/{image_id}")
    assert image_response.status_code == 200
    assert image_response.mimetype == "image/png"


def test_las_publicaciones_mas_recientes_aparecen_primero(app, client):
    with app.app_context():
        db.session.add_all(
            [
                Post(body="PUBLICACION ANTIGUA", created_at=utcnow() - timedelta(hours=2)),
                Post(body="PUBLICACION RECIENTE", created_at=utcnow()),
            ]
        )
        db.session.commit()

    text = client.get("/").get_data(as_text=True)
    assert text.index("PUBLICACION RECIENTE") < text.index("PUBLICACION ANTIGUA")


def test_admin_elimina_publicacion_y_sus_fotos(auth_client, app):
    _publish(
        auth_client,
        body="Publicación que se eliminará",
        files=[(io.BytesIO(PNG_BYTES), "borrar.png")],
    )

    with app.app_context():
        post = Post.query.one()
        post_id = post.id
        image_path = Path(app.config["UPLOAD_FOLDER"]) / post.images[0].path
        assert image_path.is_file()

    response = auth_client.post(
        f"/publicaciones/{post_id}/eliminar", follow_redirects=True
    )
    text = response.get_data(as_text=True)

    assert "Publicación eliminada" in text
    with app.app_context():
        assert db.session.get(Post, post_id) is None
        assert not image_path.exists()


def test_archivo_invalido_no_crea_publicacion(auth_client, app):
    response = _publish(
        auth_client,
        body="",
        files=[(io.BytesIO(b"esto no es una imagen"), "falsa.png")],
    )

    assert "no parece una imagen" in response.get_data(as_text=True)
    with app.app_context():
        assert Post.query.count() == 0


def test_imagen_inexistente_devuelve_404(client):
    assert client.get("/imagenes/9999").status_code == 404
