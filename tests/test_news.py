"""Pruebas del muro público de noticias y de su panel de administración."""

from __future__ import annotations

import io
from pathlib import Path

from app.extensions import db
from app.models import NewsComment, NewsPost, NewsReaction, User, utcnow


def login(client, email, password="ClaveSegura123"):
    return client.post("/login", data={"email": email, "password": password})


def seed_posts(app):
    """Crea una publicación visible y un borrador interno."""
    with app.app_context():
        author = User.query.filter_by(email="direccion@test.local").first()
        published = NewsPost(
            title="Acto cívico de bienvenida al año escolar",
            summary="La comunidad educativa celebró el inicio de clases.",
            body="La comunidad educativa celebró el inicio del año escolar con un acto cívico.",
            category="civico",
            status="published",
            published_at=utcnow(),
            author_id=author.id,
        )
        draft = NewsPost(
            title="Borrador de noticia no publicada",
            body="Este contenido todavía no debe aparecer en el muro público.",
            category="institucional",
            status="draft",
            author_id=author.id,
        )
        db.session.add_all([published, draft])
        db.session.commit()
        return published.id, draft.id


def test_wall_lists_only_published_posts(app, client):
    published_id, _ = seed_posts(app)
    body = client.get("/noticias").get_data(as_text=True)
    assert "Acto cívico de bienvenida al año escolar" in body
    assert "Borrador de noticia no publicada" not in body
    assert f'href="/noticias/{published_id}"' in body


def test_home_page_includes_latest_news(app, client):
    seed_posts(app)
    body = client.get("/").get_data(as_text=True)
    assert "Acto cívico de bienvenida al año escolar" in body
    assert "Borrador de noticia no publicada" not in body


def test_detail_page_and_hidden_draft(app, client):
    published_id, draft_id = seed_posts(app)

    response = client.get(f"/noticias/{published_id}")
    assert response.status_code == 200
    assert "Acto cívico de bienvenida" in response.get_data(as_text=True)

    assert client.get(f"/noticias/{draft_id}").status_code == 404
    assert client.get("/noticias/99999").status_code == 404


def test_staff_can_preview_draft(app, client):
    _, draft_id = seed_posts(app)
    login(client, "admin@test.local")
    response = client.get(f"/noticias/{draft_id}")
    assert response.status_code == 200
    assert "Vista previa" in response.get_data(as_text=True)


def test_category_filter_and_search(app, client):
    seed_posts(app)
    assert "Acto cívico de bienvenida" in client.get("/noticias?categoria=civico").get_data(as_text=True)
    assert "Acto cívico de bienvenida" not in client.get("/noticias?categoria=deportivo").get_data(as_text=True)
    assert "Acto cívico de bienvenida" in client.get("/noticias?q=cívico").get_data(as_text=True)


def test_like_toggle_returns_json(app, client):
    published_id, _ = seed_posts(app)
    headers = {"X-Requested-With": "fetch"}

    first = client.post(f"/noticias/{published_id}/me-gusta", headers=headers)
    assert first.status_code == 200
    assert first.get_json() == {"liked": True, "total": 1}

    second = client.post(f"/noticias/{published_id}/me-gusta", headers=headers)
    assert second.get_json() == {"liked": False, "total": 0}

    with app.app_context():
        assert NewsReaction.query.count() == 0


def test_public_comment_is_published_and_visible(app, client):
    published_id, _ = seed_posts(app)
    response = client.post(
        f"/noticias/{published_id}/comentar",
        data={
            "author_name": "Familia de Prueba",
            "body": "Felicitaciones a los estudiantes por el acto cívico.",
        },
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Felicitaciones a los estudiantes" in body

    with app.app_context():
        comment = NewsComment.query.filter_by(post_id=published_id).first()
        assert comment is not None
        assert comment.status == "approved"


def test_comment_honeypot_blocks_submission(app, client):
    published_id, _ = seed_posts(app)
    client.post(
        f"/noticias/{published_id}/comentar",
        data={
            "author_name": "Bot de prueba",
            "body": "Comentario automatizado que debe ser bloqueado.",
            "website": "http://spam.example",
        },
        follow_redirects=True,
    )
    with app.app_context():
        assert NewsComment.query.count() == 0


def test_hidden_comment_disappears_from_wall(app, client):
    published_id, _ = seed_posts(app)
    with app.app_context():
        db.session.add(
            NewsComment(
                post_id=published_id,
                author_name="Comentario Oculto",
                body="Comentario que la institución decidió ocultar del muro.",
                status="hidden",
            )
        )
        db.session.commit()
        comment_id = NewsComment.query.one().id

    assert "Comentario que la institución" not in client.get(
        f"/noticias/{published_id}"
    ).get_data(as_text=True)

    login(client, "admin@test.local")
    client.post(f"/admin/noticias/comentarios/{comment_id}/ocultar", follow_redirects=True)

    assert "Comentario que la institución" in client.get(
        f"/noticias/{published_id}"
    ).get_data(as_text=True)


def test_comment_disabled_on_post(app, client):
    published_id, _ = seed_posts(app)
    with app.app_context():
        post = db.session.get(NewsPost, published_id)
        post.allow_comments = False
        db.session.commit()

    body = client.get(f"/noticias/{published_id}").get_data(as_text=True)
    assert "comentarios están desactivados" in body

    client.post(
        f"/noticias/{published_id}/comentar",
        data={"author_name": "Familia de Prueba", "body": "Comentario no permitido."},
        follow_redirects=True,
    )
    with app.app_context():
        assert NewsComment.query.count() == 0


def test_staff_creates_post_from_admin_panel(app, client):
    login(client, "admin@test.local")
    response = client.post(
        "/admin/noticias/nueva",
        data={
            "title": "Campeonato interescolar de fútbol",
            "summary": "Nuestro equipo obtuvo el primer lugar.",
            "body": "Los estudiantes de secundaria participaron en el campeonato interescolar.",
            "category": "campeonato",
            "status": "published",
            "is_pinned": "1",
            "allow_comments": "1",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        post = NewsPost.query.filter_by(title="Campeonato interescolar de fútbol").first()
        assert post is not None
        assert post.status == "published"
        assert post.is_pinned is True
        assert post.allow_comments is True
        assert post.published_at is not None
        assert post.author is not None

    assert "Campeonato interescolar de fútbol" in client.get("/noticias").get_data(as_text=True)


def test_post_validation_rejects_short_content(app, client):
    login(client, "admin@test.local")
    response = client.post(
        "/admin/noticias/nueva",
        data={"title": "Ab", "body": "Corto", "status": "draft"},
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert "al menos 5 caracteres" in body
    assert "al menos 15 caracteres" in body
    with app.app_context():
        assert NewsPost.query.count() == 0


def test_publish_pin_and_archive_flow(app, client):
    published_id, draft_id = seed_posts(app)
    login(client, "admin@test.local")

    client.post(f"/admin/noticias/{draft_id}/publicar", follow_redirects=True)
    with app.app_context():
        draft = db.session.get(NewsPost, draft_id)
        assert draft.status == "published"
        assert draft.published_at is not None

    client.post(f"/admin/noticias/{published_id}/fijar", follow_redirects=True)
    with app.app_context():
        assert db.session.get(NewsPost, published_id).is_pinned is True

    client.post(f"/admin/noticias/{published_id}/archivar", follow_redirects=True)
    with app.app_context():
        assert db.session.get(NewsPost, published_id).status == "archived"

    assert "Acto cívico de bienvenida" not in client.get("/noticias").get_data(as_text=True)


def test_staff_uploads_cover_photo(app, client):
    login(client, "admin@test.local")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    response = client.post(
        "/admin/noticias/nueva",
        data={
            "title": "Feria cultural con fotografías",
            "body": "La feria cultural reunió a estudiantes y familias de todos los niveles.",
            "category": "cultural",
            "status": "published",
            "allow_comments": "1",
            "image": (io.BytesIO(png), "feria-cultural.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        post = NewsPost.query.filter_by(title="Feria cultural con fotografías").first()
        assert post is not None
        image = post.cover_image
        assert image is not None
        assert image.mime == "image/png"
        assert (Path(app.config["UPLOAD_FOLDER"]) / image.path).is_file()
        image_id = image.id
        post_id = post.id

    photo = client.get(f"/noticias/foto/{image_id}")
    assert photo.status_code == 200
    assert photo.mimetype == "image/png"
    assert client.get("/noticias/foto/99999").status_code == 404

    with app.app_context():
        db.session.get(NewsPost, post_id).status = "draft"
        db.session.commit()

    # El personal puede previsualizar la fotografía del borrador...
    assert client.get(f"/noticias/foto/{image_id}").status_code == 200

    # ...pero el público no.
    client.post("/logout")
    assert client.get(f"/noticias/foto/{image_id}").status_code == 404


def test_news_admin_requires_staff_role(app, client):
    assert client.get("/admin/noticias/").status_code == 302

    login(client, "tutor@test.local")
    assert client.get("/admin/noticias/").status_code == 403
    assert client.get("/admin/noticias/comentarios").status_code == 403

    client.post("/logout")
    login(client, "direccion@test.local")
    assert client.get("/admin/noticias/").status_code == 200
    assert client.get("/admin/noticias/comentarios").status_code == 200

