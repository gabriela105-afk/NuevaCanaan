"""Panel de docentes: cursos asignados, tareas, asistencia y calificaciones."""

from __future__ import annotations

from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    ASSIGNMENT_KINDS,
    ATTENDANCE_STATUSES,
    ANNOUNCEMENT_CATEGORIES,
    PRIORITIES,
    Announcement,
    AnnouncementRecipient,
    Assignment,
    Attendance,
    Course,
    Event,
    Grade,
    Message,
    utcnow,
)
from ..utils import (
    choices,
    clean,
    clean_multiline,
    notify_announcement,
    parse_date,
    parse_float,
    record_audit,
    role_required,
)

teachers_bp = Blueprint("teachers", __name__, url_prefix="/docentes")


def _profile():
    profile = current_user.teacher_profile
    if profile is None:
        abort(403)
    return profile


def _own_course(course_id: int) -> Course:
    """Verifica que el curso esté realmente asignado al docente autenticado."""
    course = db.session.get(Course, course_id)
    if course is None:
        abort(404)
    if course.id not in {c.id for c in _profile().courses}:
        current_app.logger.warning(
            "Docente %s intentó acceder al curso %s", current_user.id, course_id
        )
        abort(403)
    return course


@teachers_bp.get("/")
@login_required
@role_required("teacher")
def dashboard():
    profile = _profile()
    courses = profile.courses
    today = date.today()

    assignments = (
        Assignment.query.filter(Assignment.teacher_id == profile.id)
        .order_by(Assignment.due_date.desc(), Assignment.id.desc())
        .limit(8)
        .all()
    )
    events = (
        Event.query.filter(Event.start_date >= today, Event.is_cancelled.is_(False))
        .order_by(Event.start_date)
        .limit(5)
        .all()
    )
    events = [event for event in events if event.is_visible_to(current_user)]
    unread_messages = Message.query.filter_by(
        recipient_id=current_user.id, read_at=None
    ).count()

    return render_template(
        "teachers/dashboard.html",
        profile=profile,
        courses=courses,
        assignments=assignments,
        events=events,
        unread_messages=unread_messages,
        today=today,
    )


@teachers_bp.get("/cursos")
@login_required
@role_required("teacher")
def courses():
    profile = _profile()
    return render_template(
        "teachers/courses.html",
        profile=profile,
        courses=profile.courses,
        today=date.today(),
    )


@teachers_bp.route("/cursos/<int:course_id>/tareas/nueva", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def assignment_new(course_id: int):
    course = _own_course(course_id)
    form = {
        "title": "",
        "description": "",
        "kind": "tarea",
        "subject": "",
        "due_date": "",
        "max_score": "",
    }

    if request.method == "POST":
        form = {
            "title": clean(request.form.get("title"), 180),
            "description": clean_multiline(request.form.get("description"), 2000),
            "kind": choices(request.form.get("kind"), ASSIGNMENT_KINDS, "tarea"),
            "subject": clean(request.form.get("subject"), 80),
            "due_date": clean(request.form.get("due_date"), 10),
            "max_score": clean(request.form.get("max_score"), 10),
        }
        due_date, date_error = parse_date(form["due_date"], "fecha de entrega")
        max_score, score_error = parse_float(form["max_score"], "puntaje máximo")

        errors = [e for e in (date_error, score_error) if e]
        if len(form["title"]) < 5:
            errors.append("El título debe tener al menos 5 caracteres.")
        if max_score is not None and max_score <= 0:
            errors.append("El puntaje máximo debe ser mayor que cero.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            assignment = Assignment(
                course_id=course.id,
                teacher_id=_profile().id,
                title=form["title"],
                description=form["description"] or None,
                kind=form["kind"],
                subject=form["subject"] or None,
                due_date=due_date,
                max_score=max_score,
            )
            db.session.add(assignment)
            record_audit(
                "assignment_create",
                "assignment",
                None,
                f"{course.label}: {form['title']}",
            )
            db.session.commit()
            flash("Tarea o actividad registrada correctamente.", "success")
            return redirect(url_for("teachers.course_detail", course_id=course.id))

    return render_template(
        "teachers/assignment_form.html", course=course, assignment=None, form=form,
        kinds=ASSIGNMENT_KINDS,
    )


@teachers_bp.route(
    "/cursos/<int:course_id>/tareas/<int:assignment_id>/editar", methods=["GET", "POST"]
)
@login_required
@role_required("teacher")
def assignment_edit(course_id: int, assignment_id: int):
    course = _own_course(course_id)
    assignment = db.session.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course.id:
        abort(404)
    if assignment.teacher_id not in (None, _profile().id):
        flash("Sólo el docente responsable puede editar esta actividad.", "error")
        return redirect(url_for("teachers.course_detail", course_id=course.id))

    form = {
        "title": assignment.title,
        "description": assignment.description or "",
        "kind": assignment.kind,
        "subject": assignment.subject or "",
        "due_date": assignment.due_date.isoformat() if assignment.due_date else "",
        "max_score": "" if assignment.max_score is None else assignment.max_score,
    }

    if request.method == "POST":
        form = {
            "title": clean(request.form.get("title"), 180),
            "description": clean_multiline(request.form.get("description"), 2000),
            "kind": choices(request.form.get("kind"), ASSIGNMENT_KINDS, "tarea"),
            "subject": clean(request.form.get("subject"), 80),
            "due_date": clean(request.form.get("due_date"), 10),
            "max_score": clean(request.form.get("max_score"), 10),
        }
        due_date, date_error = parse_date(form["due_date"], "fecha de entrega")
        max_score, score_error = parse_float(form["max_score"], "puntaje máximo")
        errors = [e for e in (date_error, score_error) if e]
        if len(form["title"]) < 5:
            errors.append("El título debe tener al menos 5 caracteres.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            assignment.title = form["title"]
            assignment.description = form["description"] or None
            assignment.kind = form["kind"]
            assignment.subject = form["subject"] or None
            assignment.due_date = due_date
            assignment.max_score = max_score
            record_audit("assignment_update", "assignment", assignment.id, form["title"])
            db.session.commit()
            flash("Actividad actualizada.", "success")
            return redirect(url_for("teachers.course_detail", course_id=course.id))

    return render_template(
        "teachers/assignment_form.html", course=course, assignment=assignment,
        form=form, kinds=ASSIGNMENT_KINDS,
    )


@teachers_bp.post("/cursos/<int:course_id>/tareas/<int:assignment_id>/eliminar")
@login_required
@role_required("teacher")
def assignment_delete(course_id: int, assignment_id: int):
    course = _own_course(course_id)
    assignment = db.session.get(Assignment, assignment_id)
    if assignment is None or assignment.course_id != course.id:
        abort(404)
    if assignment.teacher_id not in (None, _profile().id):
        abort(403)
    db.session.delete(assignment)
    record_audit("assignment_delete", "assignment", assignment_id, assignment.title)
    db.session.commit()
    flash("Actividad eliminada.", "info")
    return redirect(url_for("teachers.course_detail", course_id=course.id))


@teachers_bp.get("/cursos/<int:course_id>")
@login_required
@role_required("teacher")
def course_detail(course_id: int):
    course = _own_course(course_id)
    students = course.active_students
    assignments = (
        Assignment.query.filter_by(course_id=course.id)
        .order_by(Assignment.due_date.desc(), Assignment.id.desc())
        .all()
    )
    today_records = {
        record.student_id: record
        for record in Attendance.query.filter_by(
            course_id=course.id, date=date.today()
        ).all()
    }
    subjects = sorted(
        {
            assignment.subject
            for assignment in course.assignments
            if assignment.teacher_id == _profile().id and assignment.subject
        }
    )

    return render_template(
        "teachers/course_detail.html",
        course=course,
        students=students,
        assignments=assignments,
        today_records=today_records,
        subjects=subjects,
        today=date.today(),
        kinds=ASSIGNMENT_KINDS,
    )


@teachers_bp.route("/cursos/<int:course_id>/asistencia", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def attendance(course_id: int):
    course = _own_course(course_id)
    students = course.active_students

    selected_date, date_error = parse_date(
        request.form.get("date") or request.args.get("fecha"), "fecha"
    )
    selected_date = selected_date or date.today()
    if date_error:
        flash(date_error, "error")

    if request.method == "POST":
        saved = 0
        absences = 0
        for student in students:
            status = request.form.get(f"status_{student.id}")
            if status not in ATTENDANCE_STATUSES:
                continue
            record = Attendance.query.filter_by(
                student_id=student.id, course_id=course.id, date=selected_date
            ).first()
            if record is None:
                record = Attendance(
                    student_id=student.id, course_id=course.id, date=selected_date
                )
                db.session.add(record)
            record.status = status
            record.notes = clean(request.form.get(f"notes_{student.id}"), 200) or None
            record.recorded_by = current_user.id
            saved += 1
            if status == "ausente":
                absences += 1
        record_audit(
            "attendance_save",
            "course",
            course.id,
            f"{selected_date.isoformat()}: {saved} registros",
        )
        db.session.commit()
        flash(
            f"Se guardaron {saved} registros de asistencia para el "
            f"{selected_date.isoformat()}."
            + (f" Se registraron {absences} inasistencias." if absences else ""),
            "success",
        )
        return redirect(
            url_for("teachers.attendance", course_id=course.id, fecha=selected_date.isoformat())
        )

    existing = {
        record.student_id: record
        for record in Attendance.query.filter_by(
            course_id=course.id, date=selected_date
        ).all()
    }
    history = (
        Attendance.query.filter_by(course_id=course.id)
        .order_by(Attendance.date.desc())
        .limit(30)
        .all()
    )
    return render_template(
        "teachers/attendance.html",
        course=course,
        students=students,
        existing=existing,
        selected_date=selected_date,
        history=history,
        statuses=ATTENDANCE_STATUSES,
    )


@teachers_bp.route("/cursos/<int:course_id>/notas", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def grades(course_id: int):
    course = _own_course(course_id)
    students = course.active_students
    assignments = (
        Assignment.query.filter_by(course_id=course.id)
        .order_by(Assignment.due_date.desc())
        .all()
    )
    student_ids = {student.id for student in students}

    if request.method == "POST":
        try:
            student_id = int(request.form.get("student_id", "0"))
        except (TypeError, ValueError):
            student_id = 0
        assignment_raw = request.form.get("assignment_id") or ""
        try:
            assignment_id = int(assignment_raw) if assignment_raw else None
        except ValueError:
            assignment_id = None
        period = clean(request.form.get("period"), 20) or "1"
        score, score_error = parse_float(request.form.get("score"), "nota")
        max_score, max_error = parse_float(
            request.form.get("max_score"), "puntaje máximo"
        )
        observations = clean(request.form.get("observations"), 200)

        errors = [e for e in (score_error, max_error) if e]
        if student_id not in student_ids:
            errors.append("El estudiante no pertenece a este curso.")
        if assignment_id is not None:
            assignment = db.session.get(Assignment, assignment_id)
            if assignment is None or assignment.course_id != course.id:
                errors.append("La evaluación seleccionada no pertenece al curso.")
        if score is None or score < 0:
            errors.append("Ingrese una nota válida (mayor o igual a cero).")
        max_score = max_score or 100.0
        if score is not None and score > max_score:
            errors.append("La nota no puede superar el puntaje máximo.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            record = Grade.query.filter_by(
                student_id=student_id, assignment_id=assignment_id, period=period
            ).first()
            if record is None:
                record = Grade(
                    student_id=student_id,
                    course_id=course.id,
                    assignment_id=assignment_id,
                    period=period,
                    score=score,
                    max_score=max_score,
                    recorded_by=current_user.id,
                )
                db.session.add(record)
            else:
                record.score = score
                record.max_score = max_score
                record.recorded_by = current_user.id
            record.observations = observations or None
            db.session.flush()
            record_audit("grade_save", "grade", record.id, f"{course.label}: {score}")
            db.session.commit()
            flash("Calificación registrada correctamente.", "success")
            return redirect(url_for("teachers.grades", course_id=course.id))

    records = (
        Grade.query.filter_by(course_id=course.id)
        .order_by(Grade.period, Grade.created_at)
        .all()
    )
    return render_template(
        "teachers/grades.html",
        course=course,
        students=students,
        assignments=assignments,
        records=records,
    )


@teachers_bp.get("/comunicados")
@login_required
@role_required("teacher")
def announcements():
    own = (
        Announcement.query.filter_by(author_id=current_user.id)
        .order_by(Announcement.created_at.desc())
        .all()
    )
    return render_template("teachers/announcements.html", announcements=own)


@teachers_bp.route("/comunicados/nuevo", methods=["GET", "POST"])
@login_required
@role_required("teacher")
def announcement_new():
    courses = _profile().courses
    form = {
        "title": "",
        "summary": "",
        "body": "",
        "category": "academico",
        "priority": "normal",
        "expires_at": "",
        "course_ids": [courses[0].id] if courses else [],
    }

    if request.method == "POST":
        course_ids: list[int] = []
        for value in request.form.getlist("course_ids"):
            try:
                course_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        form = {
            "title": clean(request.form.get("title"), 180),
            "summary": clean(request.form.get("summary"), 300),
            "body": clean_multiline(request.form.get("body"), 4000),
            "category": choices(
                request.form.get("category"), ANNOUNCEMENT_CATEGORIES, "academico"
            ),
            "priority": choices(request.form.get("priority"), PRIORITIES, "normal"),
            "expires_at": clean(request.form.get("expires_at"), 10),
            "course_ids": course_ids,
        }
        expires_at, date_error = parse_date(form["expires_at"], "fecha de vencimiento")

        allowed_course_ids = {course.id for course in courses}
        errors = [date_error] if date_error else []
        if len(form["title"]) < 5:
            errors.append("El título del aviso debe tener al menos 5 caracteres.")
        if len(form["body"]) < 15:
            errors.append("El contenido del aviso debe tener al menos 15 caracteres.")
        if not course_ids:
            errors.append("Seleccione al menos un curso destinatario.")
        if not set(course_ids).issubset(allowed_course_ids):
            errors.append("Sólo puede publicar avisos en los cursos que tiene asignados.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            announcement = Announcement(
                title=form["title"],
                summary=form["summary"] or None,
                body=form["body"],
                category=form["category"],
                priority=form["priority"],
                status="published",
                audience="internal",
                target_role="parent",
                published_at=utcnow(),
                expires_at=expires_at,
                author_id=current_user.id,
            )
            db.session.add(announcement)
            db.session.flush()
            for course_id in course_ids:
                db.session.add(
                    AnnouncementRecipient(
                        announcement_id=announcement.id, course_id=course_id
                    )
                )
            db.session.flush()
            notify_announcement(announcement)
            record_audit(
                "announcement_teacher_create",
                "announcement",
                announcement.id,
                announcement.title,
            )
            db.session.commit()
            flash("Aviso publicado para los cursos seleccionados.", "success")
            return redirect(url_for("teachers.announcements"))

    return render_template(
        "teachers/announcement_form.html",
        courses=courses,
        form=form,
        categories=ANNOUNCEMENT_CATEGORIES,
        priorities=PRIORITIES,
    )


@teachers_bp.post("/comunicados/<int:announcement_id>/eliminar")
@login_required
@role_required("teacher")
def announcement_delete(announcement_id: int):
    announcement = db.session.get(Announcement, announcement_id)
    if announcement is None:
        abort(404)
    if announcement.author_id != current_user.id:
        abort(403)
    db.session.delete(announcement)
    record_audit(
        "announcement_delete", "announcement", announcement_id, announcement.title
    )
    db.session.commit()
    flash("Aviso eliminado.", "info")
    return redirect(url_for("teachers.announcements"))




    course = _own_course(course_id)
    students = course.active_students
    assignments = (
        Assignment.query.filter_by(course_id=course.id)
        .order_by(Assignment.due_date.desc(), Assignment.id.desc())
        .all()
    )
    today_records = {
        record.student_id: record
        for record in Attendance.query.filter_by(
            course_id=course.id, date=date.today()
        ).all()
    }
    subjects = sorted(
        {
            assignment.subject
            for assignment in course.assignments
            if assignment.teacher_id == _profile().id and assignment.subject
        }
    )

    return render_template(
        "teachers/course_detail.html",
        course=course,
        students=students,
        assignments=assignments,
        today_records=today_records,
        subjects=subjects,
        today=date.today(),
        kinds=ASSIGNMENT_KINDS,
    )
