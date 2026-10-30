"""Configuración común de las pruebas automatizadas (pytest)."""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    Announcement,
    Course,
    CourseAssignment,
    Parent,
    ParentStudent,
    Student,
    StudentEnrollment,
    Teacher,
    User,
)
from app.models import utcnow
from werkzeug.security import generate_password_hash


@pytest.fixture()
def app(tmp_path):
    """Aplicación con base de datos temporal y datos mínimos de prueba."""
    app = create_app(
        "testing",
        overrides={
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "WTF_CSRF_ENABLED": False,
            "SERVER_NAME": "localhost",
            "PREFERRED_URL_SCHEME": "http",
            "SECRET_KEY": "clave-de-pruebas",
        },
    )

    with app.app_context():
        db.create_all()
        _seed(app)
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def data(app):
    """Devuelve identificadores útiles para las pruebas."""
    with app.app_context():
        students = Student.query.order_by(Student.id).all()
        courses = Course.query.order_by(Course.id).all()
        return {
            "students": [s.id for s in students],
            "courses": [c.id for c in courses],
            "student_one": students[0].id,
            "student_two": students[1].id,
            "course_one": courses[0].id,
            "course_two": courses[1].id,
        }


TEST_PASSWORD = "ClaveSegura123"
_PASSWORD_HASH_CACHE: dict[str, str] = {}


def _make_user(email, name, role, password=TEST_PASSWORD):
    user = User(email=email, full_name=name, role=role, is_active=True)
    # El hash se memoriza: calcularlo en cada usuario haría las pruebas muy lentas.
    if password not in _PASSWORD_HASH_CACHE:
        _PASSWORD_HASH_CACHE[password] = generate_password_hash(
            password, method="pbkdf2:sha256"
        )
    user.password_hash = _PASSWORD_HASH_CACHE[password]
    db.session.add(user)
    db.session.flush()
    return user


def _seed(app):
    """Datos ficticios mínimos para las pruebas."""
    admin = _make_user("admin@test.local", "Admin de Pruebas", "admin")
    direction = _make_user("direccion@test.local", "Dirección de Pruebas", "direction")
    teacher_user = _make_user("docente@test.local", "Docente de Pruebas", "teacher")
    other_teacher_user = _make_user("docente2@test.local", "Otro Docente", "teacher")
    parent_user = _make_user("tutor@test.local", "Tutor de Pruebas", "parent")
    other_parent_user = _make_user("tutor2@test.local", "Otro Tutor", "parent")

    course_one = Course(name="1ro de Secundaria", level="Secundaria", parallel="A", academic_year=2026)
    course_two = Course(name="2do de Secundaria", level="Secundaria", parallel="B", academic_year=2026)
    db.session.add_all([course_one, course_two])
    db.session.flush()

    teacher = Teacher(user_id=teacher_user.id, specialty="Matemática")
    other_teacher = Teacher(user_id=other_teacher_user.id, specialty="Lengua")
    db.session.add_all([teacher, other_teacher])
    db.session.flush()
    db.session.add(
        CourseAssignment(teacher_id=teacher.id, course_id=course_one.id, subject="Matemática")
    )

    student_one = Student(code="T-001", first_name="Ana", last_name="Prueba Uno")
    student_two = Student(code="T-002", first_name="Beto", last_name="Prueba Dos")
    db.session.add_all([student_one, student_two])
    db.session.flush()
    db.session.add_all(
        [
            StudentEnrollment(
                student_id=student_one.id, course_id=course_one.id, academic_year=2026
            ),
            StudentEnrollment(
                student_id=student_two.id, course_id=course_two.id, academic_year=2026
            ),
        ]
    )

    parent = Parent(user_id=parent_user.id, relationship="Madre")
    other_parent = Parent(user_id=other_parent_user.id, relationship="Padre")
    db.session.add_all([parent, other_parent])
    db.session.flush()
    db.session.add(
        ParentStudent(parent_id=parent.id, student_id=student_one.id, relationship="Madre")
    )
    db.session.add(
        ParentStudent(parent_id=other_parent.id, student_id=student_two.id, relationship="Padre")
    )

    db.session.add_all(
        [
            Announcement(
                title="Comunicado público de prueba",
                body="Contenido del comunicado público de prueba para el sitio web.",
                category="general",
                priority="normal",
                status="published",
                audience="public",
                published_at=utcnow(),
                author_id=direction.id,
            ),
            Announcement(
                title="Borrador interno de prueba",
                body="Este borrador no debe ser visible para el público.",
                category="administrativo",
                priority="baja",
                status="draft",
                audience="public",
                author_id=admin.id,
            ),
        ]
    )
    db.session.commit()
