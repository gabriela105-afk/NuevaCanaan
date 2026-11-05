"""Comandos de consola: inicialización de la base y datos de demostración.

Uso local:
    flask --app run.py init-db
    flask --app run.py seed-demo
    flask --app run.py create-admin --email ... --password ...

En Render el comando de arranque ejecuta ``python -m app.cli init-and-seed``,
que es idempotente: no duplica usuarios ni ajustes si ya existen.
"""

from __future__ import annotations

import os
import sys

import click

from .extensions import db
from .models import InstitutionSetting, NewsComment, NewsPost, User
from .utils import SETTING_DEFAULTS

DEMO_PASSWORD = "Demo12345"


def _ensure_settings() -> int:
    """Crea los ajustes institucionales faltantes sin sobrescribir los existentes."""
    created = 0
    for key, value in SETTING_DEFAULTS.items():
        if db.session.get(InstitutionSetting, key) is None:
            db.session.add(InstitutionSetting(key=key, value=value))
            created += 1
    db.session.commit()
    return created


def _ensure_admin() -> str | None:
    """Crea la cuenta administradora inicial definida por variables de entorno."""
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""
    name = (os.getenv("ADMIN_NAME") or "Administrador institucional").strip()

    if not email or not password:
        click.echo(
            "Aviso: ADMIN_EMAIL / ADMIN_PASSWORD no están definidos; "
            "no se creó una cuenta administradora."
        )
        return None

    if User.query.filter_by(email=email).first():
        click.echo(f"La cuenta administradora {email} ya existe; no se modificó.")
        return None

    user = User(email=email, full_name=name, role="admin", is_active=True)
    user.set_password(password)
    user.must_change_password = True
    db.session.add(user)
    db.session.commit()
    click.echo(f"Cuenta administradora creada: {email}")
    return email


def bootstrap_database() -> None:
    """Crea el esquema y los datos mínimos (idempotente)."""
    db.create_all()
    _ensure_settings()
    _ensure_admin()


# ---------------------------------------------------------------------------
# Registro de comandos
# ---------------------------------------------------------------------------
def register_cli(app) -> None:
    @app.cli.command("init-db")
    def init_db_command():
        """Crea las tablas y los datos institucionales mínimos."""
        bootstrap_database()
        click.echo("Esquema y ajustes institucionales verificados correctamente.")

    @app.cli.command("init-and-seed")
    def init_and_seed_command():
        """Inicialización usada por Render al arrancar el servicio."""
        bootstrap_database()
        click.echo("Inicialización completada (tablas + ajustes + administrador).")

    @app.cli.command("create-admin")
    @click.option("--email", required=True, help="Correo del administrador.")
    @click.option("--password", required=True, help="Contraseña inicial.")
    @click.option("--name", default="Administrador institucional", help="Nombre completo.")
    def create_admin_command(email, password, name):
        """Crea una cuenta administradora adicional."""
        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            click.echo(f"El correo {email} ya está registrado.")
            return
        user = User(email=email, full_name=name, role="admin", is_active=True)
        user.set_password(password)
        user.must_change_password = True
        db.session.add(user)
        db.session.commit()
        click.echo(f"Administrador {email} creado. Debe cambiar la contraseña al ingresar.")

    @app.cli.command("reset-password")
    @click.option("--email", required=True)
    @click.option("--password", required=True)
    def reset_password_command(email, password):
        """Restablece la contraseña de un usuario existente."""
        user = User.query.filter_by(email=email.strip().lower()).first()
        if not user:
            click.echo("No existe un usuario con ese correo.")
            return
        user.set_password(password)
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()
        click.echo(f"Contraseña restablecida para {user.email}.")

    @app.cli.command("list-users")
    def list_users_command():
        """Lista los usuarios registrados con su rol y estado."""
        users = User.query.order_by(User.role, User.full_name).all()
        if not users:
            click.echo("No hay usuarios registrados.")
            return
        for user in users:
            state = "activo" if user.is_active else "inactivo"
            click.echo(f"[{user.role:9}] {user.email:38} {user.full_name} ({state})")

    @app.cli.command("seed-demo")
    @click.option("--force", is_flag=True, help="Vuelve a crear los datos si faltan.")
    def seed_demo_command(force):
        """Carga datos FICTICIOS de demostración (identificados como tales)."""
        bootstrap_database()
        created = seed_demo_data(force=force)
        if created:
            click.echo("Datos de demostración cargados.")
            click.echo(
                "Cuentas ficticias (contraseña '" + DEMO_PASSWORD + "'):\n"
                "  direccion@nuevacanaan.edu\n"
                "  docente1@nuevacanaan.edu\n"
                "  padre1@nuevacanaan.edu"
            )
        else:
            click.echo("Los datos de demostración ya estaban cargados.")


# ---------------------------------------------------------------------------
# Datos FICTICIOS de demostración (no representan información real)
# ---------------------------------------------------------------------------
def seed_demo_data(force: bool = False) -> bool:
    """Carga datos de ejemplo claramente identificados con el sufijo (DEMO).

    Devuelve ``True`` si se crearon datos y ``False`` si ya existían.
    """
    from datetime import date, time, timedelta

    from .models import (
        Announcement,
        AnnouncementRecipient,
        Assignment,
        Attendance,
        ContactMessage,
        Course,
        CourseAssignment,
        Event,
        Grade,
        Parent,
        ParentStudent,
        Student,
        StudentEnrollment,
        Teacher,
    )
    from .models import utcnow
    from .utils import notify

    if User.query.filter_by(email="padre1@nuevacanaan.edu").first() and not force:
        return False

    today = date.today()
    year = today.year

    def make_user(email: str, name: str, role: str, phone: str | None = None) -> User:
        user = User(email=email, full_name=name, role=role, phone=phone, is_active=True)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        db.session.flush()
        return user

    direction_user = make_user("direccion@nuevacanaan.edu", "Dirección (DEMO)", "direction")

    courses = [
        Course(name="1ro de Secundaria", level="Secundaria", parallel="A",
               academic_year=year, description="Curso ficticio de demostración"),
        Course(name="2do de Secundaria", level="Secundaria", parallel="B",
               academic_year=year, description="Curso ficticio de demostración"),
        Course(name="4to de Secundaria", level="Secundaria", parallel="A",
               academic_year=year, description="Curso ficticio de demostración"),
    ]
    db.session.add_all(courses)
    db.session.flush()

    teacher_users = [
        make_user("docente1@nuevacanaan.edu", "Prof. Ana Quispe (DEMO)", "teacher"),
        make_user("docente2@nuevacanaan.edu", "Prof. Luis Mamani (DEMO)", "teacher"),
    ]
    teachers = [
        Teacher(user=teacher_users[0], employee_code="DEMO-DOC-01", specialty="Matemática"),
        Teacher(user=teacher_users[1], employee_code="DEMO-DOC-02", specialty="Lengua y Literatura"),
    ]
    db.session.add_all(teachers)
    db.session.flush()

    db.session.add_all(
        [
            CourseAssignment(teacher_id=teachers[0].id, course_id=courses[0].id, subject="Matemática"),
            CourseAssignment(teacher_id=teachers[0].id, course_id=courses[1].id, subject="Matemática"),
            CourseAssignment(teacher_id=teachers[1].id, course_id=courses[0].id, subject="Lengua y Literatura"),
        ]
    )

    students = [
        Student(code="DEMO-001", first_name="Estudiante", last_name="Demo Uno",
                birth_date=date(year - 14, 4, 12), gender="F"),
        Student(code="DEMO-002", first_name="Estudiante", last_name="Demo Dos",
                birth_date=date(year - 14, 8, 3), gender="M"),
        Student(code="DEMO-003", first_name="Estudiante", last_name="Demo Tres",
                birth_date=date(year - 16, 1, 27), gender="F"),
    ]
    db.session.add_all(students)
    db.session.flush()

    db.session.add_all(
        [
            StudentEnrollment(student_id=students[0].id, course_id=courses[0].id, academic_year=year),
            StudentEnrollment(student_id=students[1].id, course_id=courses[1].id, academic_year=year),
            StudentEnrollment(student_id=students[2].id, course_id=courses[2].id, academic_year=year),
        ]
    )

    parent_user_one = make_user("padre1@nuevacanaan.edu", "Sra. Rosa Flores (DEMO)", "parent", "70000001")
    parent_user_two = make_user("padre2@nuevacanaan.edu", "Sr. Juan Choque (DEMO)", "parent", "70000002")
    parents = [
        Parent(user=parent_user_one, relationship="Madre"),
        Parent(user=parent_user_two, relationship="Padre"),
    ]
    db.session.add_all(parents)
    db.session.flush()

    db.session.add_all(
        [
            ParentStudent(parent_id=parents[0].id, student_id=students[0].id,
                          relationship="Madre", is_primary=True),
            ParentStudent(parent_id=parents[0].id, student_id=students[1].id,
                          relationship="Madre", is_primary=True),
            ParentStudent(parent_id=parents[1].id, student_id=students[2].id,
                          relationship="Padre", is_primary=True),
        ]
    )
    db.session.flush()

    announcements = [
        Announcement(
            title="[DEMO] Reunión de padres de familia - primer trimestre",
            summary="Convocatoria ficticia para la reunión de entrega de informes.",
            body=(
                "Este comunicado es un EJEMPLO de demostración.\n\n"
                "Se convoca a las madres, padres y tutores a la reunión de entrega de "
                "informes del primer trimestre. La asistencia es importante para "
                "acompañar el proceso educativo de los estudiantes."
            ),
            category="reunion",
            priority="alta",
            status="published",
            audience="public",
            is_pinned=True,
            published_at=utcnow(),
            expires_at=today + timedelta(days=15),
            author_id=direction_user.id,
        ),
        Announcement(
            title="[DEMO] Calendario de evaluaciones del trimestre",
            summary="Fechas ficticias de evaluaciones para ejemplificar el módulo.",
            body=(
                "Comunicado de EJEMPLO. Las fechas de evaluaciones se publicarán en el "
                "calendario escolar y en el panel de cada curso."
            ),
            category="evaluacion",
            priority="normal",
            status="published",
            audience="public",
            published_at=utcnow(),
            author_id=direction_user.id,
        ),
        Announcement(
            title="[DEMO] Aviso interno para el curso 1ro de Secundaria A",
            summary="Comunicado dirigido únicamente a las familias de un curso.",
            body=(
                "Comunicado interno de EJEMPLO visible sólo para las familias y docentes "
                "del curso destinatario."
            ),
            category="academico",
            priority="normal",
            status="published",
            audience="internal",
            target_role="parent",
            published_at=utcnow(),
            author_id=direction_user.id,
        ),
        Announcement(
            title="[DEMO] Borrador de circular administrativa",
            summary="Ejemplo de comunicado en estado borrador (no visible al público).",
            body="Borrador de EJEMPLO que sólo ve el equipo administrativo.",
            category="administrativo",
            priority="baja",
            status="draft",
            audience="public",
            author_id=direction_user.id,
        ),
    ]
    db.session.add_all(announcements)
    db.session.flush()
    db.session.add(
        AnnouncementRecipient(announcement_id=announcements[2].id, course_id=courses[0].id)
    )
    news_posts = [
        NewsPost(
            title="[DEMO] Acto cívico de inicio del año escolar",
            summary="Publicación de ejemplo del muro NUEVA CANAÁN NOTICIAS.",
            body=(
                "Publicación de EJEMPLO del muro de noticias.\n\n"
                "La comunidad educativa participó del acto cívico de inicio del año "
                "escolar, con la presentación de los cursos y el saludo de la dirección."
            ),
            category="civico",
            status="published",
            is_pinned=True,
            published_at=utcnow(),
            author_id=direction_user.id,
        ),
        NewsPost(
            title="[DEMO] Campeonato interescolar de fútbol",
            summary="Los estudiantes representaron a la institución en el campeonato.",
            body=(
                "Noticia de EJEMPLO.\n\n"
                "El equipo de secundaria participó del campeonato interescolar y obtuvo "
                "el reconocimiento al juego limpio."
            ),
            category="campeonato",
            status="published",
            published_at=utcnow(),
            author_id=direction_user.id,
        ),
        NewsPost(
            title="[DEMO] Borrador de noticia sobre la feria cultural",
            body="Borrador de EJEMPLO que no se muestra en el muro público.",
            category="cultural",
            status="draft",
            author_id=direction_user.id,
        ),
    ]
    db.session.add_all(news_posts)
    db.session.flush()
    db.session.add(
        NewsComment(
            post_id=news_posts[0].id,
            author_name="Familia de demostración",
            body="Comentario de EJEMPLO publicado en el muro de noticias.",
            status="approved",
        )
    )
    db.session.add_all(
        [
            Event(title="[DEMO] Reunión de padres - 1ro A",
                  start_date=today + timedelta(days=5), start_time=time(9, 0),
                  location="Salón de actos (ficticio)", category="reunion",
                  audience="public", course_id=courses[0].id,
                  created_by=direction_user.id,
                  description="Evento de EJEMPLO del calendario escolar."),
            Event(title="[DEMO] Acto cívico institucional",
                  start_date=today + timedelta(days=10), start_time=time(7, 45),
                  location="Patio central (ficticio)", category="civico",
                  audience="public", created_by=direction_user.id),
            Event(title="[DEMO] Feria de actividades deportivas",
                  start_date=today + timedelta(days=20),
                  location="Cancha deportiva (ficticia)", category="deportivo",
                  audience="public", created_by=direction_user.id),
            Event(title="[DEMO] Evaluación interna de Matemática",
                  start_date=today + timedelta(days=12), start_time=time(10, 30),
                  category="examen", audience="internal", target_role="parent",
                  course_id=courses[0].id, created_by=direction_user.id),
        ]
    )

    assignments = [
        Assignment(course_id=courses[0].id, teacher_id=teachers[0].id,
                   title="[DEMO] Ejercicios de fracciones", kind="tarea",
                   subject="Matemática",
                   description="Tarea ficticia de ejemplo para el módulo de tareas.",
                   due_date=today + timedelta(days=7), max_score=20),
        Assignment(course_id=courses[0].id, teacher_id=teachers[0].id,
                   title="[DEMO] Evaluación de operaciones combinadas",
                   kind="evaluacion", subject="Matemática",
                   due_date=today + timedelta(days=3), max_score=100),
        Assignment(course_id=courses[0].id, teacher_id=teachers[1].id,
                   title="[DEMO] Lectura comprensiva", kind="actividad",
                   subject="Lengua y Literatura",
                   due_date=today + timedelta(days=9), max_score=50),
    ]
    db.session.add_all(assignments)
    db.session.flush()

    db.session.add_all(
        [
            Attendance(student_id=students[0].id, course_id=courses[0].id, date=today,
                       status="presente", recorded_by=teacher_users[0].id),
            Attendance(student_id=students[1].id, course_id=courses[1].id, date=today,
                       status="tarde", recorded_by=teacher_users[0].id,
                       notes="Registro ficticio de demostración"),
        ]
    )
    db.session.add_all(
        [
            Grade(student_id=students[0].id, course_id=courses[0].id,
                  assignment_id=assignments[1].id, period="1", score=86, max_score=100,
                  recorded_by=teacher_users[0].id,
                  observations="Nota ficticia de ejemplo"),
            Grade(student_id=students[0].id, course_id=courses[0].id,
                  assignment_id=assignments[2].id, period="1", score=42, max_score=50,
                  recorded_by=teacher_users[1].id),
        ]
    )

    db.session.add(
        ContactMessage(
            name="Consultante de prueba (DEMO)",
            email="consulta@demo.local",
            subject="[DEMO] Consulta de ejemplo",
            body="Mensaje ficticio creado por el comando seed-demo para probar el buzón.",
            ip_address="127.0.0.1",
        )
    )

    notify(
        parent_user_one,
        "Nuevo comunicado: [DEMO] Reunión de padres de familia - primer trimestre",
        "Notificación ficticia de demostración.",
        link=f"/comunicados/{announcements[0].id}",
        category="announcement",
    )

    db.session.commit()
    return True


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

