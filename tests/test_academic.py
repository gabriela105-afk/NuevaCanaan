"""Pruebas de los módulos académicos y de la mensajería interna."""

from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models import Attendance, Grade, Message, Notification, User


def login(client, email, password="ClaveSegura123"):
    return client.post("/login", data={"email": email, "password": password})


def test_teacher_registers_attendance(app, client, data):
    login(client, "docente@test.local")
    response = client.post(
        f"/docentes/cursos/{data['course_one']}/asistencia",
        data={
            "date": date.today().isoformat(),
            f"status_{data['student_one']}": "ausente",
            f"notes_{data['student_one']}": "Sin justificación registrada",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "registros de asistencia" in response.get_data(as_text=True)

    with app.app_context():
        record = Attendance.query.filter_by(student_id=data["student_one"]).first()
        assert record is not None
        assert record.status == "ausente"


def test_teacher_registers_grade_and_parent_sees_it(app, client, data):
    login(client, "docente@test.local")
    client.post(
        f"/docentes/cursos/{data['course_one']}/notas",
        data={
            "student_id": data["student_one"],
            "period": "1",
            "score": "78",
            "max_score": "100",
            "observations": "Buen desempeño",
        },
        follow_redirects=True,
    )

    with app.app_context():
        grade = Grade.query.filter_by(student_id=data["student_one"]).first()
        assert grade is not None
        assert grade.score == 78
        assert grade.percentage == 78.0

    client.post("/logout")
    login(client, "tutor@test.local")
    body = client.get(f"/portal/hijos/{data['student_one']}").get_data(as_text=True)
    assert "78.0 / 100.0" in body


def test_grade_rejects_score_above_maximum(app, client, data):
    login(client, "docente@test.local")
    response = client.post(
        f"/docentes/cursos/{data['course_one']}/notas",
        data={
            "student_id": data["student_one"],
            "period": "1",
            "score": "150",
            "max_score": "100",
        },
        follow_redirects=True,
    )
    assert "no puede superar el puntaje máximo" in response.get_data(as_text=True)
    with app.app_context():
        assert Grade.query.count() == 0


def test_parent_cannot_see_other_student_grades(app, client, data):
    with app.app_context():
        db.session.add(
            Grade(
                student_id=data["student_two"],
                course_id=data["course_two"],
                period="1",
                score=95,
                max_score=100,
            )
        )
        db.session.commit()

    login(client, "tutor@test.local")
    assert client.get(f"/portal/hijos/{data['student_two']}").status_code == 403


def test_notification_mark_all_read(app, client):
    login(client, "tutor@test.local")
    with app.app_context():
        user = User.query.filter_by(email="tutor@test.local").first()
        db.session.add(
            Notification(user_id=user.id, title="Aviso de prueba", body="Contenido")
        )
        db.session.commit()

    response = client.post("/notificaciones/leer-todas", follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="tutor@test.local").first()
        assert Notification.query.filter_by(user_id=user.id, read_at=None).count() == 0


def test_internal_message_between_parent_and_direction(app, client):
    login(client, "tutor@test.local")
    with app.app_context():
        direction_id = User.query.filter_by(email="direccion@test.local").first().id

    response = client.post(
        "/mensajes/nuevo",
        data={
            "recipient_id": direction_id,
            "subject": "Consulta sobre reunión",
            "body": "Deseo confirmar la hora de la reunión de padres.",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Mensaje enviado correctamente" in response.get_data(as_text=True)

    with app.app_context():
        message = Message.query.filter_by(subject="Consulta sobre reunión").first()
        assert message is not None
        assert message.recipient_id == direction_id


def test_parent_cannot_message_another_parent(app, client):
    with app.app_context():
        other = User.query.filter_by(email="tutor2@test.local").first()
        other_id = other.id

    login(client, "tutor@test.local")
    response = client.post(
        "/mensajes/nuevo",
        data={
            "recipient_id": other_id,
            "subject": "Intento de mensaje",
            "body": "Este mensaje no debería permitirse entre familias.",
        },
        follow_redirects=True,
    )
    assert "destinatario válido" in response.get_data(as_text=True)


def test_parent_cannot_read_others_message(app, client):
    with app.app_context():
        first = User.query.filter_by(email="tutor@test.local").first()
        second = User.query.filter_by(email="tutor2@test.local").first()
        message = Message(
            sender_id=second.id,
            recipient_id=second.id,
            subject="Mensaje privado ajeno",
            body="Contenido que no debe ver otro tutor.",
        )
        db.session.add(message)
        db.session.commit()
        message_id = message.id

    login(client, "tutor@test.local")
    assert client.get(f"/mensajes/{message_id}").status_code == 403
