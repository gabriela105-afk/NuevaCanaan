"""Rutas públicas del muro y acciones del administrador."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import db
from .models import Admin, Post, PostImage
from .utils import (
    clean,
    clean_multiline,
    delete_upload,
    save_image_upload,
    upload_path,
)

main = Blueprint("main", __name__)


@main.get("/")
def index():
    """Muro público: visible sin iniciar sesión, lo más reciente primero."""
    posts = Post.query.order_by(Post.created_at.desc(), Post.id.desc()).all()
    return render_template("index.html", posts=posts)


@main.route("/login", methods=["GET", "POST"])
def login():
    """Acceso exclusivo del administrador (no hay registro público)."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    email = ""
    if request.method == "POST":
        email = clean(request.form.get("email"), 180).lower()
        password = request.form.get("password") or ""
        admin = Admin.query.filter_by(email=email).first() if email else None

        if admin is not None and admin.is_active and admin.check_password(password):
            login_user(admin, remember=bool(request.form.get("remember")))
            flash("Sesión iniciada. Ya puede publicar.", "success")
            return redirect(url_for("main.index"))

        flash("Correo o contraseña incorrectos.", "error")

    return render_template("login.html", email=email)


@main.post("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("main.index"))


@main.post("/publicar")
@login_required
def publish():
    """Crea una publicación con texto y varias fotografías opcionales."""
    body = clean_multiline(
        request.form.get("body"), current_app.config["POST_MAX_LENGTH"]
    )
    uploads = [
        item for item in request.files.getlist("photos") if item and item.filename
    ]

    if not body and not uploads:
        flash("Escriba una noticia o seleccione al menos una fotografía.", "error")
        return redirect(url_for("main.index"))

    saved: list[dict] = []
    errors: list[str] = []
    for upload in uploads:
        metadata, error = save_image_upload(upload, "posts")
        if error:
            errors.append(error)
            continue
        if metadata:
            saved.append(metadata)

    if not body and not saved:
        for error in errors:
            flash(error, "error")
        flash("No se creó la publicación: no había contenido válido.", "error")
        return redirect(url_for("main.index"))

    post = Post(body=body, author_id=current_user.id)
    for position, metadata in enumerate(saved):
        post.images.append(
            PostImage(
                path=metadata["path"],
                storage=metadata.get("storage", "local"),
                url=metadata.get("url"),
                name=metadata["name"],
                mime=metadata["mime"],
                size=metadata["size"],
                position=position,
            )
        )

    try:
        db.session.add(post)
        db.session.commit()
    except Exception:  # pragma: no cover - protección ante fallos de la BD
        db.session.rollback()
        for metadata in saved:
            delete_upload(metadata["path"], metadata.get("storage", "local"))
        current_app.logger.exception("No se pudo guardar la publicación")
        flash("No se pudo guardar la publicación. Intente de nuevo.", "error")
        return redirect(url_for("main.index"))

    for error in errors:
        flash(error, "warning")
    flash("Publicación creada correctamente.", "success")
    return redirect(url_for("main.index"))


@main.post("/publicaciones/<int:post_id>/eliminar")
@login_required
def delete_post(post_id: int):
    """Elimina una publicación y sus fotografías del disco."""
    post = db.session.get(Post, post_id)
    if post is None:
        abort(404)

    for image in list(post.images):
        delete_upload(image.path, image.storage or "local")

    db.session.delete(post)
    db.session.commit()
    flash("Publicación eliminada.", "info")
    return redirect(url_for("main.index"))


@main.get("/imagenes/<int:image_id>")
def image(image_id: int):
    """Sirve una fotografía del muro a cualquier visitante."""
    post_image = db.session.get(PostImage, image_id)
    if post_image is None:
        abort(404)

    if (post_image.storage or "local") == "supabase":
        target = post_image.display_url
        if not target:
            abort(404)
        return redirect(target)

    try:
        path = upload_path(post_image.path)
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)

    return send_file(
        path,
        mimetype=post_image.mime or None,
        download_name=post_image.name or path.name,
        max_age=604800,
        conditional=True,
    )
