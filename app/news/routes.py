"""Muro público de NUEVA CANAÁN NOTICIAS.

Rutas públicas (sin inicio de sesión):

- ``/noticias``                muro paginado con filtros y búsqueda
- ``/noticias/<id>``           detalle de la publicación
- ``/noticias/foto/<id>``      entrega la fotografía (no expone el disco)
- ``/noticias/<id>/me-gusta``  reacción "me gusta" (anónima o con sesión)
- ``/noticias/<id>/comentar``  comentario del público

La portada ``/`` reutiliza :func:`render_feed` para mostrar el mismo muro.
"""

from __future__ import annotations

import time
import uuid

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import NEWS_CATEGORIES, NewsComment, NewsImage, NewsPost, NewsReaction
from ..utils import clean, clean_multiline, client_ip, upload_path

news_bp = Blueprint("news", __name__)

COMMENT_MAX_LENGTH = 1200
COMMENT_LIMIT = 5
COMMENT_WINDOW_SECONDS = 3600
VISITOR_SESSION_KEY = "news_visitor"


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------
def visitor_key() -> str:
    """Identificador anónimo del visitante, guardado en la sesión."""
    key = session.get(VISITOR_SESSION_KEY)
    if not key:
        key = uuid.uuid4().hex
        session[VISITOR_SESSION_KEY] = key
    return key


def _current_viewer():
    return current_user if current_user.is_authenticated else None


def _published_query():
    """Publicaciones publicadas con sus relaciones precargadas."""
    return NewsPost.query.filter(NewsPost.status == "published").options(
        selectinload(NewsPost.images),
        selectinload(NewsPost.author),
        selectinload(NewsPost.reactions),
        selectinload(NewsPost.comments),
    )


def _liked_post_ids(posts) -> set[int]:
    ids = [post.id for post in posts]
    if not ids:
        return set()
    rows = NewsReaction.query.filter(
        NewsReaction.post_id.in_(ids), NewsReaction.visitor_key == visitor_key()
    ).all()
    return {row.post_id for row in rows}


def render_feed(template: str = "news/index.html"):
    """Muro de noticias reutilizable desde la portada y desde ``/noticias``."""
    page = request.args.get("page", 1, type=int)
    category = clean(request.args.get("categoria"), 30)
    search = clean(request.args.get("q"), 80)

    query = _published_query()
    if category in NEWS_CATEGORIES:
        query = query.filter(NewsPost.category == category)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                NewsPost.title.ilike(like),
                NewsPost.summary.ilike(like),
                NewsPost.body.ilike(like),
            )
        )

    pagination = query.order_by(
        NewsPost.is_pinned.desc(),
        NewsPost.published_at.desc(),
        NewsPost.id.desc(),
    ).paginate(
        page=page, per_page=current_app.config["NEWS_PER_PAGE"], error_out=False
    )

    posts = pagination.items
    return render_template(
        template,
        posts=posts,
        pagination=pagination,
        category=category,
        search=search,
        categories=NEWS_CATEGORIES,
        liked_ids=_liked_post_ids(posts),
        total_posts=pagination.total,
    )


def _comment_rate_limited() -> bool:
    """Límite simple de comentarios por sesión."""
    now = int(time.time())
    stamps = [
        int(stamp)
        for stamp in session.get("news_comment_stamps", [])
        if now - int(stamp) < COMMENT_WINDOW_SECONDS
    ]
    if len(stamps) >= COMMENT_LIMIT:
        session["news_comment_stamps"] = stamps
        return True
    stamps.append(now)
    session["news_comment_stamps"] = stamps
    return False


# ---------------------------------------------------------------------------
# Rutas públicas
# ---------------------------------------------------------------------------
@news_bp.get("/noticias")
def index():
    """Muro de noticias con paginación y filtros."""
    return render_feed()


@news_bp.get("/noticias/<int:post_id>")
def detail(post_id: int):
    post = db.session.get(NewsPost, post_id)
    if post is None or not post.is_visible_to(_current_viewer()):
        abort(404)

    related = (
        _published_query()
        .filter(NewsPost.id != post.id, NewsPost.category == post.category)
        .order_by(NewsPost.published_at.desc())
        .limit(3)
        .all()
    )
    comments = [comment for comment in post.comments if comment.status == "approved"]
    return render_template(
        "news/detail.html",
        post=post,
        comments=comments,
        related=related,
        liked=post.id in _liked_post_ids([post]),
    )


@news_bp.get("/noticias/foto/<int:image_id>")
def image(image_id: int):
    """Entrega la fotografía almacenada en ``UPLOAD_FOLDER``."""
    image = db.session.get(NewsImage, image_id)
    if image is None or image.post is None:
        abort(404)
    if not image.post.is_visible_to(_current_viewer()):
        abort(404)
    try:
        path = upload_path(image.path)
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)
    return send_file(
        path,
        mimetype=image.mime or None,
        download_name=image.name or path.name,
        max_age=604800,
        conditional=True,
    )


@news_bp.post("/noticias/<int:post_id>/me-gusta")
def like(post_id: int):
    """Alterna la reacción "me gusta" del visitante actual."""
    post = db.session.get(NewsPost, post_id)
    if post is None or not post.is_visible_to(_current_viewer()):
        abort(404)

    key = visitor_key()
    existing = NewsReaction.query.filter_by(post_id=post.id, visitor_key=key).first()
    if existing is not None:
        db.session.delete(existing)
        liked = False
    else:
        db.session.add(
            NewsReaction(
                post_id=post.id,
                visitor_key=key,
                user_id=current_user.id if current_user.is_authenticated else None,
            )
        )
        liked = True
    db.session.commit()

    total = NewsReaction.query.filter_by(post_id=post.id).count()
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"liked": liked, "total": total})
    return redirect(url_for("news.detail", post_id=post.id) + "#reacciones")


@news_bp.post("/noticias/<int:post_id>/comentar")
def comment(post_id: int):
    """Registra un comentario del público (con campo trampa y límite por sesión)."""
    post = db.session.get(NewsPost, post_id)
    if post is None or not post.is_visible_to(_current_viewer()):
        abort(404)

    target = url_for("news.detail", post_id=post.id) + "#comentarios"
    if not post.allow_comments:
        flash("Los comentarios están desactivados en esta publicación.", "warning")
        return redirect(target)

    form = request.form
    if clean(form.get("website"), 100):  # campo trampa antispam
        flash("No pudimos registrar su comentario. Intente nuevamente.", "error")
        return redirect(target)

    name = clean(form.get("author_name"), 80)
    body = clean_multiline(form.get("body"), COMMENT_MAX_LENGTH)

    errors: list[str] = []
    if len(name) < 3:
        errors.append("Escriba su nombre (mínimo 3 caracteres).")
    if len(body) < 5:
        errors.append("El comentario debe tener al menos 5 caracteres.")
    if _comment_rate_limited():
        errors.append("Ha enviado varios comentarios seguidos. Espere unos minutos.")

    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(target)

    db.session.add(
        NewsComment(
            post_id=post.id,
            author_name=name,
            body=body,
            status="approved",
            visitor_key=visitor_key(),
            ip_address=client_ip(),
            user_id=current_user.id if current_user.is_authenticated else None,
        )
    )
    db.session.commit()
    flash("¡Gracias por participar! Su comentario fue publicado.", "success")
    return redirect(target)
