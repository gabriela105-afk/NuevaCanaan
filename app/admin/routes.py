"""Panel de administración y dirección: gestión integral de la plataforma."""

from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

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
from sqlalchemy import func, or_

from ..extensions import db
from ..models import (
    ANNOUNCEMENT_CATEGORIES,
    ANNOUNCEMENT_STATUSES,
    AUDIENCES,
    EVENT_CATEGORIES,
    PRIORITIES,
    ROLES,
    Announcement,
    AnnouncementRecipient,
    AuditLog,
    ContactMessage,
    Course,
    CourseAssignment,
    Event,
    Message,
    NewsComment,
    NewsPost,
    Notification,
    Parent,
    ParentStudent,
    Student,
    StudentEnrollment,
    Teacher,
    User,
    utcnow,
)
from ..utils import (
    SETTING_LABELS,
    admin_required,
    choices,
    clean,
    clean_multiline,
    delete_upload,
    gallery_images,
    is_valid_email,
    load_settings,
    notify_announcement,
    notify_many,
    parse_date,
    parse_int,
    parse_time,
    pending_settings,
    record_audit,
    save_settings,
    save_upload,
    staff_required,
    validate_password,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------
def _get_or_404(model, entity_id: int):
    entity = db.session.get(model, entity_id)
    if entity is None:
        abort(404)
    return entity


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [part for part in full_name.split() if part]
    if not parts:
        return "Estudiante", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


@admin_bp.get("/")
@login_required
@staff_required
def dashboard():
    today = date.today()
    stats = {
        "students": Student.query.filter_by(is_active=True).count(),
        "courses": Course.query.filter_by(is_active=True).count(),
        "parents": User.query.filter_by(role="parent", is_active=True).count(),
        "teachers": User.query.filter_by(role="teacher", is_active=True).count(),
        "announcements": Announcement.query.filter_by(status="published").count(),
        "drafts": Announcement.query.filter_by(status="draft").count(),
        "upcoming_events": Event.query.filter(
            Event.start_date >= today, Event.is_cancelled.is_(False)
        ).count(),
        "unread_contact": ContactMessage.query.filter_by(is_read=False).count(),
        "messages": Message.query.filter_by(recipient_id=current_user.id, read_at=None).count(),
        "news_published": NewsPost.query.filter_by(status="published").count(),
        "news_drafts": NewsPost.query.filter_by(status="draft").count(),
        "news_comments": NewsComment.query.filter_by(status="approved").count(),
    }
    recent_announcements = (
        Announcement.query.order_by(Announcement.created_at.desc()).limit(5).all()
    )
    upcoming_events = (
        Event.query.filter(Event.start_date >= today, Event.is_cancelled.is_(False))
        .order_by(Event.start_date)
        .limit(5)
        .all()
    )
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(8).all()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_announcements=recent_announcements,
        upcoming_events=upcoming_events,
        audit_logs=audit_logs,
        settings=load_settings(),
        pending=pending_settings(load_settings()),
        today=today,
    )


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
@admin_bp.get("/usuarios")
@login_required
@admin_required
def users():
    role = request.args.get("rol", "")
    search = clean(request.args.get("q"), 80)
    page = request.args.get("page", 1, type=int)

    query = User.query
    if role in ROLES:
        query = query.filter(User.role == role)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))

    pagination = query.order_by(User.role, User.full_name).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"] * 2, error_out=False
    )
    return render_template(
        "admin/users.html",
        pagination=pagination,
        users=pagination.items,
        role=role,
        search=search,
        roles=ROLES,
    )


@admin_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def user_new():
    form = {"full_name": "", "email": "", "phone": "", "role": "parent"}

    if request.method == "POST":
        form = {
            "full_name": clean(request.form.get("full_name"), 160),
            "email": clean(request.form.get("email"), 180).lower(),
            "phone": clean(request.form.get("phone"), 40),
            "role": choices(request.form.get("role"), ROLES, "parent"),
        }
        password = request.form.get("password") or ""
        confirmation = request.form.get("confirm_password") or ""

        errors = []
        if len(form["full_name"]) < 5:
            errors.append("Ingrese el nombre completo (mínimo 5 caracteres).")
        if not is_valid_email(form["email"]):
            errors.append("El correo electrónico no es válido.")
        elif User.query.filter_by(email=form["email"]).first():
            errors.append("Ya existe un usuario registrado con ese correo.")
        errors.extend(validate_password(password, confirmation))

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            user = User(
                full_name=form["full_name"],
                email=form["email"],
                phone=form["phone"] or None,
                role=form["role"],
                is_active=True,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            if user.role == "parent":
                db.session.add(Parent(user_id=user.id, relationship="Tutor"))
            elif user.role == "teacher":
                db.session.add(Teacher(user_id=user.id))
            record_audit("user_create", "user", user.id, f"{user.email} ({user.role})")
            db.session.commit()
            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("admin.users"))

    return render_template("admin/user_form.html", form=form, user=None, roles=ROLES)


@admin_bp.route("/usuarios/<int:user_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def user_edit(user_id: int):
    user = _get_or_404(User, user_id)
    form = {
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone or "",
        "role": user.role,
    }

    if request.method == "POST":
        form = {
            "full_name": clean(request.form.get("full_name"), 160),
            "email": clean(request.form.get("email"), 180).lower(),
            "phone": clean(request.form.get("phone"), 40),
            "role": choices(request.form.get("role"), ROLES, user.role),
        }
        errors = []
        if len(form["full_name"]) < 5:
            errors.append("Ingrese el nombre completo (mínimo 5 caracteres).")
        if not is_valid_email(form["email"]):
            errors.append("El correo electrónico no es válido.")
        duplicate = User.query.filter(
            User.email == form["email"], User.id != user.id
        ).first()
        if duplicate:
            errors.append("Otro usuario ya utiliza ese correo electrónico.")
        if user.id == current_user.id and form["role"] != user.role:
            errors.append("No puede cambiar su propio rol.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            previous_role = user.role
            user.full_name = form["full_name"]
            user.email = form["email"]
            user.phone = form["phone"] or None
            user.role = form["role"]

            if user.role == "parent" and user.parent_profile is None:
                db.session.add(Parent(user_id=user.id, relationship="Tutor"))
            if user.role == "teacher" and user.teacher_profile is None:
                db.session.add(Teacher(user_id=user.id))

            record_audit("user_update", "user", user.id, f"{previous_role} → {user.role}")
            db.session.commit()
            flash("Usuario actualizado correctamente.", "success")
            return redirect(url_for("admin.users"))

    return render_template("admin/user_form.html", form=form, user=user, roles=ROLES)


@admin_bp.post("/usuarios/<int:user_id>/estado")
@login_required
@admin_required
def user_toggle(user_id: int):
    user = _get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("No puede desactivar su propia cuenta.", "error")
        return redirect(url_for("admin.users"))

    user.is_active = not user.is_active
    if not user.is_active:
        user.failed_login_attempts = 0
        user.locked_until = None
    record_audit(
        "user_activate" if user.is_active else "user_deactivate",
        "user",
        user.id,
        user.email,
    )
    db.session.commit()
    flash(
        f"Usuario {'activado' if user.is_active else 'desactivado'} correctamente.",
        "success",
    )
    return redirect(url_for("admin.users"))


@admin_bp.post("/usuarios/<int:user_id>/contrasena")
@login_required
@admin_required
def user_reset_password(user_id: int):
    user = _get_or_404(User, user_id)
    password = request.form.get("new_password") or ""
    confirmation = request.form.get("confirm_password") or ""

    errors = validate_password(password, confirmation)
    if errors:
        for message in errors:
            flash(message, "error")
    else:
        user.set_password(password)
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.locked_until = None
        record_audit("user_password_reset", "user", user.id, user.email)
        db.session.commit()
        flash(
            "Contraseña restablecida. El usuario deberá cambiarla al ingresar.",
            "success",
        )
    return redirect(url_for("admin.user_edit", user_id=user.id))


# ---------------------------------------------------------------------------
# Estudiantes
# ---------------------------------------------------------------------------
@admin_bp.get("/estudiantes")
@login_required
@admin_required
def students():
    search = clean(request.args.get("q"), 80)
    page = request.args.get("page", 1, type=int)
    query = Student.query
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Student.first_name.ilike(like),
                Student.last_name.ilike(like),
                Student.code.ilike(like),
            )
        )
    pagination = query.order_by(Student.last_name, Student.first_name).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"] * 2, error_out=False
    )
    return render_template(
        "admin/students.html",
        pagination=pagination,
        students=pagination.items,
        search=search,
    )


def _student_form_data(form: dict) -> tuple[dict, list[str], date | None]:
    birth_date, date_error = parse_date(form.get("birth_date"), "fecha de nacimiento")
    errors = [date_error] if date_error else []
    if len(form["first_name"]) < 2:
        errors.append("Ingrese los nombres del estudiante.")
    if len(form["last_name"]) < 2:
        errors.append("Ingrese los apellidos del estudiante.")
    if len(form["code"]) < 3:
        errors.append("El código de estudiante debe tener al menos 3 caracteres.")
    return form, errors, birth_date


@admin_bp.route("/estudiantes/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def student_new():
    form = {
        "code": "", "first_name": "", "last_name": "", "birth_date": "",
        "gender": "", "notes": "", "course_id": "",
    }
    if request.method == "POST":
        form = {
            "code": clean(request.form.get("code"), 30).upper(),
            "first_name": clean(request.form.get("first_name"), 80),
            "last_name": clean(request.form.get("last_name"), 80),
            "birth_date": clean(request.form.get("birth_date"), 10),
            "gender": choices(request.form.get("gender"), ("F", "M", "Otro"), ""),
            "notes": clean_multiline(request.form.get("notes"), 1000),
            "course_id": clean(request.form.get("course_id"), 10),
        }
        form, errors, birth_date = _student_form_data(form)
        if Student.query.filter_by(code=form["code"]).first():
            errors.append("Ya existe un estudiante con ese código.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            student = Student(
                code=form["code"],
                first_name=form["first_name"],
                last_name=form["last_name"],
                birth_date=birth_date,
                gender=form["gender"] or None,
                notes=form["notes"] or None,
            )
            db.session.add(student)
            db.session.flush()
            course = db.session.get(Course, int(form["course_id"])) if form["course_id"] else None
            if course is not None:
                db.session.add(
                    StudentEnrollment(
                        student_id=student.id,
                        course_id=course.id,
                        academic_year=course.academic_year,
                        status="activo",
                    )
                )
            record_audit("student_create", "student", student.id, student.full_name)
            db.session.commit()
            flash("Estudiante registrado correctamente.", "success")
            return redirect(url_for("admin.students"))

    courses = Course.query.filter_by(is_active=True).order_by(Course.academic_year.desc()).all()
    return render_template(
        "admin/student_form.html", form=form, student=None, courses=courses
    )


@admin_bp.route("/estudiantes/<int:student_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def student_edit(student_id: int):
    student = _get_or_404(Student, student_id)
    form = {
        "code": student.code,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "birth_date": student.birth_date.isoformat() if student.birth_date else "",
        "gender": student.gender or "",
        "notes": student.notes or "",
        "course_id": "",
    }

    if request.method == "POST":
        form = {
            "code": clean(request.form.get("code"), 30).upper(),
            "first_name": clean(request.form.get("first_name"), 80),
            "last_name": clean(request.form.get("last_name"), 80),
            "birth_date": clean(request.form.get("birth_date"), 10),
            "gender": choices(request.form.get("gender"), ("F", "M", "Otro"), ""),
            "notes": clean_multiline(request.form.get("notes"), 1000),
            "course_id": "",
        }
        form, errors, birth_date = _student_form_data(form)
        duplicate = Student.query.filter(
            Student.code == form["code"], Student.id != student.id
        ).first()
        if duplicate:
            errors.append("Otro estudiante ya utiliza ese código.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            student.code = form["code"]
            student.first_name = form["first_name"]
            student.last_name = form["last_name"]
            student.birth_date = birth_date
            student.gender = form["gender"] or None
            student.notes = form["notes"] or None
            record_audit("student_update", "student", student.id, student.full_name)
            db.session.commit()
            flash("Datos del estudiante actualizados.", "success")
            return redirect(url_for("admin.students"))

    courses = Course.query.filter_by(is_active=True).order_by(Course.academic_year.desc()).all()
    return render_template(
        "admin/student_form.html", form=form, student=student, courses=courses
    )


@admin_bp.post("/estudiantes/<int:student_id>/estado")
@login_required
@admin_required
def student_toggle(student_id: int):
    student = _get_or_404(Student, student_id)
    student.is_active = not student.is_active
    record_audit(
        "student_activate" if student.is_active else "student_deactivate",
        "student",
        student.id,
        student.full_name,
    )
    db.session.commit()
    flash(
        f"Estudiante {'activado' if student.is_active else 'desactivado'} correctamente.",
        "success",
    )
    return redirect(url_for("admin.students"))


@admin_bp.post("/estudiantes/<int:student_id>/inscribir")
@login_required
@admin_required
def student_enroll(student_id: int):
    student = _get_or_404(Student, student_id)
    course_id, id_error = parse_int(request.form.get("course_id"), "curso")
    course = db.session.get(Course, course_id) if course_id else None

    if id_error or course is None:
        flash("Seleccione un curso válido para la inscripción.", "error")
        return redirect(url_for("admin.student_edit", student_id=student.id))

    existing = StudentEnrollment.query.filter_by(
        student_id=student.id, course_id=course.id, academic_year=course.academic_year
    ).first()
    if existing:
        existing.status = "activo"
    else:
        for previous in student.enrollments:
            if previous.status == "activo":
                previous.status = "retirado"
        db.session.add(
            StudentEnrollment(
                student_id=student.id,
                course_id=course.id,
                academic_year=course.academic_year,
                status="activo",
            )
        )
    record_audit("student_enroll", "student", student.id, course.label)
    db.session.commit()
    flash(f"Estudiante inscrito en {course.label}.", "success")
    return redirect(url_for("admin.student_edit", student_id=student.id))


# ---------------------------------------------------------------------------
# Familias (tutores) y vinculación con estudiantes
# ---------------------------------------------------------------------------
@admin_bp.get("/familias")
@login_required
@admin_required
def parents():
    search = clean(request.args.get("q"), 80)
    page = request.args.get("page", 1, type=int)
    query = Parent.query.join(User)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))
    pagination = query.order_by(User.full_name).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"] * 2, error_out=False
    )
    return render_template(
        "admin/parents.html",
        pagination=pagination,
        parents=pagination.items,
        search=search,
    )


@admin_bp.route("/familias/nueva", methods=["GET", "POST"])
@login_required
@admin_required
def parent_new():
    form = {
        "full_name": "", "email": "", "phone": "", "relationship": "Madre",
        "occupation": "", "address": "",
    }
    students = Student.query.filter_by(is_active=True).order_by(
        Student.last_name, Student.first_name
    ).all()

    if request.method == "POST":
        form = {
            "full_name": clean(request.form.get("full_name"), 160),
            "email": clean(request.form.get("email"), 180).lower(),
            "phone": clean(request.form.get("phone"), 40),
            "relationship": clean(request.form.get("relationship"), 40),
            "occupation": clean(request.form.get("occupation"), 120),
            "address": clean(request.form.get("address"), 200),
        }
        errors = []
        if len(form["full_name"]) < 5:
            errors.append("Ingrese el nombre completo del tutor.")
        if not is_valid_email(form["email"]):
            errors.append("El correo electrónico no es válido.")
        elif User.query.filter_by(email=form["email"]).first():
            errors.append("Ya existe un usuario con ese correo electrónico.")
        errors.extend(validate_password(password := request.form.get("password") or "",
                                        request.form.get("confirm_password") or ""))

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            user = User(
                full_name=form["full_name"],
                email=form["email"],
                phone=form["phone"] or None,
                role="parent",
                is_active=True,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            parent = Parent(
                user_id=user.id,
                relationship=form["relationship"] or None,
                occupation=form["occupation"] or None,
                address=form["address"] or None,
            )
            db.session.add(parent)
            db.session.flush()
            for value in request.form.getlist("student_ids"):
                try:
                    student_id = int(value)
                except ValueError:
                    continue
                db.session.add(
                    ParentStudent(
                        parent_id=parent.id,
                        student_id=student_id,
                        relationship=form["relationship"] or None,
                        is_primary=True,
                    )
                )
            record_audit("parent_create", "parent", parent.id, user.email)
            db.session.commit()
            flash("Familia registrada correctamente.", "success")
            return redirect(url_for("admin.parent_edit", parent_id=parent.id))

    return render_template(
        "admin/parent_form.html", form=form, parent=None, students=students
    )


@admin_bp.route("/familias/<int:parent_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def parent_edit(parent_id: int):
    parent = _get_or_404(Parent, parent_id)
    user = parent.user
    form = {
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone or "",
        "relationship": parent.relationship or "",
        "occupation": parent.occupation or "",
        "address": parent.address or "",
    }

    if request.method == "POST":
        form = {
            "full_name": clean(request.form.get("full_name"), 160),
            "email": clean(request.form.get("email"), 180).lower(),
            "phone": clean(request.form.get("phone"), 40),
            "relationship": clean(request.form.get("relationship"), 40),
            "occupation": clean(request.form.get("occupation"), 120),
            "address": clean(request.form.get("address"), 200),
        }
        errors = []
        if len(form["full_name"]) < 5:
            errors.append("Ingrese el nombre completo del tutor.")
        if not is_valid_email(form["email"]):
            errors.append("El correo electrónico no es válido.")
        if User.query.filter(User.email == form["email"], User.id != user.id).first():
            errors.append("Otro usuario ya utiliza ese correo electrónico.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            user.full_name = form["full_name"]
            user.email = form["email"]
            user.phone = form["phone"] or None
            parent.relationship = form["relationship"] or None
            parent.occupation = form["occupation"] or None
            parent.address = form["address"] or None
            record_audit("parent_update", "parent", parent.id, user.email)
            db.session.commit()
            flash("Datos de la familia actualizados.", "success")
            return redirect(url_for("admin.parent_edit", parent_id=parent.id))

    linked_ids = {link.student_id for link in parent.student_links}
    available = Student.query.filter(Student.is_active.is_(True))
    if linked_ids:
        available = available.filter(Student.id.notin_(linked_ids))
    available = available.order_by(Student.last_name, Student.first_name).all()

    return render_template(
        "admin/parent_form.html",
        form=form,
        parent=parent,
        students=available,
        linked=sorted(parent.students, key=lambda s: s.full_name),
    )


@admin_bp.post("/familias/<int:parent_id>/vincular")
@login_required
@admin_required
def parent_link(parent_id: int):
    parent = _get_or_404(Parent, parent_id)
    student_id, error = parse_int(request.form.get("student_id"), "estudiante")
    student = db.session.get(Student, student_id) if student_id else None

    if error or student is None:
        flash("Seleccione un estudiante válido.", "error")
        return redirect(url_for("admin.parent_edit", parent_id=parent.id))

    if db.session.get(ParentStudent, (parent.id, student.id)):
        flash("El estudiante ya está vinculado a esta familia.", "info")
    else:
        db.session.add(
            ParentStudent(
                parent_id=parent.id,
                student_id=student.id,
                relationship=clean(request.form.get("relationship"), 40) or None,
                is_primary=True,
            )
        )
        record_audit("parent_link_student", "parent", parent.id, student.full_name)
        db.session.commit()
        flash("Estudiante vinculado correctamente.", "success")
    return redirect(url_for("admin.parent_edit", parent_id=parent.id))


@admin_bp.post("/familias/<int:parent_id>/desvincular/<int:student_id>")
@login_required
@admin_required
def parent_unlink(parent_id: int, student_id: int):
    parent = _get_or_404(Parent, parent_id)
    link = db.session.get(ParentStudent, (parent.id, student_id))
    if link is None:
        abort(404)
    db.session.delete(link)
    record_audit("parent_unlink_student", "parent", parent.id, f"estudiante {student_id}")
    db.session.commit()
    flash("Vinculación eliminada.", "info")
    return redirect(url_for("admin.parent_edit", parent_id=parent.id))


# ---------------------------------------------------------------------------
# Docentes
# ---------------------------------------------------------------------------
@admin_bp.get("/docentes")
@login_required
@admin_required
def teachers():
    search = clean(request.args.get("q"), 80)
    page = request.args.get("page", 1, type=int)
    query = Teacher.query.join(User)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))
    pagination = query.order_by(User.full_name).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"] * 2, error_out=False
    )
    return render_template(
        "admin/teachers.html",
        pagination=pagination,
        teachers=pagination.items,
        search=search,
    )


@admin_bp.route("/docentes/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def teacher_new():
    form = {
        "full_name": "", "email": "", "phone": "", "employee_code": "",
        "specialty": "", "hire_date": "",
    }

    if request.method == "POST":
        form = {
            "full_name": clean(request.form.get("full_name"), 160),
            "email": clean(request.form.get("email"), 180).lower(),
            "phone": clean(request.form.get("phone"), 40),
            "employee_code": clean(request.form.get("employee_code"), 30),
            "specialty": clean(request.form.get("specialty"), 120),
            "hire_date": clean(request.form.get("hire_date"), 10),
        }
        password = request.form.get("password") or ""
        hire_date, date_error = parse_date(form["hire_date"], "fecha de ingreso")
        errors = [date_error] if date_error else []
        if len(form["full_name"]) < 5:
            errors.append("Ingrese el nombre completo del docente.")
        if not is_valid_email(form["email"]):
            errors.append("El correo electrónico no es válido.")
        elif User.query.filter_by(email=form["email"]).first():
            errors.append("Ya existe un usuario con ese correo electrónico.")
        errors.extend(
            validate_password(password, request.form.get("confirm_password") or "")
        )

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            user = User(
                full_name=form["full_name"],
                email=form["email"],
                phone=form["phone"] or None,
                role="teacher",
                is_active=True,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            teacher = Teacher(
                user_id=user.id,
                employee_code=form["employee_code"] or None,
                specialty=form["specialty"] or None,
                hire_date=hire_date,
            )
            db.session.add(teacher)
            db.session.flush()
            record_audit("teacher_create", "teacher", teacher.id, user.email)
            db.session.commit()
            flash("Docente registrado correctamente.", "success")
            return redirect(url_for("admin.teacher_edit", teacher_id=teacher.id))

    return render_template("admin/teacher_form.html", form=form, teacher=None)


@admin_bp.route("/docentes/<int:teacher_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def teacher_edit(teacher_id: int):
    teacher = _get_or_404(Teacher, teacher_id)
    user = teacher.user
    form = {
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone or "",
        "employee_code": teacher.employee_code or "",
        "specialty": teacher.specialty or "",
        "hire_date": teacher.hire_date.isoformat() if teacher.hire_date else "",
    }

    if request.method == "POST":
        form = {
            "full_name": clean(request.form.get("full_name"), 160),
            "email": clean(request.form.get("email"), 180).lower(),
            "phone": clean(request.form.get("phone"), 40),
            "employee_code": clean(request.form.get("employee_code"), 30),
            "specialty": clean(request.form.get("specialty"), 120),
            "hire_date": clean(request.form.get("hire_date"), 10),
        }
        hire_date, date_error = parse_date(form["hire_date"], "fecha de ingreso")
        errors = [date_error] if date_error else []
        if len(form["full_name"]) < 5:
            errors.append("Ingrese el nombre completo del docente.")
        if not is_valid_email(form["email"]):
            errors.append("El correo electrónico no es válido.")
        if User.query.filter(User.email == form["email"], User.id != user.id).first():
            errors.append("Otro usuario ya utiliza ese correo electrónico.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            user.full_name = form["full_name"]
            user.email = form["email"]
            user.phone = form["phone"] or None
            teacher.employee_code = form["employee_code"] or None
            teacher.specialty = form["specialty"] or None
            teacher.hire_date = hire_date
            record_audit("teacher_update", "teacher", teacher.id, user.email)
            db.session.commit()
            flash("Datos del docente actualizados.", "success")
            return redirect(url_for("admin.teacher_edit", teacher_id=teacher.id))

    courses = Course.query.filter_by(is_active=True).order_by(Course.academic_year.desc()).all()
    return render_template(
        "admin/teacher_form.html",
        form=form,
        teacher=teacher,
        courses=courses,
        assignments=teacher.course_assignments,
    )


@admin_bp.post("/docentes/<int:teacher_id>/asignar")
@login_required
@admin_required
def teacher_assign(teacher_id: int):
    teacher = _get_or_404(Teacher, teacher_id)
    course_id, id_error = parse_int(request.form.get("course_id"), "curso")
    subject = clean(request.form.get("subject"), 80)
    course = db.session.get(Course, course_id) if course_id else None

    if id_error or course is None or len(subject) < 2:
        flash("Seleccione un curso e indique la materia.", "error")
        return redirect(url_for("admin.teacher_edit", teacher_id=teacher.id))

    existing = CourseAssignment.query.filter_by(
        teacher_id=teacher.id, course_id=course.id, subject=subject
    ).first()
    if existing:
        flash("Esa asignación ya existe.", "info")
    else:
        db.session.add(
            CourseAssignment(teacher_id=teacher.id, course_id=course.id, subject=subject)
        )
        record_audit("teacher_assign", "teacher", teacher.id, f"{course.label} · {subject}")
        db.session.commit()
        flash("Curso asignado al docente.", "success")
    return redirect(url_for("admin.teacher_edit", teacher_id=teacher.id))


@admin_bp.post("/docentes/<int:teacher_id>/asignaciones/<int:assignment_id>/eliminar")
@login_required
@admin_required
def teacher_unassign(teacher_id: int, assignment_id: int):
    teacher = _get_or_404(Teacher, teacher_id)
    assignment = _get_or_404(CourseAssignment, assignment_id)
    if assignment.teacher_id != teacher.id:
        abort(404)
    label = assignment.label
    db.session.delete(assignment)
    record_audit("teacher_unassign", "teacher", teacher.id, label)
    db.session.commit()
    flash("Asignación eliminada.", "info")
    return redirect(url_for("admin.teacher_edit", teacher_id=teacher.id))


# ---------------------------------------------------------------------------
# Cursos
# ---------------------------------------------------------------------------
@admin_bp.get("/cursos")
@login_required
@admin_required
def courses():
    page = request.args.get("page", 1, type=int)
    year = request.args.get("anio", "", type=str)
    query = Course.query
    if year.isdigit():
        query = query.filter(Course.academic_year == int(year))
    pagination = query.order_by(
        Course.academic_year.desc(), Course.name, Course.parallel
    ).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"] * 2, error_out=False
    )
    years = sorted({course.academic_year for course in Course.query.all()}, reverse=True)
    return render_template(
        "admin/courses.html",
        pagination=pagination,
        courses=pagination.items,
        years=years,
        year=year,
    )


def _course_form_data(form: dict) -> tuple[dict, list[str], int | None]:
    year, year_error = parse_int(form.get("academic_year"), "año académico")
    errors = [year_error] if year_error else []
    if len(form["name"]) < 2:
        errors.append("Ingrese el nombre del curso.")
    if not form["parallel"]:
        errors.append("Indique el paralelo o sección.")
    if year is None or not (2000 <= year <= 2100):
        errors.append("El año académico debe estar entre 2000 y 2100.")
    return form, errors, year


@admin_bp.route("/cursos/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def course_new():
    form = {
        "name": "", "level": "Secundaria", "parallel": "A",
        "academic_year": str(date.today().year), "description": "",
    }

    if request.method == "POST":
        form = {
            "name": clean(request.form.get("name"), 80),
            "level": clean(request.form.get("level"), 60),
            "parallel": clean(request.form.get("parallel"), 10).upper(),
            "academic_year": clean(request.form.get("academic_year"), 4),
            "description": clean(request.form.get("description"), 200),
        }
        form, errors, year = _course_form_data(form)
        duplicate = Course.query.filter_by(
            name=form["name"], parallel=form["parallel"], academic_year=year
        ).first()
        if duplicate:
            errors.append("Ya existe un curso con ese nombre, paralelo y año.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            course = Course(
                name=form["name"],
                level=form["level"] or None,
                parallel=form["parallel"],
                academic_year=year,
                description=form["description"] or None,
            )
            db.session.add(course)
            db.session.flush()
            record_audit("course_create", "course", course.id, course.label)
            db.session.commit()
            flash("Curso creado correctamente.", "success")
            return redirect(url_for("admin.courses"))

    return render_template("admin/course_form.html", form=form, course=None)


@admin_bp.route("/cursos/<int:course_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def course_edit(course_id: int):
    course = _get_or_404(Course, course_id)
    form = {
        "name": course.name,
        "level": course.level or "",
        "parallel": course.parallel,
        "academic_year": str(course.academic_year),
        "description": course.description or "",
    }

    if request.method == "POST":
        form = {
            "name": clean(request.form.get("name"), 80),
            "level": clean(request.form.get("level"), 60),
            "parallel": clean(request.form.get("parallel"), 10).upper(),
            "academic_year": clean(request.form.get("academic_year"), 4),
            "description": clean(request.form.get("description"), 200),
        }
        form, errors, year = _course_form_data(form)
        duplicate = Course.query.filter(
            Course.name == form["name"],
            Course.parallel == form["parallel"],
            Course.academic_year == year,
            Course.id != course.id,
        ).first()
        if duplicate:
            errors.append("Otro curso ya utiliza ese nombre, paralelo y año.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            course.name = form["name"]
            course.level = form["level"] or None
            course.parallel = form["parallel"]
            course.academic_year = year
            course.description = form["description"] or None
            record_audit("course_update", "course", course.id, course.label)
            db.session.commit()
            flash("Curso actualizado correctamente.", "success")
            return redirect(url_for("admin.courses"))

    return render_template(
        "admin/course_form.html",
        form=form,
        course=course,
        students=course.active_students,
        teachers=course.teachers(),
    )


@admin_bp.post("/cursos/<int:course_id>/estado")
@login_required
@admin_required
def course_toggle(course_id: int):
    course = _get_or_404(Course, course_id)
    course.is_active = not course.is_active
    record_audit(
        "course_activate" if course.is_active else "course_deactivate",
        "course",
        course.id,
        course.label,
    )
    db.session.commit()
    flash(
        f"Curso {'activado' if course.is_active else 'desactivado'} correctamente.",
        "success",
    )
    return redirect(url_for("admin.courses"))


# ---------------------------------------------------------------------------
# Comunicados (dirección y administración)
# ---------------------------------------------------------------------------
def _announcement_form_data(form) -> tuple[dict, list[str]]:
    course_ids: list[int] = []
    for value in form.getlist("course_ids"):
        try:
            course_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    data = {
        "title": clean(form.get("title"), 180),
        "summary": clean(form.get("summary"), 300),
        "body": clean_multiline(form.get("body"), 8000),
        "category": choices(form.get("category"), ANNOUNCEMENT_CATEGORIES, "general"),
        "priority": choices(form.get("priority"), PRIORITIES, "normal"),
        "status": choices(form.get("status"), ("draft", "published"), "draft"),
        "audience": choices(form.get("audience"), AUDIENCES, "public"),
        "target_role": choices(form.get("target_role"), ROLES, None),
        "is_pinned": bool(form.get("is_pinned")),
        "expires_at": clean(form.get("expires_at"), 10),
        "course_ids": course_ids,
    }
    expires_at, date_error = parse_date(data["expires_at"], "fecha de vencimiento")
    data["expires_at_value"] = expires_at

    errors = [date_error] if date_error else []
    if len(data["title"]) < 5:
        errors.append("El título debe tener al menos 5 caracteres.")
    if len(data["body"]) < 15:
        errors.append("El contenido del comunicado debe tener al menos 15 caracteres.")
    if data["audience"] == "internal" and not data["target_role"]:
        errors.append("Seleccione el público destinatario del comunicado interno.")
    if data["audience"] == "internal" and not course_ids and data["target_role"] == "parent":
        errors.append(
            "Si el comunicado interno es para familias, seleccione al menos un curso."
        )
    return data, errors


def _announcement_context() -> dict:
    return {
        "courses": Course.query.filter_by(is_active=True)
        .order_by(Course.academic_year.desc(), Course.name)
        .all(),
        "categories": ANNOUNCEMENT_CATEGORIES,
        "priorities": PRIORITIES,
        "roles": ROLES,
        "audiences": AUDIENCES,
    }


@admin_bp.get("/comunicados")
@login_required
@staff_required
def announcements():
    status = request.args.get("estado", "")
    category = request.args.get("categoria", "")
    search = clean(request.args.get("q"), 80)
    page = request.args.get("page", 1, type=int)

    query = Announcement.query
    if status in ANNOUNCEMENT_STATUSES:
        query = query.filter(Announcement.status == status)
    if category in ANNOUNCEMENT_CATEGORIES:
        query = query.filter(Announcement.category == category)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(Announcement.title.ilike(like), Announcement.body.ilike(like))
        )

    pagination = query.order_by(
        Announcement.is_pinned.desc(), Announcement.created_at.desc()
    ).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"] * 2, error_out=False
    )
    return render_template(
        "admin/announcements.html",
        pagination=pagination,
        announcements=pagination.items,
        status=status,
        category=category,
        search=search,
        statuses=ANNOUNCEMENT_STATUSES,
        categories=ANNOUNCEMENT_CATEGORIES,
    )


@admin_bp.route("/comunicados/nuevo", methods=["GET", "POST"])
@login_required
@staff_required
def announcement_new():
    form = {
        "title": "", "summary": "", "body": "", "category": "general",
        "priority": "normal", "status": "draft", "audience": "public",
        "target_role": "", "is_pinned": False, "expires_at": "", "course_ids": [],
    }

    if request.method == "POST":
        data, errors = _announcement_form_data(request.form)
        metadata = None
        if not errors:
            metadata, upload_error = save_upload(request.files.get("attachment"))
            if upload_error:
                errors.append(upload_error)

        if errors:
            for message in errors:
                flash(message, "error")
            form = {**data, "target_role": data["target_role"] or ""}
        else:
            announcement = Announcement(
                title=data["title"],
                summary=data["summary"] or None,
                body=data["body"],
                category=data["category"],
                priority=data["priority"],
                status=data["status"],
                audience=data["audience"],
                target_role=data["target_role"],
                is_pinned=data["is_pinned"],
                expires_at=data["expires_at_value"],
                author_id=current_user.id,
                published_at=utcnow() if data["status"] == "published" else None,
            )
            if metadata:
                announcement.attachment_path = metadata["path"]
                announcement.attachment_name = metadata["name"]
                announcement.attachment_mime = metadata["mime"]
                announcement.attachment_size = metadata["size"]

            db.session.add(announcement)
            db.session.flush()
            if data["audience"] == "internal":
                for course_id in data["course_ids"]:
                    if db.session.get(Course, course_id) is not None:
                        db.session.add(
                            AnnouncementRecipient(
                                announcement_id=announcement.id, course_id=course_id
                            )
                        )
            db.session.flush()
            if announcement.status == "published":
                notify_announcement(announcement)
            record_audit(
                "announcement_create", "announcement", announcement.id, announcement.title
            )
            db.session.commit()
            flash(
                "Comunicado publicado correctamente."
                if announcement.status == "published"
                else "Borrador guardado correctamente.",
                "success",
            )
            return redirect(url_for("admin.announcements"))

    return render_template(
        "admin/announcement_form.html",
        form=form,
        announcement=None,
        **_announcement_context(),
    )


@admin_bp.route("/comunicados/<int:announcement_id>/editar", methods=["GET", "POST"])
@login_required
@staff_required
def announcement_edit(announcement_id: int):
    announcement = _get_or_404(Announcement, announcement_id)
    form = {
        "title": announcement.title,
        "summary": announcement.summary or "",
        "body": announcement.body,
        "category": announcement.category,
        "priority": announcement.priority,
        "status": announcement.status if announcement.status != "archived" else "draft",
        "audience": announcement.audience,
        "target_role": announcement.target_role or "",
        "is_pinned": announcement.is_pinned,
        "expires_at": (
            announcement.expires_at.isoformat() if announcement.expires_at else ""
        ),
        "course_ids": [recipient.course_id for recipient in announcement.recipients],
    }

    if request.method == "POST":
        data, errors = _announcement_form_data(request.form)
        metadata = None
        if not errors:
            metadata, upload_error = save_upload(request.files.get("attachment"))
            if upload_error:
                errors.append(upload_error)

        if errors:
            for message in errors:
                flash(message, "error")
            form = {**data, "target_role": data["target_role"] or ""}
        else:
            was_published = announcement.status == "published"
            announcement.title = data["title"]
            announcement.summary = data["summary"] or None
            announcement.body = data["body"]
            announcement.category = data["category"]
            announcement.priority = data["priority"]
            announcement.audience = data["audience"]
            announcement.target_role = data["target_role"]
            announcement.is_pinned = data["is_pinned"]
            announcement.expires_at = data["expires_at_value"]

            if data["status"] == "published" and announcement.published_at is None:
                announcement.published_at = utcnow()
            if data["status"] == "draft" and was_published:
                flash(
                    "El comunicado vuelve a borrador y deja de ser visible al público.",
                    "warning",
                )
            announcement.status = data["status"]

            if metadata:
                delete_upload(announcement.attachment_path)
                announcement.attachment_path = metadata["path"]
                announcement.attachment_name = metadata["name"]
                announcement.attachment_mime = metadata["mime"]
                announcement.attachment_size = metadata["size"]
            elif request.form.get("remove_attachment"):
                delete_upload(announcement.attachment_path)
                announcement.attachment_path = None
                announcement.attachment_name = None
                announcement.attachment_mime = None
                announcement.attachment_size = None

            for recipient in list(announcement.recipients):
                db.session.delete(recipient)
            db.session.flush()
            if data["audience"] == "internal":
                for course_id in data["course_ids"]:
                    if db.session.get(Course, course_id) is not None:
                        db.session.add(
                            AnnouncementRecipient(
                                announcement_id=announcement.id, course_id=course_id
                            )
                        )
            db.session.flush()

            if data["status"] == "published" and not was_published:
                notify_announcement(announcement)
            record_audit(
                "announcement_update", "announcement", announcement.id, announcement.title
            )
            db.session.commit()
            flash("Comunicado actualizado correctamente.", "success")
            return redirect(url_for("admin.announcements"))

    return render_template(
        "admin/announcement_form.html",
        form=form,
        announcement=announcement,
        **_announcement_context(),
    )


@admin_bp.post("/comunicados/<int:announcement_id>/publicar")
@login_required
@staff_required
def announcement_publish(announcement_id: int):
    announcement = _get_or_404(Announcement, announcement_id)
    announcement.status = "published"
    if announcement.published_at is None:
        announcement.published_at = utcnow()
    notify_announcement(announcement)
    record_audit("announcement_publish", "announcement", announcement.id, announcement.title)
    db.session.commit()
    flash("Comunicado publicado y notificado a los destinatarios.", "success")
    return redirect(url_for("admin.announcements"))


@admin_bp.post("/comunicados/<int:announcement_id>/archivar")
@login_required
@staff_required
def announcement_archive(announcement_id: int):
    announcement = _get_or_404(Announcement, announcement_id)
    announcement.status = "archived"
    record_audit("announcement_archive", "announcement", announcement.id, announcement.title)
    db.session.commit()
    flash("Comunicado archivado.", "info")
    return redirect(url_for("admin.announcements"))


@admin_bp.post("/comunicados/<int:announcement_id>/fijar")
@login_required
@staff_required
def announcement_pin(announcement_id: int):
    announcement = _get_or_404(Announcement, announcement_id)
    announcement.is_pinned = not announcement.is_pinned
    record_audit(
        "announcement_pin" if announcement.is_pinned else "announcement_unpin",
        "announcement",
        announcement.id,
        announcement.title,
    )
    db.session.commit()
    flash(
        "Comunicado fijado en la portada."
        if announcement.is_pinned
        else "El comunicado ya no está fijado.",
        "success",
    )
    return redirect(url_for("admin.announcements"))


@admin_bp.post("/comunicados/<int:announcement_id>/eliminar")
@login_required
@admin_required
def announcement_delete(announcement_id: int):
    announcement = _get_or_404(Announcement, announcement_id)
    title = announcement.title
    delete_upload(announcement.attachment_path)
    db.session.delete(announcement)
    record_audit("announcement_delete", "announcement", announcement_id, title)
    db.session.commit()
    flash("Comunicado eliminado definitivamente.", "info")
    return redirect(url_for("admin.announcements"))


# ---------------------------------------------------------------------------
# Calendario escolar
# ---------------------------------------------------------------------------
@admin_bp.get("/calendario")
@login_required
@staff_required
def events():
    month = request.args.get("mes", "", type=str)
    query = Event.query
    if month and len(month) == 7:
        try:
            year_part, month_part = month.split("-")
            start = date(int(year_part), int(month_part), 1)
            last_day = __import__("calendar").monthrange(start.year, start.month)[1]
            query = query.filter(
                Event.start_date >= start,
                Event.start_date <= date(start.year, start.month, last_day),
            )
        except (ValueError, TypeError):
            month = ""
    items = query.order_by(Event.start_date.desc(), Event.start_time).limit(200).all()
    return render_template("admin/events.html", events=items, month=month)


def _event_form_data(form) -> tuple[dict, list[str]]:
    data = {
        "title": clean(form.get("title"), 180),
        "description": clean_multiline(form.get("description"), 2000),
        "start_date": clean(form.get("start_date"), 10),
        "start_time": clean(form.get("start_time"), 5),
        "end_date": clean(form.get("end_date"), 10),
        "location": clean(form.get("location"), 160),
        "category": choices(form.get("category"), EVENT_CATEGORIES, "otro"),
        "audience": choices(form.get("audience"), AUDIENCES, "public"),
        "target_role": choices(form.get("target_role"), ROLES, None),
        "course_id": clean(form.get("course_id"), 10),
    }
    start_date, start_error = parse_date(data["start_date"], "fecha de inicio")
    end_date, end_error = parse_date(data["end_date"], "fecha de fin")
    start_time, time_error = parse_time(data["start_time"])
    errors = [e for e in (start_error, end_error, time_error) if e]
    if len(data["title"]) < 4:
        errors.append("El título del evento debe tener al menos 4 caracteres.")
    if start_date is None:
        errors.append("Indique la fecha del evento.")
    if end_date and start_date and end_date < start_date:
        errors.append("La fecha de fin no puede ser anterior a la fecha de inicio.")
    data.update(
        {"start_date_value": start_date, "end_date_value": end_date, "start_time_value": start_time}
    )
    return data, errors


@admin_bp.route("/calendario/nuevo", methods=["GET", "POST"])
@login_required
@staff_required
def event_new():
    form = {
        "title": "", "description": "", "start_date": "", "start_time": "",
        "end_date": "", "location": "", "category": "reunion",
        "audience": "public", "target_role": "", "course_id": "",
    }
    courses = Course.query.filter_by(is_active=True).order_by(Course.name).all()

    if request.method == "POST":
        data, errors = _event_form_data(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
            form = {**data, "target_role": data["target_role"] or ""}
        else:
            course_id, _ = parse_int(data["course_id"], "curso")
            event = Event(
                title=data["title"],
                description=data["description"] or None,
                start_date=data["start_date_value"],
                start_time=data["start_time_value"],
                end_date=data["end_date_value"],
                location=data["location"] or None,
                category=data["category"],
                audience=data["audience"],
                target_role=data["target_role"],
                course_id=course_id,
                created_by=current_user.id,
            )
            db.session.add(event)
            db.session.flush()
            record_audit("event_create", "event", event.id, event.title)
            db.session.commit()
            flash("Evento agregado al calendario escolar.", "success")
            return redirect(url_for("admin.events"))

    return render_template(
        "admin/event_form.html",
        form=form,
        event=None,
        courses=courses,
        categories=EVENT_CATEGORIES,
        roles=ROLES,
    )


@admin_bp.route("/calendario/<int:event_id>/editar", methods=["GET", "POST"])
@login_required
@staff_required
def event_edit(event_id: int):
    event = _get_or_404(Event, event_id)
    form = {
        "title": event.title,
        "description": event.description or "",
        "start_date": event.start_date.isoformat(),
        "start_time": event.start_time.strftime("%H:%M") if event.start_time else "",
        "end_date": event.end_date.isoformat() if event.end_date else "",
        "location": event.location or "",
        "category": event.category,
        "audience": event.audience,
        "target_role": event.target_role or "",
        "course_id": str(event.course_id or ""),
    }
    courses = Course.query.filter_by(is_active=True).order_by(Course.name).all()

    if request.method == "POST":
        data, errors = _event_form_data(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
            form = {**data, "target_role": data["target_role"] or ""}
        else:
            course_id, _ = parse_int(data["course_id"], "curso")
            event.title = data["title"]
            event.description = data["description"] or None
            event.start_date = data["start_date_value"]
            event.start_time = data["start_time_value"]
            event.end_date = data["end_date_value"]
            event.location = data["location"] or None
            event.category = data["category"]
            event.audience = data["audience"]
            event.target_role = data["target_role"]
            event.course_id = course_id
            record_audit("event_update", "event", event.id, event.title)
            db.session.commit()
            flash("Evento actualizado correctamente.", "success")
            return redirect(url_for("admin.events"))

    return render_template(
        "admin/event_form.html",
        form=form,
        event=event,
        courses=courses,
        categories=EVENT_CATEGORIES,
        roles=ROLES,
    )


@admin_bp.post("/calendario/<int:event_id>/cancelar")
@login_required
@staff_required
def event_cancel(event_id: int):
    event = _get_or_404(Event, event_id)
    event.is_cancelled = not event.is_cancelled
    record_audit(
        "event_cancel" if event.is_cancelled else "event_restore",
        "event",
        event.id,
        event.title,
    )
    db.session.commit()
    flash(
        "Evento marcado como cancelado." if event.is_cancelled
        else "Evento reactivado en el calendario.",
        "success",
    )
    return redirect(url_for("admin.events"))


@admin_bp.post("/calendario/<int:event_id>/eliminar")
@login_required
@admin_required
def event_delete(event_id: int):
    event = _get_or_404(Event, event_id)
    title = event.title
    db.session.delete(event)
    record_audit("event_delete", "event", event_id, title)
    db.session.commit()
    flash("Evento eliminado del calendario.", "info")
    return redirect(url_for("admin.events"))


# ---------------------------------------------------------------------------
# Configuración institucional y galería
# ---------------------------------------------------------------------------
@admin_bp.route("/configuracion", methods=["GET", "POST"])
@login_required
@staff_required
def settings():
    if request.method == "POST":
        data = {key: request.form.get(key, "") for key in SETTING_LABELS}
        save_settings(data)
        record_audit("settings_update", "settings", None, "Datos institucionales")
        db.session.commit()
        flash("Datos institucionales actualizados.", "success")
        return redirect(url_for("admin.settings"))

    values = load_settings()
    return render_template(
        "admin/settings.html",
        values=values,
        labels=SETTING_LABELS,
        pending=pending_settings(values),
    )


@admin_bp.route("/galeria", methods=["GET", "POST"])
@login_required
@staff_required
def gallery():
    folder = Path(current_app.static_folder) / "img" / "galeria"
    folder.mkdir(parents=True, exist_ok=True)

    if request.method == "POST":
        upload = request.files.get("image")
        allowed = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
        if upload is None or not upload.filename:
            flash("Seleccione una imagen para subir.", "error")
        elif not upload.filename.lower().endswith(tuple(f".{ext}" for ext in allowed)):
            flash("Formato no permitido. Use PNG, JPG o WEBP.", "error")
        else:
            data = upload.read()
            if len(data) > current_app.config["MAX_ATTACHMENT_MB"] * 1024 * 1024:
                flash(
                    f"La imagen supera el límite de "
                    f"{current_app.config['MAX_ATTACHMENT_MB']} MB.",
                    "error",
                )
            else:
                from werkzeug.utils import secure_filename

                base = secure_filename(Path(upload.filename).stem)[:40] or "imagen"
                extension = Path(upload.filename).suffix.lower()
                target = folder / f"{base}{extension}"
                if target.exists():
                    target = folder / f"{base}-{utcnow().strftime('%Y%m%d%H%M%S')}{extension}"
                target.write_bytes(data)
                record_audit("gallery_upload", "gallery", None, target.name)
                db.session.commit()
                flash(
                    "Imagen agregada a la galería institucional. "
                    "Recuerde que debe contar con autorización para publicar "
                    "fotografías de estudiantes.",
                    "success",
                )
        return redirect(url_for("admin.gallery"))

    return render_template("admin/gallery.html", gallery=gallery_images())


@admin_bp.post("/galeria/eliminar")
@login_required
@admin_required
def gallery_delete():
    filename = clean(request.form.get("filename"), 120)
    folder = Path(current_app.static_folder) / "img" / "galeria"
    target = (folder / filename).resolve()
    if not filename or folder.resolve() not in target.parents or not target.is_file():
        flash("La imagen indicada no existe.", "error")
        return redirect(url_for("admin.gallery"))

    target.unlink()
    record_audit("gallery_delete", "gallery", None, target.name)
    db.session.commit()
    flash("Imagen eliminada de la galería.", "info")
    return redirect(url_for("admin.gallery"))


# ---------------------------------------------------------------------------
# Buzón del formulario de contacto
# ---------------------------------------------------------------------------
@admin_bp.get("/mensajes-contacto")
@login_required
@staff_required
def contact_messages():
    page = request.args.get("page", 1, type=int)
    only_unread = request.args.get("pendientes") == "1"
    query = ContactMessage.query
    if only_unread:
        query = query.filter(ContactMessage.is_read.is_(False))
    pagination = query.order_by(ContactMessage.created_at.desc()).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"] * 2, error_out=False
    )
    return render_template(
        "admin/contact_messages.html",
        pagination=pagination,
        messages=pagination.items,
        only_unread=only_unread,
        unread_count=ContactMessage.query.filter_by(is_read=False).count(),
    )


@admin_bp.get("/mensajes-contacto/<int:message_id>")
@login_required
@staff_required
def contact_message_detail(message_id: int):
    message = _get_or_404(ContactMessage, message_id)
    if not message.is_read:
        message.is_read = True
        db.session.commit()
    return render_template("admin/contact_message_detail.html", message=message)


@admin_bp.post("/mensajes-contacto/<int:message_id>/eliminar")
@login_required
@admin_required
def contact_message_delete(message_id: int):
    message = _get_or_404(ContactMessage, message_id)
    subject = message.subject
    db.session.delete(message)
    record_audit("contact_message_delete", "contact_message", message_id, subject)
    db.session.commit()
    flash("Mensaje eliminado del buzón.", "info")
    return redirect(url_for("admin.contact_messages"))


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------
@admin_bp.get("/auditoria")
@login_required
@staff_required
def audit():
    page = request.args.get("page", 1, type=int)
    action = clean(request.args.get("accion"), 80)
    query = AuditLog.query
    if action:
        query = query.filter(AuditLog.action == action)
    pagination = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"] * 2, error_out=False
    )
    actions = [
        row[0]
        for row in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action)
    ]
    return render_template(
        "admin/audit.html",
        pagination=pagination,
        logs=pagination.items,
        action=action,
        actions=actions,
    )


# ---------------------------------------------------------------------------
# Notificaciones internas masivas
# ---------------------------------------------------------------------------
@admin_bp.route("/notificaciones", methods=["GET", "POST"])
@login_required
@staff_required
def notifications():
    courses = Course.query.filter_by(is_active=True).order_by(Course.name).all()
    form = {"audience": "all", "role": "", "course_id": "", "title": "", "body": ""}

    if request.method == "POST":
        form = {
            "audience": choices(
                request.form.get("audience"), ("all", "role", "course"), "all"
            ),
            "role": choices(request.form.get("role"), ROLES, ""),
            "course_id": clean(request.form.get("course_id"), 10),
            "title": clean(request.form.get("title"), 180),
            "body": clean_multiline(request.form.get("body"), 400),
        }
        errors = []
        if len(form["title"]) < 5:
            errors.append("El título debe tener al menos 5 caracteres.")
        if len(form["body"]) < 10:
            errors.append("El mensaje debe tener al menos 10 caracteres.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            recipients: list[User] = []
            if form["audience"] == "role" and form["role"]:
                recipients = User.query.filter(
                    User.role == form["role"], User.is_active.is_(True)
                ).all()
            elif form["audience"] == "course":
                course_id, _ = parse_int(form["course_id"], "curso")
                course = db.session.get(Course, course_id) if course_id else None
                if course is None:
                    flash("Seleccione un curso válido.", "error")
                else:
                    seen: set[int] = set()
                    for student in course.active_students:
                        for user in student.guardians:
                            if user.id not in seen and user.is_active:
                                seen.add(user.id)
                                recipients.append(user)
                    for teacher in course.teachers():
                        if (
                            teacher.user
                            and teacher.user.id not in seen
                            and teacher.user.is_active
                        ):
                            seen.add(teacher.user.id)
                            recipients.append(teacher.user)
            else:
                recipients = User.query.filter(
                    User.is_active.is_(True), User.id != current_user.id
                ).all()

            if not recipients:
                flash("No se encontraron destinatarios para la selección.", "warning")
            else:
                notify_many(
                    recipients, form["title"], form["body"], category="broadcast"
                )
                record_audit(
                    "notification_broadcast",
                    "notification",
                    None,
                    f"{len(recipients)} destinatarios: {form['title']}",
                )
                db.session.commit()
                flash(f"Notificación enviada a {len(recipients)} usuarios.", "success")
                return redirect(url_for("admin.notifications"))

    recent = (
        Notification.query.join(User)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "admin/notifications.html",
        form=form,
        courses=courses,
        roles=ROLES,
        recent=recent,
    )

















