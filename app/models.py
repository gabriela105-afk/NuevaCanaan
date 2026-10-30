"""Modelos de datos de la plataforma institucional Nueva Canaán.

Diseño relacional normalizado sobre SQLite (desarrollo) o PostgreSQL (opcional).
Las claves foráneas se validan a nivel de base de datos: ver el PRAGMA activado
en ``app/extensions.py``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

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







