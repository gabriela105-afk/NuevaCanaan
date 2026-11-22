"""Panel de gestión académica (dirección y administración).

Permite configurar la escala institucional, los años escolares y trimestres,
las materias y su asignación a cursos, y registrar notas y observaciones con
auditoría de cada modificación.

Reglas de privacidad:
* las notas nunca se muestran en páginas abiertas;
* sólo el personal (administración/dirección) accede a este panel;
* cada cambio de nota queda registrado en ``GradeChange``.
"""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    AcademicConfig,
    AcademicObservation,
    Course,
    CourseSubject,
    GradeChange,
    SchoolYear,
    Student,
    Subject,
    SubjectGrade,
    Teacher,
    Trimester,
)
from ..utils import (
    admin_required,
    clean,
    clean_multiline,
    parse_date,
    parse_float,
    record_audit,
    staff_required,
)

academic_bp = Blueprint("academic", __name__, url_prefix="/admin/academico")


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------
def _get_or_404(model, entity_id: int | None):
    entity = db.session.get(model, entity_id) if entity_id else None
    if entity is None:
        abort(404)
    return entity


def _year_options(only_active: bool = False) -> list[tuple[int, str]]:
    query = SchoolYear.query
    if only_active:
        query = query.filter_by(is_active=True)
    return [(year.id, year.name) for year in query.order_by(SchoolYear.name.desc())]


def _trimester_options(year_id: int | None = None) -> list[tuple[int, str]]:
    query = Trimester.query
    if year_id:
        query = query.filter_by(school_year_id=year_id)
    return [
        (trimester.id, trimester.full_label)
        for trimester in query.join(SchoolYear)
        .order_by(SchoolYear.name.desc(), Trimester.number)
    ]


def _selected_year() -> SchoolYear | None:
    year_id = request.args.get("anio", type=int)
    if year_id:
        return db.session.get(SchoolYear, year_id)
    return (
        SchoolYear.query.filter_by(is_active=True)
        .order_by(SchoolYear.name.desc())
        .first()
        or SchoolYear.query.order_by(SchoolYear.name.desc()).first()
    )


def _selected_trimester(year: SchoolYear | None) -> Trimester | None:
    trimester_id = request.args.get("trimestre", type=int)
    if trimester_id:
        return db.session.get(Trimester, trimester_id)
    if year is not None:
        return year.current_trimester or (
            year.trimesters[0] if year.trimesters else None
        )
    return None


def _enrolled_students(course: Course) -> list[Student]:
    return sorted(course.active_students, key=lambda student: student.full_name)


def _course_options() -> list[tuple[int, str]]:
    return [
        (course.id, course.label)
        for course in Course.query.filter_by(is_active=True)
        .order_by(Course.academic_year.desc(), Course.name, Course.parallel)
    ]


def _teacher_options() -> list[tuple[int, str]]:
    teachers = Teacher.query.order_by(Teacher.id).all()
    return [
        (teacher.id, teacher.user.full_name if teacher.user else f"Docente {teacher.id}")
        for teacher in teachers
    ]


def _subject_options() -> list[tuple[int, str]]:
    return [
        (subject.id, subject.label)
        for subject in Subject.query.filter_by(is_active=True).order_by(Subject.name)
    ]


def _config() -> AcademicConfig:
    return AcademicConfig.current()


# ---------------------------------------------------------------------------
# Panel general y escala de calificación
# ---------------------------------------------------------------------------
@academic_bp.get("/")
@login_required
@staff_required
def dashboard():
    year = _selected_year()
    trimester = _selected_trimester(year)
    stats = {
        "years": SchoolYear.query.count(),
        "trimesters": Trimester.query.count(),
        "subjects": Subject.query.filter_by(is_active=True).count(),
        "assignments": CourseSubject.query.filter_by(is_active=True).count(),
        "grades": SubjectGrade.query.count(),
        "observations": AcademicObservation.query.count(),
    }
    return render_template(
        "academic/index.html",
        stats=stats,
        year=year,
        trimester=trimester,
        config=_config(),
        years=_year_options(),
        recent_changes=GradeChange.query.order_by(GradeChange.created_at.desc())
        .limit(8)
        .all(),
    )


@academic_bp.route("/configuracion", methods=["GET", "POST"])
@login_required
@admin_required
def config():
    row = AcademicConfig.get_or_create()

    if request.method == "POST":
        errors: list[str] = []
        minimum, error = parse_float(request.form.get("min_score"), "nota mínima")
        if error:
            errors.append(error)
        maximum, error = parse_float(request.form.get("max_score"), "nota máxima")
        if error:
            errors.append(error)
        passing, error = parse_float(
            request.form.get("passing_score"), "nota de aprobación"
        )
        if error:
            errors.append(error)
        decimals = request.form.get("decimals", type=int)
        if decimals is None or not 0 <= decimals <= 3:
            errors.append("Los decimales deben estar entre 0 y 3.")

        if minimum is None or maximum is None or passing is None:
            errors.append("Debe completar la nota mínima, máxima y de aprobación.")
        elif maximum <= minimum:
            errors.append("La nota máxima debe ser mayor que la nota mínima.")
        elif not minimum <= passing <= maximum:
            errors.append("La nota de aprobación debe estar dentro de la escala.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            row.min_score = minimum
            row.max_score = maximum
            row.passing_score = passing
            row.decimals = decimals
            row.updated_by = current_user.id
            record_audit(
                "academic_config_update",
                "academic_config",
                row.id,
                f"Escala {minimum} a {maximum}, aprueba desde {passing}",
            )
            db.session.commit()
            flash("Escala de calificación guardada correctamente.", "success")
            return redirect(url_for("academic.config"))

    return render_template("academic/config.html", config=row)



# ---------------------------------------------------------------------------
# Años escolares y trimestres
# ---------------------------------------------------------------------------
@academic_bp.route("/anios", methods=["GET", "POST"])
@login_required
@staff_required
def years():
    if request.method == "POST":
        name = clean(request.form.get("name"), 40)
        start, start_error = parse_date(request.form.get("start_date"), "inicio")
        end, end_error = parse_date(request.form.get("end_date"), "fin")
        if not name:
            flash("Indique el nombre del año escolar (por ejemplo 2027).", "error")
        elif start_error or end_error:
            flash(start_error or end_error, "error")
        elif start and end and end < start:
            flash("La fecha de cierre no puede ser anterior al inicio.", "error")
        elif SchoolYear.query.filter(func.lower(SchoolYear.name) == name.lower()).first():
            flash("Ya existe un año escolar con ese nombre.", "error")
        else:
            year = SchoolYear(
                name=name,
                start_date=start,
                end_date=end,
                is_active=bool(request.form.get("is_active")),
            )
            db.session.add(year)
            db.session.flush()
            for number in (1, 2, 3):
                db.session.add(Trimester(school_year_id=year.id, number=number))
            record_audit("school_year_create", "school_year", year.id, year.name)
            db.session.commit()
            flash("Año escolar creado con sus tres trimestres.", "success")
            return redirect(url_for("academic.years", anio=year.id))

    selected = _selected_year()
    trimesters = (
        Trimester.query.filter_by(school_year_id=selected.id)
        .order_by(Trimester.number)
        .all()
        if selected
        else []
    )
    return render_template(
        "academic/years.html",
        years=SchoolYear.query.order_by(SchoolYear.name.desc()).all(),
        year=selected,
        trimesters=trimesters,
    )


@academic_bp.post("/anios/<int:year_id>/editar")
@login_required
@admin_required
def year_edit(year_id: int):
    year = _get_or_404(SchoolYear, year_id)
    name = clean(request.form.get("name"), 40)
    start, start_error = parse_date(request.form.get("start_date"), "inicio")
    end, end_error = parse_date(request.form.get("end_date"), "fin")

    if not name:
        flash("El nombre del año escolar es obligatorio.", "error")
    elif start_error or end_error:
        flash(start_error or end_error, "error")
    elif start and end and end < start:
        flash("La fecha de cierre no puede ser anterior al inicio.", "error")
    else:
        duplicate = SchoolYear.query.filter(
            func.lower(SchoolYear.name) == name.lower(), SchoolYear.id != year.id
        ).first()
        if duplicate:
            flash("Ya existe otro año escolar con ese nombre.", "error")
        else:
            year.name = name
            year.start_date = start
            year.end_date = end
            year.is_active = bool(request.form.get("is_active"))
            record_audit("school_year_update", "school_year", year.id, name)
            db.session.commit()
            flash("Año escolar actualizado.", "success")
    return redirect(url_for("academic.years", anio=year.id))


@academic_bp.post("/anios/<int:year_id>/eliminar")
@login_required
@admin_required
def year_delete(year_id: int):
    year = _get_or_404(SchoolYear, year_id)
    if any(t.grades or t.observations for t in year.trimesters):
        flash(
            "No se puede eliminar el año porque tiene calificaciones u observaciones "
            "registradas. Desactívelo en su lugar.",
            "error",
        )
        return redirect(url_for("academic.years", anio=year.id))
    name = year.name
    db.session.delete(year)
    record_audit("school_year_delete", "school_year", year_id, name)
    db.session.commit()
    flash("Año escolar eliminado.", "info")
    return redirect(url_for("academic.years"))


@academic_bp.post("/anios/<int:year_id>/trimestres")
@login_required
@staff_required
def trimester_create(year_id: int):
    year = _get_or_404(SchoolYear, year_id)
    number = request.form.get("number", type=int)
    start, start_error = parse_date(request.form.get("start_date"), "inicio")
    end, end_error = parse_date(request.form.get("end_date"), "fin")
    if number not in (1, 2, 3):
        flash("El trimestre debe ser 1, 2 o 3.", "error")
    elif start_error or end_error:
        flash(start_error or end_error, "error")
    elif start and end and end < start:
        flash("El cierre del trimestre no puede ser anterior al inicio.", "error")
    elif Trimester.query.filter_by(school_year_id=year.id, number=number).first():
        flash("Ese trimestre ya existe en el año escolar.", "error")
    else:
        trimester = Trimester(
            school_year_id=year.id,
            number=number,
            start_date=start,
            end_date=end,
        )
        db.session.add(trimester)
        db.session.flush()
        record_audit(
            "trimester_create", "trimester", trimester.id, trimester.full_label
        )
        db.session.commit()
        flash("Trimestre agregado.", "success")
    return redirect(url_for("academic.years", anio=year.id))


@academic_bp.post("/trimestres/<int:trimester_id>/editar")
@login_required
@staff_required
def trimester_edit(trimester_id: int):
    trimester = _get_or_404(Trimester, trimester_id)
    start, start_error = parse_date(request.form.get("start_date"), "inicio")
    end, end_error = parse_date(request.form.get("end_date"), "fin")
    number = request.form.get("number", type=int)

    if start_error or end_error:
        flash(start_error or end_error, "error")
    elif start and end and end < start:
        flash("El cierre del trimestre no puede ser anterior al inicio.", "error")
    elif number not in (1, 2, 3):
        flash("El trimestre debe ser 1, 2 o 3.", "error")
    else:
        duplicate = Trimester.query.filter(
            Trimester.school_year_id == trimester.school_year_id,
            Trimester.number == number,
            Trimester.id != trimester.id,
        ).first()
        if duplicate:
            flash("Ya existe otro trimestre con ese número.", "error")
        else:
            trimester.number = number
            trimester.start_date = start
            trimester.end_date = end
            record_audit(
                "trimester_update", "trimester", trimester.id, trimester.full_label
            )
            db.session.commit()
            flash("Trimestre actualizado.", "success")
    return redirect(url_for("academic.years", anio=trimester.school_year_id))


@academic_bp.post("/trimestres/<int:trimester_id>/cerrar")
@login_required
@admin_required
def trimester_toggle(trimester_id: int):
    trimester = _get_or_404(Trimester, trimester_id)
    trimester.is_closed = not trimester.is_closed
    record_audit(
        "trimester_close" if trimester.is_closed else "trimester_open",
        "trimester",
        trimester.id,
        trimester.full_label,
    )
    db.session.commit()
    flash(
        "Trimestre cerrado: las notas quedan bloqueadas."
        if trimester.is_closed
        else "Trimestre reabierto para edición.",
        "info",
    )
    return redirect(url_for("academic.years", anio=trimester.school_year_id))


# ---------------------------------------------------------------------------
# Materias
# ---------------------------------------------------------------------------
@academic_bp.route("/materias", methods=["GET", "POST"])
@login_required
@staff_required
def subjects():
    if request.method == "POST":
        name = clean(request.form.get("name"), 100)
        code = clean(request.form.get("code"), 20)
        description = clean(request.form.get("area"), 60)
        if not name:
            flash("El nombre de la materia es obligatorio.", "error")
        elif code and Subject.query.filter(func.lower(Subject.code) == code.lower()).first():
            flash("Ya existe una materia con ese código.", "error")
        else:
            subject = Subject(name=name, code=code or None, area=description or None)
            db.session.add(subject)
            db.session.flush()
            record_audit("subject_create", "subject", subject.id, subject.name)
            db.session.commit()
            flash("Materia registrada.", "success")
            return redirect(url_for("academic.subjects"))

    return render_template(
        "academic/subjects.html",
        subjects=Subject.query.order_by(Subject.name).all(),
        usage=dict(
            db.session.query(CourseSubject.subject_id, func.count(CourseSubject.id))
            .group_by(CourseSubject.subject_id)
            .all()
        ),
    )


@academic_bp.post("/materias/<int:subject_id>/editar")
@login_required
@staff_required
def subject_edit(subject_id: int):
    subject = _get_or_404(Subject, subject_id)
    name = clean(request.form.get("name"), 100)
    code = clean(request.form.get("code"), 20)
    description = clean(request.form.get("area"), 60)

    if not name:
        flash("El nombre de la materia es obligatorio.", "error")
    else:
        duplicate = (
            Subject.query.filter(
                func.lower(Subject.code) == code.lower(), Subject.id != subject.id
            ).first()
            if code
            else None
        )
        if duplicate:
            flash("Ya existe otra materia con ese código.", "error")
        else:
            subject.name = name
            subject.code = code or None
            subject.area = description or None
            subject.is_active = bool(request.form.get("is_active"))
            record_audit("subject_update", "subject", subject.id, subject.name)
            db.session.commit()
            flash("Materia actualizada.", "success")
    return redirect(url_for("academic.subjects"))


@academic_bp.post("/materias/<int:subject_id>/eliminar")
@login_required
@admin_required
def subject_delete(subject_id: int):
    subject = _get_or_404(Subject, subject_id)
    if subject.course_links or subject.grades:
        flash(
            "La materia tiene asignaciones o notas registradas; desactívela en lugar "
            "de eliminarla.",
            "error",
        )
        return redirect(url_for("academic.subjects"))
    name = subject.name
    db.session.delete(subject)
    record_audit("subject_delete", "subject", subject_id, name)
    db.session.commit()
    flash("Materia eliminada.", "info")
    return redirect(url_for("academic.subjects"))



# ---------------------------------------------------------------------------
# Asignación de materias a cursos
# ---------------------------------------------------------------------------
@academic_bp.route("/asignaciones", methods=["GET", "POST"])
@login_required
@staff_required
def assignments():
    if request.method == "POST":
        course_id = request.form.get("course_id", type=int)
        subject_id = request.form.get("subject_id", type=int)
        teacher_id = request.form.get("teacher_id", type=int)
        weekly_hours = request.form.get("weekly_hours", type=int)
        course = db.session.get(Course, course_id) if course_id else None
        subject = db.session.get(Subject, subject_id) if subject_id else None

        if course is None or subject is None:
            flash("Seleccione un curso y una materia válidos.", "error")
        elif weekly_hours is not None and not 0 <= weekly_hours <= 40:
            flash("La carga horaria semanal debe estar entre 0 y 40.", "error")
        else:
            link = CourseSubject.query.filter_by(
                course_id=course.id, subject_id=subject.id
            ).first()
            if link is None:
                link = CourseSubject(course_id=course.id, subject_id=subject.id)
                db.session.add(link)
            link.teacher_id = teacher_id
            link.weekly_hours = weekly_hours
            link.is_active = True
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                flash("No se pudo guardar la asignación (registro duplicado).", "error")
            else:
                record_audit(
                    "course_subject_save",
                    "course_subject",
                    link.id,
                    f"{course.label} - {subject.name}",
                )
                db.session.commit()
                flash("Materia asignada al curso.", "success")
                return redirect(url_for("academic.assignments", curso=course.id))

    selected_course_id = request.args.get("curso", type=int)
    selected_course = (
        db.session.get(Course, selected_course_id) if selected_course_id else None
    )
    links_query = CourseSubject.query
    if selected_course:
        links_query = links_query.filter_by(course_id=selected_course.id)
    return render_template(
        "academic/assignments.html",
        links=links_query.join(Course)
        .join(Subject)
        .order_by(
            Course.academic_year.desc(), Course.name, Course.parallel, Subject.name
        )
        .all(),
        courses=_course_options(),
        subjects=_subject_options(),
        teachers=_teacher_options(),
        selected_course=selected_course,
    )


@academic_bp.post("/asignaciones/<int:link_id>/editor")
@login_required
@staff_required
def assignment_edit(link_id: int):
    link = _get_or_404(CourseSubject, link_id)
    teacher_id = request.form.get("teacher_id", type=int)
    weekly_hours = request.form.get("weekly_hours", type=int)
    if weekly_hours is not None and not 0 <= weekly_hours <= 40:
        flash("La carga horaria semanal debe estar entre 0 y 40.", "error")
    else:
        link.teacher_id = teacher_id
        link.weekly_hours = weekly_hours
        link.is_active = bool(request.form.get("is_active"))
        record_audit(
            "course_subject_update",
            "course_subject",
            link.id,
            f"{link.course.label if link.course else ''} - "
            f"{link.subject.name if link.subject else ''}",
        )
        db.session.commit()
        flash("Asignación actualizada.", "success")
    return redirect(url_for("academic.assignments", curso=link.course_id))


@academic_bp.post("/asignaciones/<int:link_id>/eliminar")
@login_required
@admin_required
def assignment_delete(link_id: int):
    link = _get_or_404(CourseSubject, link_id)
    if link.grades:
        flash(
            "No se puede quitar la asignación porque tiene notas registradas. "
            "Desactívela en su lugar.",
            "error",
        )
        return redirect(url_for("academic.assignments", curso=link.course_id))
    course_id = link.course_id
    db.session.delete(link)
    record_audit("course_subject_delete", "course_subject", link_id, "")
    db.session.commit()
    flash("Asignación eliminada.", "info")
    return redirect(url_for("academic.assignments", curso=course_id))



# ---------------------------------------------------------------------------
# Notas por materia y trimestre
# ---------------------------------------------------------------------------
def _course_subject_options(year: SchoolYear | None) -> list[tuple[int, str]]:
    query = CourseSubject.query.join(Course).filter(CourseSubject.is_active.is_(True))
    if year is not None and str(year.name).isdigit():
        query = query.filter(Course.academic_year == int(year.name))
    return [
        (link.id, link.label)
        for link in query.order_by(Course.name, Course.parallel)
    ]


@academic_bp.route("/notas", methods=["GET", "POST"])
@login_required
@staff_required
def grades():
    config = _config()
    year = _selected_year()
    trimester = _selected_trimester(year)
    options = _course_subject_options(year)
    if request.method == "POST":
        link_id = request.form.get("course_subject_id", type=int)
    else:
        link_id = request.args.get("asignacion", type=int)
    allowed_ids = {option[0] for option in options}
    link = db.session.get(CourseSubject, link_id) if link_id in allowed_ids else None

    if not config.is_configured:
        flash(
            "Antes de registrar notas configure la escala de calificación institucional.",
            "warning",
        )

    if request.method == "POST":
        if link is None or trimester is None:
            flash("Seleccione el trimestre y la materia del curso.", "error")
        elif trimester.is_closed:
            flash("El trimestre está cerrado; no se pueden modificar notas.", "error")
        elif not config.is_configured:
            flash("Configure la escala de calificación para registrar notas.", "error")
        else:
            students = _enrolled_students(link.course) if link.course else []
            reason = clean(request.form.get("reason"), 200) or (
                "Registro/actualización desde el panel académico"
            )
            pending = []
            errors: list[str] = []

            for student in students:
                raw = (request.form.get(f"score_{student.id}") or "").strip()
                note = clean(request.form.get(f"note_{student.id}"), 300)
                existing = link.grade_for(student.id, trimester.id)
                if not raw:
                    continue
                value, error = parse_float(raw, f"nota de {student.full_name}")
                if error:
                    errors.append(error)
                    continue
                valid, message = config.validate(value)
                if not valid:
                    errors.append(f"{student.full_name}: {message}")
                    continue
                pending.append((student, existing, value, note))

            if errors:
                for message in errors:
                    flash(message, "error")
            else:
                _apply_grades(link, trimester, pending, reason)
                record_audit(
                    "grades_save",
                    "course_subject",
                    link.id,
                    f"{link.label} · {trimester.full_label} · {len(pending)} notas",
                )
                db.session.commit()
                flash(f"Notas guardadas ({len(pending)} estudiantes).", "success")
                return redirect(
                    url_for(
                        "academic.grades",
                        anio=year.id if year else None,
                        trimestre=trimester.id,
                        asignacion=link.id,
                    )
                )

    students = _enrolled_students(link.course) if link and link.course else []
    existing_grades = {
        grade.student_id: grade
        for grade in (link.grades if link and trimester else [])
        if grade.trimester_id == (trimester.id if trimester else None)
    }
    return render_template(
        "academic/grades.html",
        config=config,
        year=year,
        trimester=trimester,
        years=_year_options(),
        trimesters=_trimester_options(year.id if year else None),
        options=options,
        link=link,
        students=students,
        existing_grades=existing_grades,
    )



def _apply_grades(link, trimester, pending, reason: str) -> None:
    """Crea o actualiza notas registrando cada cambio en ``GradeChange``."""
    for student, existing, value, note in pending:
        if existing is None:
            grade = SubjectGrade(
                student_id=student.id,
                course_subject_id=link.id,
                trimester_id=trimester.id,
                score=value,
                observations=note,
                recorded_by=current_user.id,
                updated_by=current_user.id,
            )
            db.session.add(grade)
            db.session.flush()
            db.session.add(
                GradeChange(
                    subject_grade_id=grade.id,
                    student_id=student.id,
                    course_subject_id=link.id,
                    trimester_id=trimester.id,
                    previous_score=None,
                    new_score=value,
                    reason=reason,
                    changed_by=current_user.id,
                )
            )
        elif existing.score != value or existing.observations != note:
            db.session.add(
                GradeChange(
                    subject_grade_id=existing.id,
                    student_id=student.id,
                    course_subject_id=link.id,
                    trimester_id=trimester.id,
                    previous_score=existing.score,
                    new_score=value,
                    reason=reason,
                    changed_by=current_user.id,
                )
            )
            existing.score = value
            existing.observations = note
            existing.updated_by = current_user.id


@academic_bp.post("/notas/<int:grade_id>/eliminar")
@login_required
@staff_required
def grade_delete(grade_id: int):
    grade = _get_or_404(SubjectGrade, grade_id)
    reason = clean(request.form.get("reason"), 200)
    if not reason:
        flash("Indique el motivo de la eliminación de la nota.", "error")
        return redirect(request.referrer or url_for("academic.grades"))
    if grade.trimester and grade.trimester.is_closed:
        flash("El trimestre está cerrado; la nota no puede eliminarse.", "error")
        return redirect(request.referrer or url_for("academic.grades"))
    db.session.add(
        GradeChange(
            subject_grade_id=None,
            student_id=grade.student_id,
            course_subject_id=grade.course_subject_id,
            trimester_id=grade.trimester_id,
            previous_score=grade.score,
            new_score=None,
            reason=reason,
            changed_by=current_user.id,
        )
    )
    record_audit("grade_delete", "subject_grade", grade.id, reason)
    db.session.delete(grade)
    db.session.commit()
    flash("Nota eliminada; la acción quedó registrada en el historial.", "info")
    return redirect(request.referrer or url_for("academic.grades"))



# ---------------------------------------------------------------------------
# Observaciones pedagógicas
# ---------------------------------------------------------------------------
@academic_bp.route("/observaciones", methods=["GET", "POST"])
@login_required
@staff_required
def observations():
    year = _selected_year()
    trimester = _selected_trimester(year)
    course_id = (
        request.form.get("course_id", type=int)
        if request.method == "POST"
        else request.args.get("curso", type=int)
    )
    course = db.session.get(Course, course_id) if course_id else None
    if course is None and year is not None:
        course = next(
            (
                c
                for c in Course.query.filter_by(is_active=True).order_by(Course.name)
                if str(year.name).isdigit()
                and c.academic_year == int(year.name)
            ),
            None,
        )

    if request.method == "POST":
        if trimester is None or course is None:
            flash("Seleccione el trimestre y el curso.", "error")
        elif trimester.is_closed:
            flash("El trimestre está cerrado; no se pueden modificar observaciones.", "error")
        else:
            students = _enrolled_students(course)
            existing = {
                row.student_id: row
                for row in AcademicObservation.query.filter_by(
                    trimester_id=trimester.id
                ).all()
            }
            changed = 0
            for student in students:
                body = clean_multiline(request.form.get(f"body_{student.id}"), 2000)
                visible = bool(request.form.get(f"visible_{student.id}"))
                row = existing.get(student.id)
                if not body:
                    if row is not None:
                        db.session.delete(row)
                        changed += 1
                    continue
                if row is None:
                    row = AcademicObservation(
                        student_id=student.id,
                        trimester_id=trimester.id,
                        course_id=course.id,
                        body=body,
                        is_visible_to_parents=visible,
                        recorded_by=current_user.id,
                    )
                    db.session.add(row)
                    changed += 1
                elif (
                    row.body != body
                    or row.is_visible_to_parents != visible
                    or row.course_id != course.id
                ):
                    row.body = body
                    row.is_visible_to_parents = visible
                    row.course_id = course.id
                    changed += 1
            record_audit(
                "observations_save",
                "course",
                course.id,
                f"{trimester.full_label} · {changed} cambios",
            )
            db.session.commit()
            flash("Observaciones actualizadas.", "success")
            return redirect(
                url_for(
                    "academic.observations",
                    anio=year.id if year else None,
                    trimestre=trimester.id,
                    curso=course.id,
                )
            )

    students = _enrolled_students(course) if course else []
    rows = {}
    if trimester is not None:
        rows = {
            row.student_id: row
            for row in AcademicObservation.query.filter_by(
                trimester_id=trimester.id
            ).all()
        }
    return render_template(
        "academic/observations.html",
        year=year,
        trimester=trimester,
        years=_year_options(),
        trimesters=_trimester_options(year.id if year else None),
        courses=_course_options(),
        course=course,
        students=students,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Historial de cambios de notas
# ---------------------------------------------------------------------------
@academic_bp.get("/historial")
@login_required
@staff_required
def history():
    year = _selected_year()
    trimester = _selected_trimester(year)
    query = GradeChange.query
    if trimester is not None:
        query = query.filter_by(trimester_id=trimester.id)
    changes = query.order_by(GradeChange.created_at.desc()).limit(300).all()
    return render_template(
        "academic/history.html",
        year=year,
        trimester=trimester,
        years=_year_options(),
        trimesters=_trimester_options(year.id if year else None),
        changes=changes,
        config=_config(),
    )

