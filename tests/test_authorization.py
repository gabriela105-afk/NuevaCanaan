"""Pruebas de autorización por rol y de aislamiento de datos entre usuarios."""

from __future__ import annotations


def login(client, email, password="ClaveSegura123"):
    return client.post("/login", data={"email": email, "password": password})


def test_parent_can_open_portal(client):
    login(client, "tutor@test.local")
    response = client.get("/portal/")
    assert response.status_code == 200
    assert "Mis hijos" in response.get_data(as_text=True)


def test_parent_sees_only_own_child(app, client, data):
    login(client, "tutor@test.local")

    own = client.get(f"/portal/hijos/{data['student_one']}")
    assert own.status_code == 200

    other = client.get(f"/portal/hijos/{data['student_two']}")
    assert other.status_code == 403


def test_second_parent_is_isolated(app, client, data):
    login(client, "tutor2@test.local")

    other = client.get(f"/portal/hijos/{data['student_one']}")
    assert other.status_code == 403

    own = client.get(f"/portal/hijos/{data['student_two']}")
    assert own.status_code == 200


def test_parent_cannot_access_admin_or_teacher_panels(client):
    login(client, "tutor@test.local")
    assert client.get("/admin/").status_code == 403
    assert client.get("/docentes/").status_code == 403
    assert client.get("/admin/usuarios").status_code == 403


def test_teacher_can_open_own_course_only(client, data):
    login(client, "docente@test.local")

    own = client.get(f"/docentes/cursos/{data['course_one']}")
    assert own.status_code == 200

    other = client.get(f"/docentes/cursos/{data['course_two']}")
    assert other.status_code == 403


def test_teacher_cannot_access_administration(client):
    login(client, "docente@test.local")
    assert client.get("/admin/").status_code == 403
    assert client.get("/portal/").status_code == 403


def test_admin_can_access_administration(client):
    login(client, "admin@test.local")
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/usuarios").status_code == 200
    assert client.get("/admin/auditoria").status_code == 200


def test_direction_has_content_access_but_not_user_management(client):
    login(client, "direccion@test.local")
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/comunicados").status_code == 200
    assert client.get("/admin/usuarios").status_code == 403


def test_teacher_cannot_grade_other_course(client, data):
    login(client, "docente@test.local")
    response = client.post(
        f"/docentes/cursos/{data['course_two']}/notas",
        data={"student_id": data["student_two"], "period": "1", "score": "90", "max_score": "100"},
    )
    assert response.status_code == 403


def test_teacher_cannot_publish_announcement_for_foreign_course(client, data):
    login(client, "docente@test.local")
    response = client.post(
        "/docentes/comunicados/nuevo",
        data={
            "title": "Aviso no permitido",
            "body": "Este aviso intenta publicarse en un curso ajeno al docente.",
            "category": "academico",
            "priority": "normal",
            "course_ids": [str(data["course_two"])],
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Sólo puede publicar avisos" in response.get_data(as_text=True)


def test_non_admin_cannot_toggle_users(client):
    login(client, "direccion@test.local")
    response = client.post("/admin/usuarios/1/estado")
    assert response.status_code == 403
