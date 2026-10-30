"""Comunicados oficiales: listado público, detalle y descarga de adjuntos."""

from __future__ import annotations

from datetime import date

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
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import ANNOUNCEMENT_CATEGORIES, Announcement
from ..utils import upload_path

announcements_bp = Blueprint("announcements", __name__)


@announcements_bp.get("/comunicados")
def index():
    category = (request.args.get("categoria") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config["ITEMS_PER_PAGE"]

    query = Announcement.query.filter(
        Announcement.status == "published",
        Announcement.audience == "public",
        or_(Announcement.expires_at.is_(None), Announcement.expires_at >= date.today()),
    )
    if category in ANNOUNCEMENT_CATEGORIES:
        query = query.filter(Announcement.category == category)

    pagination = query.order_by(
        Announcement.is_pinned.desc(),
        Announcement.published_at.desc(),
        Announcement.id.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "announcements/index.html",
        pagination=pagination,
        announcements=pagination.items,
        category=category,
        categories=ANNOUNCEMENT_CATEGORIES,
    )


@announcements_bp.get("/comunicados/<int:announcement_id>")
def detail(announcement_id: int):
    announcement = db.session.get(Announcement, announcement_id)
    if announcement is None:
        abort(404)

    user = current_user if current_user.is_authenticated else None
    is_staff = bool(user and user.is_staff)
    is_author = bool(user and announcement.author_id == user.id)

    if announcement.status != "published" or announcement.is_expired:
        # El equipo institucional y el autor pueden previsualizar borradores y vencidos.
        if not is_staff and not is_author:
            abort(404)
    elif not announcement.is_visible_to(user) and not is_author:
        if user is None:
            flash(
                "Inicie sesión con su cuenta institucional para ver este comunicado.",
                "warning",
            )
            return redirect(url_for("auth.login", next=request.path))
        abort(403)

    return render_template("announcements/detail.html", announcement=announcement)


@announcements_bp.get("/comunicados/<int:announcement_id>/adjunto")
@login_required
def attachment(announcement_id: int):
    announcement = db.session.get(Announcement, announcement_id)
    if announcement is None or not announcement.attachment_path:
        abort(404)
    if not (current_user.is_staff or announcement.is_visible_to(current_user)):
        abort(403)

    try:
        path = upload_path(announcement.attachment_path)
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)

    return send_file(
        path,
        mimetype=announcement.attachment_mime or "application/octet-stream",
        as_attachment=True,
        download_name=announcement.attachment_name or path.name,
        max_age=0,
    )
