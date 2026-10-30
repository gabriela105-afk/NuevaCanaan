"""Pruebas de los flujos principales: comunicados, calendario y tareas."""

from __future__ import annotations

from datetime import date, timedelta

from app.models import Announcement, Assignment, Event, Notification


def login(client, email, password="ClaveSegura123"):
    return client.post("/login", data={"email": email, "password": password})


def test_admin_creates_published_announcement(app, client):
    login(client, "admin@test.local")
    response = client.post(
        "/admin/comunicados/nuevo",
        data={
            "title": "Reunión general de padres de familia",
            "summary": "Convocatoria institucional de prueba",
            "body": "Se convoca a todas las familias a la reunión general del trimestre.",
            "category": "reunion",
            "priority": "alta",
            "status": "published",
            "audience": "public",
            "target_role": "",
            "is_pinned": "1",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        announcement = Announcement.query.filter_by(
            title="Reunión general de padres de familia"
        ).first()
        assert announcement is not None
        assert announcement.status == "published"
        assert announcement.is_pinned is True
        assert announcement.published_at is not None
        assert announcement.author is not None
        assert Notification.query.count() > 0


def test_announcement_validation_rejects_short_title(app, client):
    login(client, "admin@test.local")
    response = client.post(
        "/admin/comunicados/nuevo",
        data={
            "title": "Ab",
            "body": "Corto",
            "status": "draft",
        },
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert "al menos 5 caracteres" in body
    assert "al menos 15 caracteres" in body
    with app.app_context():
        assert Announcement.query.count() == 2


def test_admin_creates_calendar_event(app, client):
    login(client, "admin@test.local")
    tomorrow = (date.today() + timedelta(days=3)).isoformat()
    response = client.post(
        "/admin/calendario/nuevo",
        data={
            "title": "Acto cívico de prueba",
            "description": "Actividad institucional de prueba",
            "start_date": tomorrow,
            "start_time": "08:30",
            "location": "Patio central",
            "category": "civico",
            "audience": "public",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        event = Event.query.filter_by(title="Acto cívico de prueba").first()
        assert event is not None
        assert event.start_time.strftime("%H:%M") == "08:30"
        assert event.category == "civico"


def test_event_validation_rejects_missing_date(app, client):
    login(client, "admin@test.local")
    response = client.post(
        "/admin/calendario/nuevo",
        data={"title": "Evento sin fecha", "start_date": "", "category": "otro"},
        follow_redirects=True,
    )
    assert "Indique la fecha" in response.get_data(as_text=True)


def test_teacher_registers_assignment_for_own_course(app, client, data):
    login(client, "docente@test.local")
    response = client.post(
        f"/docentes/cursos/{data['course_one']}/tareas/nueva",
        data={
            "title": "Tarea de fracciones",
            "description": "Resolver los ejercicios del capítulo 2.",
            "kind": "tarea",
            "subject": "Matemática",
            "due_date": (date.today() + timedelta(days=5)).isoformat(),
            "max_score": "20",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        assignment = Assignment.query.filter_by(title="Tarea de fracciones").first()
        assert assignment is not None
        assert assignment.course_id == data["course_one"]
        assert assignment.max_score == 20


def test_public_announcement_appears_on_home(app, client):
    login(client, "admin@test.local")
    client.post(
        "/admin/comunicados/nuevo",
        data={
            "title": "Inscripciones abiertas para la gestión 2027",
            "body": "La institución informa el periodo de inscripciones para la nueva gestión.",
            "category": "inscripcion",
            "priority": "alta",
            "status": "published",
            "audience": "public",
        },
        follow_redirects=True,
    )
    client.post("/logout")

    body = client.get("/").get_data(as_text=True)
    assert "Inscripciones abiertas para la gestión 2027" in body
