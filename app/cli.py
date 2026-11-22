"""Comandos de consola para inicializar la base y crear el administrador.

Uso local:
    flask --app run.py init-db
    flask --app run.py create-admin --email ... --password ... --name ...

En Render el arranque ejecuta ``python -m app.cli init-and-seed``: crea las
tablas y la cuenta administradora definida por variables de entorno. Es
idempotente: no duplica ni sobrescribe datos existentes.
"""

from __future__ import annotations

import os
import sys

import click

from .extensions import db
from .models import Admin
from .schema import ensure_schema


def _ensure_admin() -> str | None:
    """Crea la cuenta administradora inicial desde ADMIN_EMAIL/ADMIN_PASSWORD."""
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""
    name = (os.getenv("ADMIN_NAME") or "Administrador").strip() or "Administrador"

    if not email or not password:
        click.echo(
            "Aviso: ADMIN_EMAIL / ADMIN_PASSWORD no están definidos; "
            "no se creó una cuenta administradora."
        )
        return None

    if Admin.query.filter_by(email=email).first():
        click.echo(f"La cuenta administradora {email} ya existe; no se modificó.")
        return None

    admin = Admin(email=email, name=name)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    click.echo(f"Cuenta administradora creada: {email}")
    return email


def bootstrap_database() -> None:
    """Crea el esquema y la cuenta administradora mínima (idempotente)."""
    db.create_all()
    additions = ensure_schema()
    if additions:
        click.echo(
            "Columnas agregadas a post_images: " + ", ".join(additions)
        )
    _ensure_admin()


def register_cli(app) -> None:
    @app.cli.command("init-db")
    def init_db_command():
        """Crea las tablas y la cuenta administradora configurada."""
        bootstrap_database()
        click.echo("Base de datos verificada correctamente.")

    @app.cli.command("init-and-seed")
    def init_and_seed_command():
        """Inicialización usada por Render al arrancar el servicio."""
        bootstrap_database()
        click.echo("Inicialización completada (tablas + administrador).")

    @app.cli.command("create-admin")
    @click.option("--email", required=True, help="Correo del administrador.")
    @click.option("--password", required=True, help="Contraseña inicial.")
    @click.option("--name", default="Administrador", help="Nombre visible.")
    def create_admin_command(email: str, password: str, name: str):
        """Crea una cuenta administradora adicional."""
        email = email.strip().lower()
        if Admin.query.filter_by(email=email).first():
            click.echo(f"El correo {email} ya está registrado.")
            return
        admin = Admin(email=email, name=name.strip() or "Administrador")
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Cuenta administradora creada: {email}")


if __name__ == "__main__":  # ``python -m app.cli init-and-seed`` en Render
    from app import create_app

    cli_app = create_app()
    with cli_app.app_context():
        if len(sys.argv) > 1 and sys.argv[1] in {"init-and-seed", "init-db"}:
            bootstrap_database()
            print("Inicialización completada.")
        else:
            print(
                "Comandos disponibles: init-and-seed, init-db.\n"
                "Para el resto use 'flask --app run.py <comando>'."
            )
