"""Gestión de publicaciones y comentarios de NUEVA CANAÁN NOTICIAS.

Todas las rutas exigen sesión iniciada y rol de personal (administración o
dirección); el público sólo puede visualizar el muro.
"""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import (
    NEWS_CATEGORIES,
    NEWS_STATUSES,
    NewsComment,
    NewsImage,
    NewsPost,
    utcnow,
)
from ..utils import (
    choices,
    clean,
    clean_multiline,
    delete_upload,
    record_audit,
    save_image_upload,
    staff_required,
)

news_admin_bp = Blueprint("news_admin", __name__, url_prefix="/admin/noticias")

EDITABLE_STATUSES = ("draft", "published")
COMMENT_STATUSES = ("approved", "hidden")


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------
def _get_or_404(model, entity_id: int):
    entity = db.session.get(model, entity_id)
    if entity is None:
        abort(404)
    return entity


def _form_defaults(post: NewsPost | None = None) -> dict:
    if post is None:
        return {
            "title": "",
            "summary": "",
            "body": "",
            "category": "institucional",
            "status": "published",
            "is_pinned": False,
            "allow_comments": True,
        }
    return {
        "title": post.title,
        "summary": post.summary or "",
        "body": post.body,
        "category": post.category,
        "status": post.status if post.status in EDITABLE_STATUSES else "draft",
        "is_pinned": post.is_pinned,
        "allow_comments": post.allow_comments,
    }


def _post_form_data(form) -> tuple[dict, list[str]]:
    data = {
        "title": clean(form.get("title"), 180),
        "summary": clean(form.get("summary"), 300),
        "body": clean_multiline(form.get("body"), 12000),
        "category": choices(form.get("category"), NEWS_CATEGORIES, "institucional"),
        "status": choices(form.get("status"), EDITABLE_STATUSES, "draft"),
        "is_pinned": bool(form.get("is_pinned")),
        "allow_comments": bool(form.get("allow_comments")),
    }
    errors: list[str] = []
    if len(data["title"]) < 5:
        errors.append("El título debe tener al menos 5 caracteres.")
    if len(data["body"]) < 15:
        errors.append("El contenido de la noticia debe tener al menos 15 caracteres.")
    return data, errors


def _attach_cover(post: NewsPost, meta: dict) -> None:
    """Agrega la fotografía principal (versión 1: una sola por publicación)."""
    db.session.add(
        NewsImage(
            post_id=post.id,
            path=meta["path"],
            name=meta["name"],
            mime=meta["mime"],
            size=meta["size"],
            position=0,
            alt=post.title[:180],
        )
    )


def _remove_cover(post: NewsPost) -> None:
    """Elimina las fotografías de la publicación (archivo + registro)."""
    for image in list(post.images):
        delete_upload(image.path)
        db.session.delete(image)


# ---------------------------------------------------------------------------
# Listado y edición de publicaciones
# ---------------------------------------------------------------------------
@news_admin_bp.get("/")
@login_required
@staff_required
def posts():
    status = request.args.get("estado", "")
    category = request.args.get("categoria", "")
    search = clean(request.args.get("q"), 80)
    page = request.args.get("page", 1, type=int)

    query = NewsPost.query.options(
        selectinload(NewsPost.images),
        selectinload(NewsPost.author),
        selectinload(NewsPost.comments),
        selectinload(NewsPost.reactions),
    )
    if status in NEWS_STATUSES:
        query = query.filter(NewsPost.status == status)
    if category in NEWS_CATEGORIES:
        query = query.filter(NewsPost.category == category)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(NewsPost.title.ilike(like), NewsPost.body.ilike(like))
        )

    pagination = query.order_by(
        NewsPost.is_pinned.desc(), NewsPost.created_at.desc()
    ).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"] * 2, error_out=False
    )

    return render_template(
        "admin/news.html",
        pagination=pagination,
        posts=pagination.items,
        status=status,
        category=category,
        search=search,
        statuses=NEWS_STATUSES,
        categories=NEWS_CATEGORIES,
        total_comments=NewsComment.query.count(),
        visible_comments=NewsComment.query.filter_by(status="approved").count(),
    )


@news_admin_bp.route("/nueva", methods=["GET", "POST"])
@login_required
@staff_required
def post_new():
    form = _form_defaults()

    if request.method == "POST":
        data, errors = _post_form_data(request.form)
        form.update(data)
        image_meta, image_error = save_image_upload(request.files.get("image"))
        if image_error:
            errors.append(image_error)

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            post = NewsPost(
                title=data["title"],
                summary=data["summary"],
                body=data["body"],
                category=data["category"],
                status=data["status"],
                is_pinned=data["is_pinned"],
                allow_comments=data["allow_comments"],
                author_id=current_user.id,
                published_at=utcnow() if data["status"] == "published" else None,
            )
            db.session.add(post)
            db.session.flush()
            if image_meta:
                _attach_cover(post, image_meta)
            record_audit("news_create", "news", post.id, post.title)
            db.session.commit()
            flash(
                "Noticia publicada en el muro."
                if data["status"] == "published"
                else "Noticia guardada como borrador.",
                "success",
            )
            return redirect(url_for("news_admin.posts"))

    return render_template(
        "admin/news_form.html",
        form=form,
        post=None,
        categories=NEWS_CATEGORIES,
        statuses=EDITABLE_STATUSES,
    )


@news_admin_bp.route("/<int:post_id>/editar", methods=["GET", "POST"])
@login_required
@staff_required
def post_edit(post_id: int):
    post = _get_or_404(NewsPost, post_id)
    form = _form_defaults(post)

    if request.method == "POST":
        data, errors = _post_form_data(request.form)
        form.update(data)
        image_meta, image_error = save_image_upload(request.files.get("image"))
        if image_error:
            errors.append(image_error)

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            post.title = data["title"]
            post.summary = data["summary"]
            post.body = data["body"]
            post.category = data["category"]
            post.is_pinned = data["is_pinned"]
            post.allow_comments = data["allow_comments"]
            if data["status"] == "published" and post.published_at is None:
                post.published_at = utcnow()
            post.status = data["status"]

            if image_meta:
                _remove_cover(post)
                db.session.flush()
                _attach_cover(post, image_meta)
            elif request.form.get("remove_image"):
                _remove_cover(post)

            record_audit("news_update", "news", post.id, post.title)
            db.session.commit()
            flash("Noticia actualizada correctamente.", "success")
            return redirect(url_for("news_admin.posts"))

    return render_template(
        "admin/news_form.html",
        form=form,
        post=post,
        categories=NEWS_CATEGORIES,
        statuses=EDITABLE_STATUSES,
    )


@news_admin_bp.post("/<int:post_id>/publicar")
@login_required
@staff_required
def post_publish(post_id: int):
    post = _get_or_404(NewsPost, post_id)
    post.status = "published"
    if post.published_at is None:
        post.published_at = utcnow()
    record_audit("news_publish", "news", post.id, post.title)
    db.session.commit()
    flash("La noticia ya está visible en el muro.", "success")
    return redirect(url_for("news_admin.posts"))


@news_admin_bp.post("/<int:post_id>/archivar")
@login_required
@staff_required
def post_archive(post_id: int):
    post = _get_or_404(NewsPost, post_id)
    post.status = "archived"
    record_audit("news_archive", "news", post.id, post.title)
    db.session.commit()
    flash("La noticia fue archivada y ya no aparece en el muro.", "info")
    return redirect(url_for("news_admin.posts"))


@news_admin_bp.post("/<int:post_id>/fijar")
@login_required
@staff_required
def post_pin(post_id: int):
    post = _get_or_404(NewsPost, post_id)
    post.is_pinned = not post.is_pinned
    record_audit(
        "news_pin" if post.is_pinned else "news_unpin",
        "news",
        post.id,
        post.title,
    )
    db.session.commit()
    flash(
        "Noticia destacada en la parte superior del muro."
        if post.is_pinned
        else "La noticia ya no está destacada.",
        "success",
    )
    return redirect(url_for("news_admin.posts"))


@news_admin_bp.post("/<int:post_id>/eliminar")
@login_required
@staff_required
def post_delete(post_id: int):
    post = _get_or_404(NewsPost, post_id)
    title = post.title
    _remove_cover(post)
    db.session.delete(post)
    record_audit("news_delete", "news", post_id, title)
    db.session.commit()
    flash("Publicación eliminada definitivamente.", "info")
    return redirect(url_for("news_admin.posts"))


# ---------------------------------------------------------------------------
# Moderación de comentarios
# ---------------------------------------------------------------------------
@news_admin_bp.get("/comentarios")
@login_required
@staff_required
def comments():
    status = request.args.get("estado", "")
    page = request.args.get("page", 1, type=int)

    query = NewsComment.query.options(selectinload(NewsComment.post))
    if status in COMMENT_STATUSES:
        query = query.filter(NewsComment.status == status)

    pagination = query.order_by(NewsComment.created_at.desc()).paginate(
        page=page,
        per_page=current_app.config["NEWS_COMMENTS_PER_PAGE"],
        error_out=False,
    )
    return render_template(
        "admin/news_comments.html",
        pagination=pagination,
        comments=pagination.items,
        status=status,
        statuses=COMMENT_STATUSES,
        total_visible=NewsComment.query.filter_by(status="approved").count(),
        total_hidden=NewsComment.query.filter_by(status="hidden").count(),
    )


@news_admin_bp.post("/comentarios/<int:comment_id>/ocultar")
@login_required
@staff_required
def comment_toggle(comment_id: int):
    comment = _get_or_404(NewsComment, comment_id)
    comment.status = "hidden" if comment.status == "approved" else "approved"
    record_audit(
        "news_comment_hide" if comment.status == "hidden" else "news_comment_show",
        "news_comment",
        comment.id,
        comment.author_name,
    )
    db.session.commit()
    flash(
        "El comentario quedó oculto del muro."
        if comment.status == "hidden"
        else "El comentario vuelve a ser visible.",
        "success",
    )
    return redirect(url_for("news_admin.comments"))


@news_admin_bp.post("/comentarios/<int:comment_id>/eliminar")
@login_required
@staff_required
def comment_delete(comment_id: int):
    comment = _get_or_404(NewsComment, comment_id)
    author = comment.author_name
    db.session.delete(comment)
    record_audit("news_comment_delete", "news_comment", comment_id, author)
    db.session.commit()
    flash("Comentario eliminado definitivamente.", "info")
    return redirect(url_for("news_admin.comments"))
