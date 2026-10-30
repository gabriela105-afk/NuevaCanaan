"""Migración de datos: SQLite local -> PostgreSQL (Supabase).

El proyecto funciona igual con SQLite (desarrollo y pruebas) o PostgreSQL
(producción). Este script copia TODOS los registros de la base SQLite local a la
base PostgreSQL de Supabase conservando identificadores, contraseñas (hashes) y
relaciones, y verifica al final que el número de filas coincida tabla por tabla.

Uso habitual (desde la raíz del proyecto, con el entorno virtual activo):

    # 1) Revisar qué se migraría, sin conectarse a Supabase
    python tools/migrate_sqlite_to_postgres.py --dry-run

    # 2) Generar el SQL del esquema para pegarlo en el editor de Supabase
    #    (opcional; también se puede dejar que el script cree las tablas)
    python tools/migrate_sqlite_to_postgres.py --print-sql

    # 3) Migrar de verdad: crea las tablas y copia los datos
    python tools/migrate_sqlite_to_postgres.py --target "postgresql://..."

    # 4) Si el destino ya tenía datos y se desea reemplazarlos
    python tools/migrate_sqlite_to_postgres.py --target "postgresql://..." --truncate

    # 5) Comprobar que todo cuadra, sin copiar nada
    python tools/migrate_sqlite_to_postgres.py --target "postgresql://..." --verify-only

Si no se pasa ``--target`` se usa la variable de entorno ``DATABASE_URL``.
La contraseña nunca se imprime: en la salida aparece siempre como ``***``.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import (  # noqa: E402  (import después de ajustar sys.path)
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    Time,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

import app.models  # noqa: E402,F401  (registra todas las tablas en db.metadata)
from app.extensions import db  # noqa: E402
from config import mask_database_uri, normalize_database_url  # noqa: E402

DEFAULT_SOURCE = BASE_DIR / "instance" / "nueva_canaan.db"
SCHEMA_SQL_FILE = BASE_DIR / "supabase_schema.sql"

EXIT_OK = 0
EXIT_ERROR = 1


# ---------------------------------------------------------------------------
# Utilidades de consola
# ---------------------------------------------------------------------------
def log(message: str = "") -> None:
    print(message, flush=True)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Conversión de valores (SQLite guarda fechas como texto y booleanos como 0/1)
# ---------------------------------------------------------------------------
def _to_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "si", "sí", "on"}


def _to_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace("T", " ")
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(raw)


def _to_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        converted = _to_datetime(raw)
        return converted.date() if converted else None


def _to_time(value):
    if value is None or isinstance(value, time):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return time.fromisoformat(raw)
    except ValueError:
        for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(raw, fmt).time()
            except ValueError:
                continue
        raise ValueError(f"hora no reconocida: {value!r}")


def convert_value(value, column):
    """Adapta un valor leído de SQLite al tipo declarado en el modelo."""
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, Boolean):
        return _to_bool(value)
    if isinstance(column_type, DateTime):
        return _to_datetime(value)
    if isinstance(column_type, Date):
        return _to_date(value)
    if isinstance(column_type, Time):
        return _to_time(value)
    if isinstance(column_type, Integer) and isinstance(value, str) and not value.strip():
        return None
    return value


def text_length_problems(table, row: dict) -> list[tuple[str, str, int, int]]:
    """Valores de texto que exceden el largo declarado (PostgreSQL lo rechaza)."""
    problems: list[tuple[str, str, int, int]] = []
    for column in table.columns:
        column_type = column.type
        limit = getattr(column_type, "length", None)
        if not isinstance(column_type, String) or not limit:
            continue
        value = row.get(column.name)
        if isinstance(value, str) and len(value) > limit:
            problems.append((table.name, column.name, len(value), limit))
    return problems


# ---------------------------------------------------------------------------
# Motores de base de datos
# ---------------------------------------------------------------------------
def build_source_engine(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"No existe la base SQLite: {path}")
    return create_engine(f"sqlite:///{path.as_posix()}", future=True)


def build_target_engine(url: str):
    if not url:
        raise ValueError(
            "Falta la cadena de conexión de Supabase. Use --target o la variable DATABASE_URL."
        )
    if url.strip().lower().startswith("sqlite"):
        raise ValueError("El destino debe ser PostgreSQL (Supabase), no SQLite.")
    normalized = normalize_database_url(url)
    connect_args = {"prepare_threshold": 0} if ":6543" in normalized else {}
    return create_engine(
        normalized,
        pool_pre_ping=True,
        pool_recycle=280,
        connect_args=connect_args,
        future=True,
    )


def ordered_tables() -> list:
    """Tablas del modelo en orden de dependencias (primero las padres)."""
    return list(db.metadata.sorted_tables)


def read_table(source_engine, table) -> list[dict]:
    with source_engine.connect() as connection:
        result = connection.execute(select(table))
        return [dict(row._mapping) for row in result]


def count_rows(engine, table) -> int:
    with engine.connect() as connection:
        return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def missing_source_tables(source_engine) -> list[str]:
    existing = set(inspect(source_engine).get_table_names())
    return [table.name for table in ordered_tables() if table.name not in existing]


def extra_source_tables(source_engine) -> list[str]:
    known = {table.name for table in ordered_tables()}
    ignored = {"sqlite_sequence", "alembic_version"}
    return [
        name
        for name in inspect(source_engine).get_table_names()
        if name not in known and name not in ignored
    ]


def schema_sql() -> str:
    """DDL de PostgreSQL equivalente a los modelos (para el editor de Supabase)."""
    dialect = postgresql.dialect()
    statements: list[str] = []
    for table in ordered_tables():
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            statements.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
    header = (
        "-- Esquema PostgreSQL de la plataforma Nueva Canaán\n"
        "-- Generado automáticamente desde app/models.py\n"
        "-- Pegar en Supabase → SQL Editor → New query → Run\n\n"
    )
    return header + "\n\n".join(statements) + "\n"


# ---------------------------------------------------------------------------
# Copia de datos
# ---------------------------------------------------------------------------
def truncate_target(target_engine) -> None:
    """Vacía las tablas del modelo en PostgreSQL (y reinicia los contadores)."""
    names = ", ".join(f'"{table.name}"' for table in reversed(ordered_tables()))
    with target_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


def reset_sequences(target_engine) -> None:
    """Ajusta las secuencias: al copiar los id explícitos, PostgreSQL no las mueve.

    Sin este paso, el primer INSERT nuevo reutilizaría un id existente y fallaría
    con "duplicate key value violates unique constraint".
    """
    with target_engine.begin() as connection:
        for table in ordered_tables():
            primary_key = list(table.primary_key.columns)
            if len(primary_key) != 1:
                continue
            column = primary_key[0]
            if not isinstance(column.type, Integer) or column.autoincrement is False:
                continue
            sequence = connection.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                {"table_name": table.name, "column_name": column.name},
            ).scalar_one()
            if not sequence:
                # La tabla no usa una secuencia (por ejemplo, clave asignada a mano).
                continue
            connection.execute(
                text(
                    "SELECT setval("
                    "pg_get_serial_sequence(:table_name, :column_name), "
                    f'COALESCE((SELECT MAX("{column.name}") FROM "{table.name}"), 0) + 1, '
                    "false)"
                ),
                {"table_name": table.name, "column_name": column.name},
            )


def copy_table(
    source_engine,
    target_engine,
    table,
    batch_size: int,
    allow_truncate_strings: bool,
) -> tuple[int, list[tuple[str, str, int, int]]]:
    """Copia una tabla. Devuelve (filas copiadas, problemas de longitud)."""
    rows = read_table(source_engine, table)
    if not rows:
        return 0, []

    problems: list[tuple[str, str, int, int]] = []
    prepared: list[dict] = []
    for row in rows:
        problems.extend(text_length_problems(table, row))
        prepared.append(
            {column.name: convert_value(row.get(column.name), column) for column in table.columns}
        )

    if problems and not allow_truncate_strings:
        return 0, problems

    if problems and allow_truncate_strings:
        limits = {column.name: column.type.length for column in table.columns}
        for row in prepared:
            for column_name, limit in limits.items():
                value = row.get(column_name)
                if isinstance(value, str) and limit and len(value) > limit:
                    row[column_name] = value[:limit]

    with target_engine.begin() as connection:
        for start in range(0, len(prepared), max(1, batch_size)):
            connection.execute(table.insert(), prepared[start : start + batch_size])
    return len(prepared), []


def verify_counts(source_engine, target_engine) -> list[tuple[str, int, int]]:
    """Compara el número de filas de cada tabla entre origen y destino."""
    mismatches: list[tuple[str, int, int]] = []
    for table in ordered_tables():
        source_total = count_rows(source_engine, table)
        target_total = count_rows(target_engine, table)
        if source_total != target_total:
            mismatches.append((table.name, source_total, target_total))
    return mismatches


# ---------------------------------------------------------------------------
# Interfaz de línea de comandos
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Copia los datos de SQLite a PostgreSQL (Supabase).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help="Ruta de la base SQLite de origen (por defecto instance/nueva_canaan.db).",
    )
    parser.add_argument(
        "--target",
        default=os.getenv("DATABASE_URL", "").strip(),
        help="Cadena de conexión de PostgreSQL/Supabase (por defecto DATABASE_URL).",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Vacía las tablas del destino antes de copiar (reemplaza su contenido).",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Sólo crea las tablas en el destino, sin copiar registros.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Sólo compara el número de filas entre origen y destino.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lee el origen y muestra qué se copiaría, sin conectarse al destino.",
    )
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help=f"Genera {SCHEMA_SQL_FILE.name} con el DDL para el editor de Supabase.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Filas enviadas por lote (por defecto 500).",
    )
    parser.add_argument(
        "--allow-truncate-strings",
        action="store_true",
        help="Recorta textos que exceden el largo del modelo en vez de abortar.",
    )
    return parser.parse_args(argv)


def _report_source(source_engine) -> bool:
    """Muestra un resumen del origen. Devuelve False si falta alguna tabla."""
    missing = missing_source_tables(source_engine)
    if missing:
        fail(
            "La base SQLite no tiene estas tablas: "
            + ", ".join(missing)
            + ". Ejecute 'flask --app run.py init-db' y vuelva a intentarlo."
        )
        return False
    extra = extra_source_tables(source_engine)
    if extra:
        log("Aviso: se ignoran tablas que no pertenecen al modelo: " + ", ".join(extra))
    return True


def _dry_run(source_engine) -> int:
    log("Revisión previa (no se escribe nada):")
    log("")
    log(f"{'Tabla':28}{'Filas':>8}")
    log("-" * 36)
    total = 0
    problems: list[tuple[str, str, int, int]] = []
    for table in ordered_tables():
        rows = read_table(source_engine, table)
        total += len(rows)
        log(f"{table.name:28}{len(rows):>8}")
        for row in rows:
            problems.extend(text_length_problems(table, row))
    log("-" * 36)
    log(f"{'TOTAL':28}{total:>8}")
    log("")
    if problems:
        log("Valores de texto que PostgreSQL rechazaría por exceder el largo:")
        for table_name, column_name, length, limit in problems:
            log(f"  - {table_name}.{column_name}: {length} caracteres (máximo {limit})")
        log("")
        log("Corrija esos datos o repita con --allow-truncate-strings (recorta el texto).")
    else:
        log("Los datos del origen son compatibles con el esquema de PostgreSQL.")
    return EXIT_OK


def main(argv=None) -> int:
    args = parse_args(argv)

    log("=" * 70)
    log(" Migración de datos: SQLite -> PostgreSQL (Supabase)")
    log("=" * 70)
    log(f"Origen  : {args.source}")
    log(f"Destino : {mask_database_uri(args.target)}")
    log("")

    try:
        source_engine = build_source_engine(Path(args.source))
    except Exception as exc:  # noqa: BLE001 - mensaje claro para el usuario
        fail(str(exc))
        return EXIT_ERROR

    try:
        if not _report_source(source_engine):
            return EXIT_ERROR
        log("")

        if args.print_sql:
            SCHEMA_SQL_FILE.write_text(schema_sql(), encoding="utf-8")
            log(f"Esquema SQL generado en: {SCHEMA_SQL_FILE}")
            log("Péguelo en Supabase → SQL Editor → New query → Run.")
            log("")
            if not args.target:
                return EXIT_OK

        if args.dry_run:
            return _dry_run(source_engine)

        if not args.target:
            fail(
                "Falta la cadena de conexión. Use --target \"postgresql://...\" "
                "o defina la variable DATABASE_URL."
            )
            return EXIT_ERROR

        try:
            target_engine = build_target_engine(args.target)
            with target_engine.connect() as connection:
                version = connection.execute(text("SELECT version()")).scalar_one()
            log(f"Conectado a: {str(version).split(',')[0]}")
            log("")
        except Exception as exc:  # noqa: BLE001
            fail(f"No se pudo conectar con PostgreSQL: {exc}")
            return EXIT_ERROR

        try:
            return _run(args, source_engine, target_engine)
        finally:
            target_engine.dispose()
    finally:
        source_engine.dispose()


def _run(args, source_engine, target_engine) -> int:
    """Ejecuta la copia (o la verificación) sobre un destino ya conectado."""
    if args.verify_only:
        mismatches = verify_counts(source_engine, target_engine)
        if mismatches:
            fail("Las tablas no coinciden:")
            for table_name, source_total, target_total in mismatches:
                log(f"  - {table_name}: origen={source_total} destino={target_total}")
            return EXIT_ERROR
        log("Verificación correcta: todas las tablas tienen el mismo número de filas.")
        return EXIT_OK

    log("Creando o verificando el esquema en PostgreSQL…")
    db.metadata.create_all(target_engine)
    log("")

    if args.schema_only:
        reset_sequences(target_engine)
        log("Esquema creado. No se copiaron registros (--schema-only).")
        return EXIT_OK

    existing = sum(count_rows(target_engine, table) for table in ordered_tables())
    if existing and not args.truncate:
        fail(
            f"El destino ya contiene {existing} filas. Use --truncate para reemplazarlas "
            "o --verify-only para comprobar el estado actual."
        )
        return EXIT_ERROR
    if existing and args.truncate:
        log(f"Vaciando el destino ({existing} filas)…")
        truncate_target(target_engine)

    log("Copiando registros:")
    log("")
    log(f"{'Tabla':28}{'Filas':>8}")
    log("-" * 36)
    total = 0
    for table in ordered_tables():
        try:
            copied, problems = copy_table(
                source_engine,
                target_engine,
                table,
                args.batch_size,
                args.allow_truncate_strings,
            )
        except Exception as exc:  # noqa: BLE001
            fail(f"Falló la copia de la tabla {table.name}: {exc}")
            return EXIT_ERROR
        if problems:
            fail(f"Textos demasiado largos en la tabla {table.name}:")
            for table_name, column_name, length, limit in problems:
                log(f"  - {table_name}.{column_name}: {length} caracteres (máximo {limit})")
            return EXIT_ERROR
        total += copied
        log(f"{table.name:28}{copied:>8}")
    log("-" * 36)
    log(f"{'TOTAL':28}{total:>8}")
    log("")

    log("Ajustando secuencias de los identificadores…")
    reset_sequences(target_engine)
    log("")

    log("Verificando que no se perdió ningún registro…")
    mismatches = verify_counts(source_engine, target_engine)
    if mismatches:
        fail("Hay diferencias después de la copia:")
        for table_name, source_total, target_total in mismatches:
            log(f"  - {table_name}: origen={source_total} destino={target_total}")
        return EXIT_ERROR

    log("")
    log("=" * 70)
    log(f" Migración completada: {total} registros copiados correctamente.")
    log(" Los usuarios conservan su contraseña: sólo se copiaron los hashes.")
    log("=" * 70)
    return EXIT_OK


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:  # pragma: no cover
        fail("Operación cancelada por el usuario.")
        raise SystemExit(EXIT_ERROR)






