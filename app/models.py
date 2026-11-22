"""Modelos de datos de la plataforma institucional Nueva Canaán.

Diseño relacional normalizado sobre SQLite (desarrollo) o PostgreSQL (opcional).
Las claves foráneas se validan a nivel de base de datos: ver el PRAGMA activado
en ``app/extensions.py``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow() -> datetime:
    """Fecha/hora UTC sin zona (se almacena igual en SQLite y PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Constantes de dominio (se usan como CHECK en la base de datos)
# ---------------------------------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_DIRECTION = "direction"
ROLE_TEACHER = "teacher"
ROLE_PARENT = "parent"
ROLE_STUDENT = "student"

ROLES = (ROLE_ADMIN, ROLE_DIRECTION, ROLE_TEACHER, ROLE_PARENT, ROLE_STUDENT)

ROLE_LABELS = {
    ROLE_ADMIN: "Administrador",
    ROLE_DIRECTION: "Dirección",
    ROLE_TEACHER: "Docente",
    ROLE_PARENT: "Padre / Madre / Tutor",
    ROLE_STUDENT: "Estudiante",
}

# Roles con acceso a funciones de gestión institucional
STAFF_ROLES = (ROLE_ADMIN, ROLE_DIRECTION)

ANNOUNCEMENT_CATEGORIES = (
    "reunion",
    "suspension",
    "academico",
    "cultural",
    "inscripcion",
    "administrativo",
    "evaluacion",
    "recordatorio",
    "general",
)

ANNOUNCEMENT_CATEGORY_LABELS = {
    "reunion": "Reunión de padres",
    "suspension": "Suspensión / cambio de actividades",
    "academico": "Actividad académica",
    "cultural": "Actividad cultural",
    "inscripcion": "Inscripciones",
    "administrativo": "Aviso administrativo",
    "evaluacion": "Evaluación",
    "recordatorio": "Recordatorio / circular",
    "general": "General",
}

PRIORITIES = ("baja", "normal", "alta", "urgente")

PRIORITY_LABELS = {
    "baja": "Baja",
    "normal": "Normal",
    "alta": "Alta",
    "urgente": "Urgente",
}

ANNOUNCEMENT_STATUSES = ("draft", "published", "archived")

ANNOUNCEMENT_STATUS_LABELS = {
    "draft": "Borrador",
    "published": "Publicado",
    "archived": "Archivado",
}

AUDIENCES = ("public", "internal")

AUDIENCE_LABELS = {
    "public": "Público general",
    "internal": "Sólo usuarios con sesión",
}

EVENT_CATEGORIES = (
    "reunion",
    "examen",
    "deportivo",
    "civico",
    "cultural",
    "administrativo",
    "periodo",
    "otro",
)

EVENT_CATEGORY_LABELS = {
    "reunion": "Reunión de padres",
    "examen": "Examen / evaluación",
    "deportivo": "Actividad deportiva",
    "civico": "Acto cívico",
    "cultural": "Actividad cultural",
    "administrativo": "Fecha administrativa",
    "periodo": "Periodo académico",
    "otro": "Otro",
}

ATTENDANCE_STATUSES = ("presente", "ausente", "tarde", "justificado")

ATTENDANCE_STATUS_LABELS = {
    "presente": "Presente",
    "ausente": "Ausente",
    "tarde": "Tarde",
    "justificado": "Justificado",
}

ASSIGNMENT_KINDS = ("tarea", "evaluacion", "actividad")

ASSIGNMENT_KIND_LABELS = {
    "tarea": "Tarea",
    "evaluacion": "Evaluación",
    "actividad": "Actividad",
}

ENROLLMENT_STATUSES = ("activo", "retirado", "egresado")

ENROLLMENT_STATUS_LABELS = {
    "activo": "Activo",
    "retirado": "Retirado",
    "egresado": "Egresado",
}


# ---------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------
class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Usuarios y perfiles
# ---------------------------------------------------------------------------
class User(UserMixin, TimestampMixin, db.Model):
    """Credenciales y rol. Nunca se almacena la contraseña en texto plano."""

    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('admin','direction','teacher','parent','student')",
            name="ck_users_role",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(40))
    role = db.Column(db.String(20), nullable=False, default=ROLE_PARENT, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(60))

    parent_profile = db.relationship(
        "Parent", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    teacher_profile = db.relationship(
        "Teacher", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    notifications = db.relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Notification.created_at.desc()",
    )

    # --- Contraseñas -------------------------------------------------
    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password, method="pbkdf2:sha256")

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

    # --- Bloqueo por intentos fallidos -------------------------------
    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > utcnow()

    def register_failed_login(self, max_attempts: int, lock_minutes: int) -> None:
        from datetime import timedelta

        self.failed_login_attempts = (self.failed_login_attempts or 0) + 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = utcnow() + timedelta(minutes=lock_minutes)

    def register_successful_login(self, ip_address: str | None = None) -> None:
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login_at = utcnow()
        self.last_login_ip = (ip_address or "")[:60] or None

    # --- Autorización -------------------------------------------------
    def has_role(self, *roles: str) -> bool:
        return self.role in roles

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def initials(self) -> str:
        parts = [p for p in (self.full_name or "").split() if p]
        return "".join(p[0].upper() for p in parts[:2]) or "?"

    @property
    def dashboard_endpoint(self) -> str:
        if self.role in STAFF_ROLES:
            return "admin.dashboard"
        if self.role == ROLE_TEACHER:
            return "teachers.dashboard"
        return "parents.dashboard"

    def unread_notifications(self) -> int:
        return Notification.query.filter_by(user_id=self.id, read_at=None).count()

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<User {self.email} ({self.role})>"


class Parent(TimestampMixin, db.Model):
    """Perfil ampliado del padre, madre o tutor."""

    __tablename__ = "parents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    relationship = db.Column(db.String(40))  # Padre / Madre / Tutor / Apoderado
    occupation = db.Column(db.String(120))
    address = db.Column(db.String(200))

    user = db.relationship("User", back_populates="parent_profile")
    student_links = db.relationship(
        "ParentStudent", back_populates="parent", cascade="all, delete-orphan"
    )

    @property
    def students(self) -> list["Student"]:
        return [link.student for link in self.student_links if link.student]

    def is_linked_to(self, student_id: int) -> bool:
        return any(link.student_id == student_id for link in self.student_links)


class Student(TimestampMixin, db.Model):
    """Estudiante. Sus datos personales no se publican en páginas abiertas."""

    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    birth_date = db.Column(db.Date)
    gender = db.Column(db.String(20))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    parent_links = db.relationship(
        "ParentStudent", back_populates="student", cascade="all, delete-orphan"
    )
    enrollments = db.relationship(
        "StudentEnrollment", back_populates="student", cascade="all, delete-orphan"
    )
    attendance_records = db.relationship(
        "Attendance", back_populates="student", cascade="all, delete-orphan"
    )
    grades = db.relationship("Grade", back_populates="student", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.last_name}, {self.first_name}".strip(", ")

    @property
    def age(self) -> int | None:
        if not self.birth_date:
            return None
        today = date.today()
        return today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )

    @property
    def current_enrollment(self) -> "StudentEnrollment | None":
        items = [e for e in self.enrollments if e.status == "activo"]
        items.sort(key=lambda e: e.id, reverse=True)
        return items[0] if items else None

    @property
    def current_course(self) -> "Course | None":
        enrollment = self.current_enrollment
        return enrollment.course if enrollment else None

    @property
    def guardians(self) -> list[User]:
        return [
            link.parent.user
            for link in self.parent_links
            if link.parent and link.parent.user
        ]


class ParentStudent(db.Model):
    """Relación N:M entre tutores y estudiantes (con datos de la relación)."""

    __tablename__ = "parent_students"

    parent_id = db.Column(
        db.Integer, db.ForeignKey("parents.id", ondelete="CASCADE"), primary_key=True
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), primary_key=True
    )
    relationship = db.Column(db.String(40))
    is_primary = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    parent = db.relationship("Parent", back_populates="student_links")
    student = db.relationship("Student", back_populates="parent_links")


class Teacher(TimestampMixin, db.Model):
    """Perfil ampliado del docente."""

    __tablename__ = "teachers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    employee_code = db.Column(db.String(30), unique=True)
    specialty = db.Column(db.String(120))
    hire_date = db.Column(db.Date)

    user = db.relationship("User", back_populates="teacher_profile")
    course_assignments = db.relationship(
        "CourseAssignment", back_populates="teacher", cascade="all, delete-orphan"
    )

    @property
    def courses(self) -> list["Course"]:
        """Cursos únicos asignados al docente."""
        seen: dict[int, "Course"] = {}
        for assignment in self.course_assignments:
            if assignment.course:
                seen[assignment.course.id] = assignment.course
        return list(seen.values())


# ---------------------------------------------------------------------------
# Estructura académica
# ---------------------------------------------------------------------------
class Course(TimestampMixin, db.Model):
    """Curso / nivel educativo dentro de un año académico."""

    __tablename__ = "courses"
    __table_args__ = (
        db.UniqueConstraint(
            "name", "parallel", "academic_year", name="uq_courses_name_parallel_year"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    level = db.Column(db.String(60))  # Inicial / Primaria / Secundaria / Técnico
    parallel = db.Column(db.String(10), nullable=False, default="A")
    academic_year = db.Column(
        db.Integer, nullable=False, default=lambda: date.today().year
    )
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    assignments = db.relationship(
        "CourseAssignment", back_populates="course", cascade="all, delete-orphan"
    )
    enrollments = db.relationship(
        "StudentEnrollment", back_populates="course", cascade="all, delete-orphan"
    )
    announcements = db.relationship(
        "AnnouncementRecipient", back_populates="course", cascade="all, delete-orphan"
    )
    class_assignments = db.relationship(
        "Assignment", back_populates="course", cascade="all, delete-orphan"
    )
    subject_links = db.relationship(
        "CourseSubject", back_populates="course", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        base = f"{self.name} {self.parallel}".strip()
        level = f" - {self.level}" if self.level else ""
        return f"{base}{level} ({self.academic_year})"

    @property
    def active_students(self) -> list["Student"]:
        return [
            e.student
            for e in self.enrollments
            if e.status == "activo" and e.student is not None
        ]

    @property
    def total_students(self) -> int:
        return len(self.active_students)

    def teachers(self) -> list["Teacher"]:
        seen: dict[int, "Teacher"] = {}
        for assignment in self.assignments:
            if assignment.teacher:
                seen[assignment.teacher.id] = assignment.teacher
        return list(seen.values())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Course {self.label}>"


class CourseAssignment(TimestampMixin, db.Model):
    """Asignación de un docente a un curso en una materia."""

    __tablename__ = "course_assignments"
    __table_args__ = (
        db.UniqueConstraint(
            "teacher_id", "course_id", "subject", name="uq_course_assignment"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(
        db.Integer, db.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    subject = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    teacher = db.relationship("Teacher", back_populates="course_assignments")
    course = db.relationship("Course", back_populates="assignments")

    @property
    def label(self) -> str:
        return f"{self.course.label} · {self.subject}" if self.course else self.subject


class StudentEnrollment(TimestampMixin, db.Model):
    """Inscripción de un estudiante en un curso y año académico."""

    __tablename__ = "student_enrollments"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id",
            "course_id",
            "academic_year",
            name="uq_enrollment_student_course",
        ),
        db.CheckConstraint(
            "status IN ('activo','retirado','egresado')", name="ck_enrollment_status"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = db.Column(
        db.Integer,
        db.ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    academic_year = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="activo")

    student = db.relationship("Student", back_populates="enrollments")
    course = db.relationship("Course", back_populates="enrollments")


# ---------------------------------------------------------------------------
# Comunicados oficiales
# ---------------------------------------------------------------------------
class Announcement(TimestampMixin, db.Model):
    """Comunicado oficial emitido por dirección, administración o docentes."""

    __tablename__ = "announcements"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_announcement_status"
        ),
        db.CheckConstraint(
            "priority IN ('baja','normal','alta','urgente')",
            name="ck_announcement_priority",
        ),
        db.CheckConstraint(
            "audience IN ('public','internal')", name="ck_announcement_audience"
        ),
        db.Index("ix_announcements_status_publication", "status", "published_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.String(300))
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(30), nullable=False, default="general", index=True)
    priority = db.Column(db.String(20), nullable=False, default="normal")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    audience = db.Column(db.String(20), nullable=False, default="public")
    target_role = db.Column(db.String(20))  # parent / teacher / None = todos
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    published_at = db.Column(db.DateTime, index=True)
    expires_at = db.Column(db.Date)

    attachment_path = db.Column(db.String(255))
    attachment_name = db.Column(db.String(255))
    attachment_mime = db.Column(db.String(120))
    attachment_size = db.Column(db.Integer)
    # ``local`` (UPLOAD_FOLDER) o ``supabase`` (Storage permanente).
    attachment_storage = db.Column(db.String(20), nullable=False, default="local")
    attachment_url = db.Column(db.String(700))

    author_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    author = db.relationship("User", foreign_keys=[author_id])

    recipients = db.relationship(
        "AnnouncementRecipient",
        back_populates="announcement",
        cascade="all, delete-orphan",
    )

    # --- Reglas de visibilidad ---------------------------------------
    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < date.today()

    @property
    def is_live(self) -> bool:
        """Publicado y vigente (no vencido)."""
        return self.status == "published" and not self.is_expired

    @property
    def is_public(self) -> bool:
        return self.audience == "public"

    @property
    def category_label(self) -> str:
        return ANNOUNCEMENT_CATEGORY_LABELS.get(self.category, self.category)

    @property
    def priority_label(self) -> str:
        return PRIORITY_LABELS.get(self.priority, self.priority)

    @property
    def status_label(self) -> str:
        return ANNOUNCEMENT_STATUS_LABELS.get(self.status, self.status)

    @property
    def audience_label(self) -> str:
        return AUDIENCE_LABELS.get(self.audience, self.audience)

    @property
    def course_labels(self) -> list[str]:
        return [r.course.label for r in self.recipients if r.course]

    def is_visible_to(self, user) -> bool:
        """¿Puede este usuario ver el comunicado en su panel?"""
        if not self.is_live:
            return False
        if user is None:
            return self.is_public
        if user.is_staff:
            return True
        if self.audience == "public":
            return True
        if self.target_role and self.target_role != user.role:
            return False
        if self.target_role is None and user.role not in (
            "parent",
            "teacher",
            "student",
        ):
            return False
        # Restricción por cursos: el usuario debe pertenecer a alguno de ellos
        if self.recipients:
            allowed_ids = {r.course_id for r in self.recipients}
            if user.role == "parent":
                profile = user.parent_profile
                if not profile:
                    return False
                student_courses = {
                    st.current_course.id
                    for st in profile.students
                    if st.current_course is not None
                }
                return bool(allowed_ids & student_courses)
            if user.role == "teacher":
                profile = user.teacher_profile
                if not profile:
                    return False
                return bool(allowed_ids & {c.id for c in profile.courses})
            return False
        return True

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Announcement {self.title!r} ({self.status})>"


class AnnouncementRecipient(db.Model):
    """Curso destinatario de un comunicado interno."""

    __tablename__ = "announcement_recipients"
    __table_args__ = (
        db.UniqueConstraint(
            "announcement_id", "course_id", name="uq_announcement_course"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(
        db.Integer,
        db.ForeignKey("announcements.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )

    announcement = db.relationship("Announcement", back_populates="recipients")
    course = db.relationship("Course", back_populates="announcements")


# ---------------------------------------------------------------------------
# Calendario escolar
# ---------------------------------------------------------------------------
class Event(TimestampMixin, db.Model):
    """Evento del calendario escolar (público o interno)."""

    __tablename__ = "events"
    __table_args__ = (
        db.CheckConstraint("audience IN ('public','internal')", name="ck_event_audience"),
        db.Index("ix_events_date", "start_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_date = db.Column(db.Date)
    location = db.Column(db.String(160))
    category = db.Column(db.String(30), nullable=False, default="otro", index=True)
    audience = db.Column(db.String(20), nullable=False, default="public")
    target_role = db.Column(db.String(20))
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="SET NULL"))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    is_cancelled = db.Column(db.Boolean, nullable=False, default=False)

    course = db.relationship("Course")

    @property
    def category_label(self) -> str:
        return EVENT_CATEGORY_LABELS.get(self.category, self.category)

    @property
    def audience_label(self) -> str:
        return AUDIENCE_LABELS.get(self.audience, self.audience)

    @property
    def time_label(self) -> str:
        return self.start_time.strftime("%H:%M") if self.start_time else ""

    def is_visible_to(self, user) -> bool:
        if self.audience == "public":
            return True
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        if user.is_staff:
            return True
        if self.target_role and self.target_role != user.role:
            return False
        if self.course_id:
            if user.role == "parent" and user.parent_profile:
                ids = {
                    st.current_course.id
                    for st in user.parent_profile.students
                    if st.current_course
                }
                return self.course_id in ids
            if user.role == "teacher" and user.teacher_profile:
                return self.course_id in {c.id for c in user.teacher_profile.courses}
            return False
        return True


# ---------------------------------------------------------------------------
# Módulos académicos: tareas, asistencia y calificaciones
# ---------------------------------------------------------------------------
class Assignment(TimestampMixin, db.Model):
    """Tarea, actividad o evaluación registrada por un docente para un curso."""

    __tablename__ = "assignments"
    __table_args__ = (
        db.CheckConstraint(
            "kind IN ('tarea','evaluacion','actividad')", name="ck_assignment_kind"
        ),
        db.Index("ix_assignments_course_due", "course_id", "due_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id", ondelete="SET NULL"))
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text)
    kind = db.Column(db.String(20), nullable=False, default="tarea")
    subject = db.Column(db.String(80))
    due_date = db.Column(db.Date)
    max_score = db.Column(db.Float)
    is_published = db.Column(db.Boolean, nullable=False, default=True)

    course = db.relationship("Course", back_populates="class_assignments")
    teacher = db.relationship("Teacher")
    grades = db.relationship("Grade", back_populates="assignment")

    @property
    def kind_label(self) -> str:
        return ASSIGNMENT_KIND_LABELS.get(self.kind, self.kind)

    @property
    def is_overdue(self) -> bool:
        return self.due_date is not None and self.due_date < date.today()


class Attendance(db.Model):
    """Registro diario de asistencia por estudiante y curso."""

    __tablename__ = "attendance"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "course_id", "date", name="uq_attendance_student_course_date"
        ),
        db.CheckConstraint(
            "status IN ('presente','ausente','tarde','justificado')",
            name="ck_attendance_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="presente")
    notes = db.Column(db.String(200))
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    student = db.relationship("Student", back_populates="attendance_records")
    course = db.relationship("Course")

    @property
    def status_label(self) -> str:
        return ATTENDANCE_STATUS_LABELS.get(self.status, self.status)


class Grade(db.Model):
    """Calificación de un estudiante en una evaluación o periodo."""

    __tablename__ = "grades"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "assignment_id", "period", name="uq_grade_student_assignment"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    assignment_id = db.Column(
        db.Integer, db.ForeignKey("assignments.id", ondelete="SET NULL")
    )
    period = db.Column(db.String(20), nullable=False, default="1")
    score = db.Column(db.Float, nullable=False)
    max_score = db.Column(db.Float, nullable=False, default=100.0)
    observations = db.Column(db.String(200))
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    student = db.relationship("Student", back_populates="grades")
    course = db.relationship("Course")
    assignment = db.relationship("Assignment", back_populates="grades")

    @property
    def percentage(self) -> float:
        if not self.max_score:
            return 0.0
        return round((self.score / self.max_score) * 100, 1)


# ---------------------------------------------------------------------------
# Mensajería interna y notificaciones
# ---------------------------------------------------------------------------
class Message(db.Model):
    """Mensaje interno entre usuarios de la plataforma (con respuestas)."""

    __tablename__ = "messages"
    __table_args__ = (db.Index("ix_messages_recipient_read", "recipient_id", "read_at"),)

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    subject = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("messages.id", ondelete="SET NULL"))
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])
    parent = db.relationship("Message", remote_side=[id])

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


class Notification(db.Model):
    """Notificación interna asociada a un usuario concreto."""

    __tablename__ = "notifications"
    __table_args__ = (db.Index("ix_notifications_user_read", "user_id", "read_at"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title = db.Column(db.String(180), nullable=False)
    body = db.Column(db.String(400))
    link = db.Column(db.String(255))
    category = db.Column(db.String(40), default="general")
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="notifications")

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


class ContactMessage(db.Model):
    """Mensaje recibido desde el formulario público de contacto."""

    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180))
    phone = db.Column(db.String(40))
    subject = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(60))
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    @property
    def excerpt(self) -> str:
        return (self.body[:120] + "…") if len(self.body) > 120 else self.body


class AuditLog(db.Model):
    """Registro de acciones administrativas relevantes."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    actor_name = db.Column(db.String(160))
    action = db.Column(db.String(80), nullable=False, index=True)
    entity = db.Column(db.String(60))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.String(400))
    ip_address = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    actor = db.relationship("User")


class InstitutionSetting(db.Model):
    """Ajustes institucionales editables (clave / valor).

    Los datos que la institución aún no ha confirmado se almacenan vacíos y la
    interfaz los muestra como "información pendiente de actualización".
    """

    __tablename__ = "institution_settings"

    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    @staticmethod
    def get(key: str, default: str = "") -> str:
        row = db.session.get(InstitutionSetting, key)
        return row.value if row and row.value else default

    @staticmethod
    def set(key: str, value: str) -> None:
        row = db.session.get(InstitutionSetting, key)
        if row is None:
            row = InstitutionSetting(key=key, value=value)
            db.session.add(row)
        else:
            row.value = value


# ===========================================================================
# NUEVA CANAÁN NOTICIAS: muro público de publicaciones
# ===========================================================================
NEWS_CATEGORIES = (
    "institucional",
    "civico",
    "deportivo",
    "campeonato",
    "convocatoria",
    "comunicado",
    "evento",
    "cultural",
)

NEWS_CATEGORY_LABELS = {
    "institucional": "Noticia institucional",
    "civico": "Acto cívico y desfile",
    "deportivo": "Actividad deportiva",
    "campeonato": "Campeonato y competencia",
    "convocatoria": "Convocatoria",
    "comunicado": "Comunicado oficial",
    "evento": "Evento institucional",
    "cultural": "Actividad cultural",
}

NEWS_STATUSES = ("draft", "published", "archived")

NEWS_STATUS_LABELS = {
    "draft": "Borrador",
    "published": "Publicada",
    "archived": "Archivada",
}

NEWS_COMMENT_STATUSES = ("approved", "hidden")

NEWS_COMMENT_STATUS_LABELS = {
    "approved": "Visible",
    "hidden": "Oculto",
}


class NewsPost(TimestampMixin, db.Model):
    """Publicación del muro de NUEVA CANAÁN NOTICIAS.

    Cada publicación puede llevar una fotografía principal (ver ``cover_image``),
    reacciones anónimas ("me gusta") y comentarios moderables.
    """

    __tablename__ = "news_posts"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('draft','published','archived')", name="ck_news_post_status"
        ),
        db.Index("ix_news_posts_status_publication", "status", "published_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.String(300))
    body = db.Column(db.Text, nullable=False)
    category = db.Column(
        db.String(30), nullable=False, default="institucional", index=True
    )
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    allow_comments = db.Column(db.Boolean, nullable=False, default=True)
    published_at = db.Column(db.DateTime, index=True)
    # Identificador de la publicación del muro anterior (migración histórica).
    legacy_post_id = db.Column(db.Integer, unique=True)

    author_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    author = db.relationship("User", foreign_keys=[author_id])

    images = db.relationship(
        "NewsImage",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="NewsImage.position",
    )
    comments = db.relationship(
        "NewsComment",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="NewsComment.created_at",
    )
    reactions = db.relationship(
        "NewsReaction", back_populates="post", cascade="all, delete-orphan"
    )

    # --- Presentación -------------------------------------------------
    @property
    def cover_image(self):
        """Fotografía principal de la publicación (la primera cargada)."""
        return self.images[0] if self.images else None

    @property
    def excerpt(self) -> str:
        """Texto corto para las tarjetas del muro."""
        text = (self.summary or self.body or "").strip()
        if len(text) <= 260:
            return text
        return text[:257].rstrip() + "…"

    @property
    def category_label(self) -> str:
        return NEWS_CATEGORY_LABELS.get(self.category, self.category)

    @property
    def status_label(self) -> str:
        return NEWS_STATUS_LABELS.get(self.status, self.status)

    @property
    def author_name(self) -> str:
        return self.author.full_name if self.author else "Equipo de comunicación"

    @property
    def likes_count(self) -> int:
        return len(self.reactions)

    @property
    def comments_count(self) -> int:
        return sum(1 for comment in self.comments if comment.status == "approved")

    @property
    def is_published(self) -> bool:
        return self.status == "published"

    def is_visible_to(self, user) -> bool:
        """El público sólo ve publicaciones publicadas; el personal ve todo."""
        if self.status == "published":
            return True
        return bool(user is not None and getattr(user, "is_staff", False))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NewsPost {self.title!r} ({self.status})>"


class NewsImage(db.Model):
    """Fotografía asociada a una publicación del muro de noticias."""

    __tablename__ = "news_images"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(
        db.Integer,
        db.ForeignKey("news_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path = db.Column(db.String(255), nullable=False)  # ruta interna del backend
    name = db.Column(db.String(255))
    mime = db.Column(db.String(120))
    size = db.Column(db.Integer)
    alt = db.Column(db.String(180))
    position = db.Column(db.Integer, nullable=False, default=0)
    # ``local`` (UPLOAD_FOLDER) o ``supabase`` (Storage permanente).
    storage = db.Column(
        db.String(20), nullable=False, default="local", server_default="local"
    )
    url = db.Column(db.String(700))
    legacy_image_id = db.Column(db.Integer, unique=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    post = db.relationship("NewsPost", back_populates="images")

    @property
    def display_url(self) -> str | None:
        """URL remota de la fotografía (``None`` si se sirve localmente)."""
        from .storage import display_url

        return display_url(self.storage, self.path, self.url)

    @property
    def is_available(self) -> bool:
        """¿La fotografía sigue disponible?

        En Render el disco es efímero, por eso las imágenes nuevas viven en
        Supabase Storage. Las antiguas (``storage='local'``) se comprueban en
        disco para no mostrar imágenes rotas si se perdió el archivo.
        """
        from flask import current_app  # importación local: evita ciclos

        if not self.path:
            return False
        if (self.storage or "local") == "supabase":
            return True
        try:
            base = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
            target = (base / self.path).resolve()
        except (KeyError, OSError, ValueError):
            return False
        if base != target and base not in target.parents:
            return False
        return target.is_file()

    @property
    def display_url(self) -> str | None:
        """URL remota de la fotografía (``None`` si se sirve localmente)."""
        from .storage import display_url

        return display_url(self.storage, self.path, self.url)

    @property
    def alt_text(self) -> str:
        return self.alt or (self.post.title if self.post else "Fotografía institucional")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NewsImage {self.path!r}>"


class NewsReaction(db.Model):
    """Reacción "me gusta" de un visitante anónimo o de un usuario con sesión."""

    __tablename__ = "news_reactions"
    __table_args__ = (
        db.UniqueConstraint("post_id", "visitor_key", name="uq_news_reaction_visitor"),
    )

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(
        db.Integer,
        db.ForeignKey("news_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    visitor_key = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    post = db.relationship("NewsPost", back_populates="reactions")
    user = db.relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NewsReaction post={self.post_id} visitor={self.visitor_key}>"


class NewsComment(db.Model):
    """Comentario del público en una publicación del muro."""

    __tablename__ = "news_comments"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('approved','hidden')", name="ck_news_comment_status"
        ),
        db.Index("ix_news_comments_post_status", "post_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(
        db.Integer,
        db.ForeignKey("news_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_name = db.Column(db.String(80), nullable=False)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="approved", index=True)
    visitor_key = db.Column(db.String(64))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    ip_address = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    post = db.relationship("NewsPost", back_populates="comments")
    user = db.relationship("User")

    @property
    def status_label(self) -> str:
        return NEWS_COMMENT_STATUS_LABELS.get(self.status, self.status)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NewsComment post={self.post_id} {self.author_name!r}>"


# ===========================================================================
# GESTIÓN ACADÉMICA: años, trimestres, materias, calificaciones y asistencia
# ===========================================================================
MEDIA_CATEGORIES = (
    "galeria",
    "actividad",
    "deportivo",
    "civico",
    "cultural",
    "academico",
    "institucional",
)

MEDIA_CATEGORY_LABELS = {
    "galeria": "Galería institucional",
    "actividad": "Actividad del colegio",
    "deportivo": "Actividad deportiva",
    "civico": "Acto cívico",
    "cultural": "Actividad cultural",
    "academico": "Actividad académica",
    "institucional": "Institucional",
}

TRIMESTER_NAMES = {1: "Primer trimestre", 2: "Segundo trimestre", 3: "Tercer trimestre"}


class SchoolYear(TimestampMixin, db.Model):
    """Año escolar (gestión) que agrupa los trimestres."""

    __tablename__ = "school_years"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), unique=True, nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    trimesters = db.relationship(
        "Trimester",
        back_populates="school_year",
        cascade="all, delete-orphan",
        order_by="Trimester.number",
    )

    @property
    def label(self) -> str:
        return self.name

    @property
    def current_trimester(self) -> "Trimester | None":
        today = date.today()
        for trimester in self.trimesters:
            if (
                trimester.start_date
                and trimester.end_date
                and trimester.start_date <= today <= trimester.end_date
            ):
                return trimester
        return next(
            (t for t in self.trimesters if not t.is_closed and t.start_date
             and t.start_date >= today),
            None,
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SchoolYear {self.name!r}>"


class Trimester(TimestampMixin, db.Model):
    """Trimestre de un año escolar (periodo de evaluación)."""

    __tablename__ = "trimesters"
    __table_args__ = (
        db.UniqueConstraint(
            "school_year_id", "number", name="uq_trimesters_year_number"
        ),
        db.CheckConstraint(
            "number BETWEEN 1 AND 3", name="ck_trimesters_number"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_year_id = db.Column(
        db.Integer,
        db.ForeignKey("school_years.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_closed = db.Column(db.Boolean, nullable=False, default=False)

    school_year = db.relationship("SchoolYear", back_populates="trimesters")
    grades = db.relationship(
        "SubjectGrade", back_populates="trimester", cascade="all, delete-orphan"
    )
    observations = db.relationship(
        "AcademicObservation",
        back_populates="trimester",
        cascade="all, delete-orphan",
    )

    @property
    def label(self) -> str:
        return TRIMESTER_NAMES.get(self.number, f"Trimestre {self.number}")

    @property
    def short_label(self) -> str:
        return f"{self.number}° trimestre"

    @property
    def full_label(self) -> str:
        year = self.school_year.name if self.school_year else ""
        return f"{year} · {self.short_label}".strip(" ·")

    @property
    def is_current(self) -> bool:
        if not (self.start_date and self.end_date):
            return False
        return self.start_date <= date.today() <= self.end_date

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Trimester {self.number} year={self.school_year_id}>"


class Subject(TimestampMixin, db.Model):
    """Materia o área curricular."""

    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True)
    area = db.Column(db.String(60))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    course_links = db.relationship(
        "CourseSubject", back_populates="subject", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        return f"{self.name} ({self.code})" if self.code else self.name

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subject {self.name!r}>"


class CourseSubject(TimestampMixin, db.Model):
    """Materia asignada a un curso con su docente responsable."""

    __tablename__ = "course_subjects"
    __table_args__ = (
        db.UniqueConstraint("course_id", "subject_id", name="uq_course_subject"),
    )

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(
        db.Integer,
        db.ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_id = db.Column(
        db.Integer,
        db.ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    teacher_id = db.Column(
        db.Integer, db.ForeignKey("teachers.id", ondelete="SET NULL")
    )
    weekly_hours = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    course = db.relationship("Course", back_populates="subject_links")
    subject = db.relationship("Subject", back_populates="course_links")
    teacher = db.relationship("Teacher", foreign_keys=[teacher_id])
    grades = db.relationship(
        "SubjectGrade", back_populates="course_subject", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        course = self.course.label if self.course else "Curso"
        return f"{course} · {self.subject.name if self.subject else 'Materia'}"

    @property
    def teacher_name(self) -> str:
        if self.teacher and self.teacher.user:
            return self.teacher.user.full_name
        return "Sin asignar"

    def grade_for(self, student_id: int, trimester_id: int) -> "SubjectGrade | None":
        return next(
            (
                grade
                for grade in self.grades
                if grade.student_id == student_id
                and grade.trimester_id == trimester_id
            ),
            None,
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CourseSubject course={self.course_id} subject={self.subject_id}>"


class AcademicConfig(db.Model):
    """Escala de calificación configurada por la institución.

    No se asume ninguna escala por defecto: mientras no se configuren los
    valores, la plataforma muestra las calificaciones sin emitir un estado de
    aprobación. El administrador define mínimo, máximo y nota de aprobación.
    """

    __tablename__ = "academic_config"

    id = db.Column(db.Integer, primary_key=True, default=1)
    min_score = db.Column(db.Float)
    max_score = db.Column(db.Float)
    passing_score = db.Column(db.Float)
    decimals = db.Column(db.Integer, nullable=False, default=0)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    updated_at = db.Column(
        db.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    updated_by_user = db.relationship("User", foreign_keys=[updated_by])

    @property
    def is_configured(self) -> bool:
        return (
            self.min_score is not None
            and self.max_score is not None
            and self.passing_score is not None
            and self.max_score > self.min_score
        )

    @property
    def scale_label(self) -> str:
        if not self.is_configured:
            return "Escala sin configurar"
        return (
            f"{self.format(self.min_score)} a {self.format(self.max_score)} · "
            f"aprobación desde {self.format(self.passing_score)}"
        )

    def format(self, value: float | None) -> str:
        if value is None:
            return "—"
        try:
            decimals = max(0, min(3, int(self.decimals or 0)))
        except (TypeError, ValueError):
            decimals = 0
        return f"{float(value):.{decimals}f}"

    def validate(self, value: float) -> tuple[bool, str]:
        """Valida una calificación contra la escala configurada."""
        if value is None:
            return False, "Falta la calificación."
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False, "La calificación debe ser un número."
        if number != number or number in (float("inf"), float("-inf")):
            return False, "La calificación no es un número válido."
        if self.min_score is not None and number < self.min_score:
            return False, f"La nota mínima permitida es {self.format(self.min_score)}."
        if self.max_score is not None and number > self.max_score:
            return False, f"La nota máxima permitida es {self.format(self.max_score)}."
        return True, ""

    def status_for(self, value: float | None) -> str | None:
        """``aprobado`` / ``reprobado``; ``None`` si no hay escala configurada."""
        if value is None or not self.is_configured or self.passing_score is None:
            return None
        return "aprobado" if float(value) >= float(self.passing_score) else "reprobado"

    @property
    def range(self) -> float | None:
        if not self.is_configured:
            return None
        return float(self.max_score) - float(self.min_score)

    def percentage(self, value: float | None) -> float | None:
        """Ubicación de la nota dentro de la escala (0-100), sin asumir 0-100."""
        if value is None or not self.range:
            return None
        position = (float(value) - float(self.min_score)) / self.range * 100
        return round(max(0.0, min(100.0, position)), 1)

    @classmethod
    def current(cls) -> "AcademicConfig":
        """Configuración guardada o una instancia vacía (sin persistir)."""
        row = db.session.get(cls, 1)
        return row if row is not None else cls(id=1, decimals=0)

    @classmethod
    def get_or_create(cls) -> "AcademicConfig":
        row = db.session.get(cls, 1)
        if row is None:
            row = cls(id=1, decimals=0)
            db.session.add(row)
        return row

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AcademicConfig configured={self.is_configured}>"


class SubjectGrade(TimestampMixin, db.Model):
    """Calificación final de una materia en un trimestre."""

    __tablename__ = "subject_grades"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id",
            "course_subject_id",
            "trimester_id",
            name="uq_subject_grade_student_subject_trimester",
        ),
        db.Index(
            "ix_subject_grades_trimester_course_subject",
            "trimester_id",
            "course_subject_id",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_subject_id = db.Column(
        db.Integer,
        db.ForeignKey("course_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trimester_id = db.Column(
        db.Integer,
        db.ForeignKey("trimesters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score = db.Column(db.Float, nullable=False)
    observations = db.Column(db.String(300))
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    student = db.relationship("Student", foreign_keys=[student_id])
    course_subject = db.relationship("CourseSubject", back_populates="grades")
    trimester = db.relationship("Trimester", back_populates="grades")
    recorder = db.relationship("User", foreign_keys=[recorded_by])
    updater = db.relationship("User", foreign_keys=[updated_by])

    @property
    def config(self) -> AcademicConfig:
        return AcademicConfig.current()

    @property
    def display_score(self) -> str:
        return self.config.format(self.score)

    @property
    def status(self) -> str | None:
        return self.config.status_for(self.score)

    @property
    def percentage(self) -> float | None:
        return self.config.percentage(self.score)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SubjectGrade student={self.student_id} score={self.score}>"


class GradeChange(db.Model):
    """Historial de modificaciones de calificaciones (auditoría)."""

    __tablename__ = "grade_changes"

    id = db.Column(db.Integer, primary_key=True)
    subject_grade_id = db.Column(
        db.Integer, db.ForeignKey("subject_grades.id", ondelete="SET NULL")
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    course_subject_id = db.Column(
        db.Integer, db.ForeignKey("course_subjects.id", ondelete="SET NULL")
    )
    trimester_id = db.Column(
        db.Integer, db.ForeignKey("trimesters.id", ondelete="SET NULL")
    )
    previous_score = db.Column(db.Float)
    new_score = db.Column(db.Float)
    reason = db.Column(db.String(300))
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    student = db.relationship("Student", foreign_keys=[student_id])
    course_subject = db.relationship("CourseSubject", foreign_keys=[course_subject_id])
    trimester = db.relationship("Trimester", foreign_keys=[trimester_id])
    actor = db.relationship("User", foreign_keys=[changed_by])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GradeChange student={self.student_id} {self.previous_score}->{self.new_score}>"


class AcademicObservation(TimestampMixin, db.Model):
    """Observación pedagógica del estudiante en un trimestre."""

    __tablename__ = "academic_observations"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "trimester_id", name="uq_observation_student_trimester"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trimester_id = db.Column(
        db.Integer,
        db.ForeignKey("trimesters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="SET NULL"))
    body = db.Column(db.Text, nullable=False)
    is_visible_to_parents = db.Column(db.Boolean, nullable=False, default=True)
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    student = db.relationship("Student", foreign_keys=[student_id])
    trimester = db.relationship("Trimester", back_populates="observations")
    course = db.relationship("Course", foreign_keys=[course_id])
    recorder = db.relationship("User", foreign_keys=[recorded_by])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AcademicObservation student={self.student_id} trimester={self.trimester_id}>"


class MediaFile(TimestampMixin, db.Model):
    """Fotografía institucional con metadatos y control de publicación.

    ``storage`` indica dónde vive el archivo (Supabase Storage o disco local) y
    ``path`` su ruta interna. ``parental_consent`` documenta la autorización de
    uso de imagen; sólo las fotografías públicas **con** autorización aparecen
    en la galería del sitio.
    """

    __tablename__ = "media_files"

    id = db.Column(db.Integer, primary_key=True)
    storage = db.Column(db.String(20), nullable=False, default="local")
    path = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(700))
    name = db.Column(db.String(255))
    mime = db.Column(db.String(120))
    size = db.Column(db.Integer)
    caption = db.Column(db.String(300))
    category = db.Column(db.String(40), nullable=False, default="galeria", index=True)
    event_name = db.Column(db.String(160))
    taken_on = db.Column(db.Date, index=True)
    is_public = db.Column(db.Boolean, nullable=False, default=True)
    parental_consent = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    related_post_id = db.Column(
        db.Integer, db.ForeignKey("news_posts.id", ondelete="SET NULL")
    )
    related_event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="SET NULL")
    )
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    related_post = db.relationship("NewsPost", foreign_keys=[related_post_id])
    related_event = db.relationship("Event", foreign_keys=[related_event_id])
    uploader = db.relationship("User", foreign_keys=[uploaded_by])

    @property
    def display_url(self) -> str | None:
        from .storage import display_url

        return display_url(self.storage, self.path, self.url)

    @property
    def category_label(self) -> str:
        return MEDIA_CATEGORY_LABELS.get(self.category, self.category)

    @property
    def can_publish(self) -> bool:
        return bool(self.is_active and self.is_public and self.parental_consent)

    @property
    def is_available(self) -> bool:
        if not self.path:
            return False
        if (self.storage or "local") == "supabase":
            return True
        try:
            from .storage import local_file

            return local_file(self.path).is_file()
        except (KeyError, OSError, ValueError):
            return False

    @property
    def alt_text(self) -> str:
        return self.caption or self.event_name or "Fotografía institucional"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MediaFile {self.path!r} ({self.storage})>"







