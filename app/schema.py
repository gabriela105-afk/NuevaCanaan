"""Migraciones aditivas del esquema mínimo del muro.

Render conserva las publicaciones en PostgreSQL, pero las tablas creadas por
versiones anteriores no tienen las columnas nuevas de almacenamiento. Este
módulo agrega únicamente las columnas que falten; nunca elimina filas ni
renombra tablas. Se ejecuta al arrancar mediante ``init-and-seed``.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from .extensions import db

# DDL controlado (sin datos del usuario) para SQLite y PostgreSQL.
_POST_IMAGE_COLUMNS = {
    "storage": "VARCHAR(20) NOT NULL DEFAULT 'local'",
    "url": "VARCHAR(700)",
}


def ensure_schema() -> list[str]:
    """Agrega a ``post_images`` las columnas de almacenamiento que falten."""
    inspector = inspect(db.engine)
    if "post_images" not in inspector.get_table_names():
        return []

    existing = {column["name"] for column in inspector.get_columns("post_images")}
    additions: list[str] = []

    with db.engine.begin() as connection:
        for name, ddl in _POST_IMAGE_COLUMNS.items():
            if name in existing:
                continue
            connection.execute(
                text(f"ALTER TABLE post_images ADD COLUMN {name} {ddl}")
            )
            additions.append(name)

        # Las fotografías anteriores viven en UPLOAD_FOLDER.
        if "storage" in existing or "storage" in additions:
            connection.execute(
                text(
                    "UPDATE post_images SET storage = 'local' "
                    "WHERE storage IS NULL OR storage = ''"
                )
            )

    return additions
