"""Pruebas de los módulos académicos y de la mensajería interna."""

from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models import (
    AcademicConfig,
    AcademicObservation,
    Attendance,
    CourseSubject,
    Grade,
    GradeChange,
    Message,
    Notification,
    SchoolYear,
    Subject,
    SubjectGrade,
    Trimester,
    User,
)


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


def _open_academic_panel(app, client):
    """Configura escala, año, materia y asignación desde el panel real."""
    login(client, "admin@test.local")
    client.post(
        "/admin/academico/configuracion",
        data={
            "min_score": "0",
            "max_score": "100",
            "passing_score": "51",
            "decimals": "0",
        },
        follow_redirects=True,
    )
    client.post(
        "/admin/academico/anios",
        data={
            "name": "2026",
            "start_date": "2026-02-01",
            "end_date": "2026-11-30",
            "is_active": "1",
        },
        follow_redirects=True,
    )
    client.post(
        "/admin/academico/materias",
        data={"name": "Matemática", "code": "MAT", "area": "Científica"},
        follow_redirects=True,
    )
    with app.app_context():
        year = SchoolYear.query.filter_by(name="2026").first()
        subject = Subject.query.filter_by(name="Matemática").first()
        return year.id, subject.id, year.trimesters[0].id


def test_academic_admin_configures_and_records_grades(app, client, data):
    year_id, subject_id, trimester_id = _open_academic_panel(app, client)

    login(client, "admin@test.local")
    client.post(
        "/admin/academico/asignaciones",
        data={
            "course_id": data["course_one"],
            "subject_id": subject_id,
            "teacher_id": "",
            "weekly_hours": "4",
        },
        follow_redirects=True,
    )
    with app.app_context():
        link = CourseSubject.query.filter_by(
            course_id=data["course_one"], subject_id=subject_id
        ).first()
        assert link is not None
        link_id = link.id

    url = (
        f"/admin/academico/notas?anio={year_id}&trimestre={trimester_id}"
        f"&asignacion={link_id}"
    )
    response = client.post(
        url,
        data={
            "course_subject_id": str(link_id),
            "reason": "Evaluación trimestral",
            f"score_{data['student_one']}": "85",
            f"note_{data['student_one']}": "Buen desempeño",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Notas guardadas" in response.get_data(as_text=True)

    with app.app_context():
        grade = SubjectGrade.query.filter_by(student_id=data["student_one"]).first()
        assert grade is not None
        assert grade.score == 85
        assert grade.observations == "Buen desempeño"
        changes = GradeChange.query.filter_by(student_id=data["student_one"]).all()
        assert len(changes) == 1
        assert changes[0].new_score == 85
        assert changes[0].reason == "Evaluación trimestral"

    client.post(
        url,
        data={
            "course_subject_id": str(link_id),
            "reason": "Corrección de acta",
            f"score_{data['student_one']}": "91",
        },
        follow_redirects=True,
    )
    with app.app_context():
        changes = (
            GradeChange.query.filter_by(student_id=data["student_one"])
            .order_by(GradeChange.id)
            .all()
        )
        assert len(changes) == 2
        assert changes[-1].previous_score == 85
        assert changes[-1].new_score == 91
        grade_id = changes[-1].subject_grade_id

    response = client.post(
        f"/admin/academico/notas/{grade_id}/eliminar",
        data={"reason": "Duplicado en el acta"},
        follow_redirects=True,
    )
    assert "Nota eliminada" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(SubjectGrade, grade_id) is None
        last = (
            GradeChange.query.filter_by(student_id=data["student_one"])
            .order_by(GradeChange.id.desc())
            .first()
        )
        assert last.previous_score == 91
        assert last.new_score is None
        assert last.reason == "Duplicado en el acta"



def test_closed_trimester_blocks_grade_changes(app, client, data):
    year_id, subject_id, trimester_id = _open_academic_panel(app, client)
    client.post(
        "/admin/academico/asignaciones",
        data={"course_id": data["course_one"], "subject_id": subject_id},
        follow_redirects=True,
    )
    with app.app_context():
        link_id = CourseSubject.query.filter_by(
            course_id=data["course_one"], subject_id=subject_id
        ).first().id

    url = (
        f"/admin/academico/notas?anio={year_id}&trimestre={trimester_id}"
        f"&asignacion={link_id}"
    )
    client.post(
        url,
        data={
            "course_subject_id": str(link_id),
            f"score_{data['student_one']}": "70",
        },
        follow_redirects=True,
    )
    client.post(
        f"/admin/academico/trimestres/{trimester_id}/cerrar", follow_redirects=True
    )

    response = client.post(
        url,
        data={
            "course_subject_id": str(link_id),
            f"score_{data['student_one']}": "95",
        },
        follow_redirects=True,
    )
    assert "cerrado" in response.get_data(as_text=True)
    with app.app_context():
        grade = SubjectGrade.query.filter_by(student_id=data["student_one"]).first()
        assert grade.score == 70


def test_teacher_cannot_open_academic_panel(client):
    login(client, "docente@test.local")
    assert client.get("/admin/academico/").status_code == 403
    assert client.get("/admin/academico/notas").status_code == 403


def test_observations_save_and_can_be_removed(app, client, data):
    year_id, _subject_id, trimester_id = _open_academic_panel(app, client)
    url = (
        f"/admin/academico/observaciones?anio={year_id}"
        f"&trimestre={trimester_id}&curso={data['course_one']}"
    )
    response = client.post(
        url,
        data={
            "course_id": str(data["course_one"]),
            f"body_{data['student_one']}": "Demuestra interés y participa.",
            f"visible_{data['student_one']}": "1",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Observaciones actualizadas" in response.get_data(as_text=True)

    with app.app_context():
        row = AcademicObservation.query.filter_by(
            student_id=data["student_one"], trimester_id=trimester_id
        ).first()
        assert row is not None
        assert row.body == "Demuestra interés y participa."
        assert row.is_visible_to_parents is True

    client.post(
        url,
        data={
            "course_id": str(data["course_one"]),
            f"body_{data['student_one']}": "",
        },
        follow_redirects=True,
    )
    with app.app_context():
        assert (
            AcademicObservation.query.filter_by(
                student_id=data["student_one"], trimester_id=trimester_id
            ).first()
            is None
        )



def test_parent_sees_subject_grades_and_visible_observations(app, client, data):
    with app.app_context():
        db.session.add(
            AcademicConfig(
                id=1,
                min_score=0,
                max_score=100,
                passing_score=51,
                decimals=0,
            )
        )
        year = SchoolYear(name="2026", is_active=True)
        first = Trimester(school_year=year, number=1)
        second = Trimester(school_year=year, number=2)
        subject = Subject(name="Historia", code="HIS")
        db.session.add_all([year, subject])
        db.session.flush()
        link = CourseSubject(
            course_id=data["course_one"], subject_id=subject.id, weekly_hours=3
        )
        db.session.add(link)
        db.session.flush()
        db.session.add_all(
            [
                SubjectGrade(
                    student_id=data["student_one"],
                    course_subject_id=link.id,
                    trimester_id=first.id,
                    score=90,
                    observations="Excelente participación",
                ),
                AcademicObservation(
                    student_id=data["student_one"],
                    trimester_id=first.id,
                    course_id=data["course_one"],
                    body="Participa activamente en clase",
                    is_visible_to_parents=True,
                ),
                AcademicObservation(
                    student_id=data["student_one"],
                    trimester_id=second.id,
                    course_id=data["course_one"],
                    body="Comentario interno confidencial",
                    is_visible_to_parents=False,
                ),
            ]
        )
        db.session.commit()

    login(client, "tutor@test.local")
    body = client.get(f"/portal/hijos/{data['student_one']}").get_data(as_text=True)
    assert "Historia" in body
    assert "90" in body
    assert "Excelente participación" in body
    assert "Participa activamente en clase" in body
    assert "Comentario interno confidencial" not in body

