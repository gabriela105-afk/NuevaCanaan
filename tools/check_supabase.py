"""Diagnóstico de solo lectura de la base PostgreSQL usada en producción.

Uso:
    python tools/check_supabase.py

Toma ``DATABASE_URL`` de ``.env`` o del entorno (la misma variable que se
configura en Render) y comprueba:

* que la conexión funcione y qué usuario/versión responde;
* qué tablas existen en el esquema ``public``;
* cuántas filas hay en ``admins``, ``posts`` y ``post_images`` (si existen).

NO crea, modifica ni elimina nada. Para crear las tablas, y solo con
autorización, use: ``python -m app.cli init-and-seed``.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv(BASE_DIR / ".env")

from config import mask_database_uri  # noqa: E402

EXPECTED_TABLES = ("admins", "posts", "post_images")


def main() -> int:
    from app import create_app
    from app.extensions import db

    app = create_app("production")
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    print(f"Base de datos en uso: {mask_database_uri(uri)}")

    if uri.startswith("sqlite"):
        print()
        print("ERROR: DATABASE_URL no está definida; se está usando SQLite local.")
        print("Defina DATABASE_URL con la cadena del pooler de Supabase en .env")
        print("(o en el entorno) y vuelva a ejecutar este diagnóstico.")
        return 1

    with app.app_context():
        try:
            with db.engine.connect() as connection:
                version = connection.execute(text("select version()")).scalar_one()
                user = connection.execute(text("select current_user")).scalar_one()
                database = connection.execute(
                    text("select current_database()")
                ).scalar_one()
        except SQLAlchemyError as error:
            print()
            print("ERROR de conexión:")
            print(f"  {error.__class__.__name__}: {error}")
            return 2

        print(f"Conectado a «{database}» como «{user}»")
        print(f"Servidor: {version}")

        tables = set(inspect(db.engine).get_table_names(schema="public"))
        existing = [name for name in EXPECTED_TABLES if name in tables]
        missing = [name for name in EXPECTED_TABLES if name not in tables]

        print()
        print("Tablas del muro: " + (", ".join(existing) if existing else "(ninguna)"))
        if missing:
            print("Faltan tablas: " + ", ".join(missing))
            print("Para crearlas (con autorización): python -m app.cli init-and-seed")

        for table in existing:
            try:
                with db.engine.connect() as connection:
                    total = connection.execute(
                        text(f'select count(*) from public."{table}"')
                    ).scalar_one()
            except SQLAlchemyError as error:
                print(f"  {table}: no se pudo contar ({error.__class__.__name__})")
            else:
                print(f"  {table}: {total} fila(s)")

        extra = sorted(tables - set(EXPECTED_TABLES))
        if extra:
            print("Otras tablas en public: " + ", ".join(extra))

    print()
    print("Diagnóstico completado (solo lectura, sin cambios).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
