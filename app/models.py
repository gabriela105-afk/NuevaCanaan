"""Modelos mínimos del muro: administrador, publicación y fotografías."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow() -> datetime:
    """Fecha/hora UTC sin zona (compatible con SQLite y PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Admin(UserMixin, db.Model):
    """Única cuenta de acceso al panel de publicaciones.

    La contraseña se guarda siempre como hash; nunca en texto plano.
    """

    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(160), nullable=False, default="Administrador")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(
            raw_password, method="pbkdf2:sha256"
        )

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash or not raw_password:
            return False
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Admin {self.email}>"


class Post(db.Model):
    """Publicación del muro. Puede tener texto, fotografías o ambos."""

    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    author_id = db.Column(
        db.Integer, db.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True
    )

    author = db.relationship("Admin")
    images = db.relationship(
        "PostImage",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="PostImage.position",
    )

    @property
    def available_images(self) -> list["PostImage"]:
        """Fotografías que todavía existen en el disco."""
        return [image for image in self.images if image.is_available]

    @property
    def author_name(self) -> str:
        return self.author.name if self.author else "Nueva Canaán"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Post {self.id} ({len(self.images)} fotos)>"


class PostImage(db.Model):
    """Fotografía asociada a una publicación."""

    __tablename__ = "post_images"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(
        db.Integer,
        db.ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path = db.Column(db.String(255), nullable=False)  # ruta interna del backend
    name = db.Column(db.String(255))
    mime = db.Column(db.String(120))
    size = db.Column(db.Integer)
    position = db.Column(db.Integer, nullable=False, default=0)
    # ``local`` (UPLOAD_FOLDER) o ``supabase`` (Storage permanente).
    storage = db.Column(
        db.String(20), nullable=False, default="local", server_default="local"
    )
    url = db.Column(db.String(700))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    post = db.relationship("Post", back_populates="images")

    @property
    def display_url(self) -> str | None:
        """URL remota de la fotografía (``None`` si se sirve localmente)."""
        from .storage import display_url

        return display_url(self.storage, self.path, self.url)

    @property
    def is_available(self) -> bool:
        """¿La fotografía sigue disponible en su backend?"""
        from flask import current_app

        if not self.path:
            return False
        if (self.storage or "local") == "supabase":
            return True
        try:
            base = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
            target = (base / self.path).resolve()
        except (KeyError, OSError, ValueError):
            return False
        if base != target and base not in target.parents:
            return False
        return target.is_file()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PostImage {self.path!r}>"
