"""Portal de padres, madres y tutores (acceso restringido a sus estudiantes)."""

from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, abort, current_app, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    Announcement,
    Assignment,
    Attendance,
    Course,
    Event,
    Grade,
    Notification,
    Student,
    utcnow,
)
from ..utils import role_required

parents_bp = Blueprint("parents", __name__, url_prefix="/portal")


def _profile():
    profile = current_user.parent_profile
    if profile is None:
        abort(403)
    return profile


def _linked_student(student_id: int) -> Student:
    """Devuelve el estudiante sólo si está vinculado a la cuenta actual."""
    student = db.session.get(Student, student_id)
    if student is None:
        abort(404)
    profile = _profile()
    if not profile.is_linked_to(student.id):
        current_app.logger.warning(
            "Acceso denegado a estudiante %s por usuario %s", student_id, current_user.id
        )
        abort(403)
    return student


def _visible_announcements(limit: int | None = None) -> list[Announcement]:
    today = date.today()
    query = Announcement.query.filter(
        Announcement.status == "published",
        or_(Announcement.expires_at.is_(None), Announcement.expires_at >= today),
    ).order_by(
        Announcement.is_pinned.desc(),
        Announcement.published_at.desc(),
        Announcement.id.desc(),
    )
    items = [item for item in query.all() if item.is_visible_to(current_user)]
    return items[:limit] if limit else items


def _visible_events(date_from: date, date_to: date) -> list[Event]:
    events = (
        Event.query.filter(
            Event.start_date >= date_from,
            Event.start_date <= date_to,
            Event.is_cancelled.is_(False),
        )
        .order_by(Event.start_date, Event.start_time)
        .all()
    )
    return [event for event in events if event.is_visible_to(current_user)]


@parents_bp.get("/")
@login_required
@role_required("parent")
def dashboard():
    profile = _profile()
    students = profile.students
    today = date.today()

    course_ids = [st.current_course.id for st in students if st.current_course]
    pending_assignments = (
        Assignment.query.filter(
            Assignment.course_id.in_(course_ids),
            Assignment.is_published.is_(True),
            Assignment.due_date >= today,
        )
        .order_by(Assignment.due_date)
        .limit(6)
        .all()
        if course_ids
        else []
    )

    unread = (
        Notification.query.filter_by(user_id=current_user.id, read_at=None)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )

    attendance_summary = {}
    for student in students:
        records = (
            Attendance.query.filter_by(student_id=student.id)
            .order_by(Attendance.date.desc())
            .limit(30)
            .all()
        )
        present = sum(1 for r in records if r.status in ("presente", "justificado"))
        attendance_summary[student.id] = {
            "total": len(records),
            "present": present,
            "rate": round((present / len(records)) * 100) if records else None,
        }

    return render_template(
        "parents/dashboard.html",
        profile=profile,
        students=students,
        announcements=_visible_announcements(limit=5),
        events=_visible_events(today, today + timedelta(days=60))[:5],
        pending_assignments=pending_assignments,
        unread=unread,
        attendance_summary=attendance_summary,
    )


@parents_bp.get("/hijos")
@login_required
@role_required("parent")
def children():
    return render_template("parents/children.html", profile=_profile(), students=_profile().students)


@parents_bp.get("/hijos/<int:student_id>")
@login_required
@role_required("parent")
def child_detail(student_id: int):
    student = _linked_student(student_id)
    course = student.current_course

    attendance = (
        Attendance.query.filter_by(student_id=student.id)
        .order_by(Attendance.date.desc())
        .limit(60)
        .all()
    )
    present = sum(1 for a in attendance if a.status in ("presente", "justificado"))

    grades = (
        Grade.query.filter_by(student_id=student.id)
        .order_by(Grade.created_at.desc())
        .all()
    )
    assignments = (
        Assignment.query.filter_by(course_id=course.id, is_published=True)
        .order_by(Assignment.due_date.desc().nulls_last())
        .limit(15)
        .all()
        if course
        else []
    )
    subjects = sorted({a.subject for a in course.assignments if a.subject}) if course else []

    return render_template(
        "parents/child.html",
        student=student,
        course=course,
        attendance=attendance,
        attendance_rate=round((present / len(attendance)) * 100) if attendance else None,
        grades=grades,
        assignments=assignments,
        subjects=subjects,
        today=date.today(),
    )


@parents_bp.get("/comunicados")
@login_required
@role_required("parent")
def announcements():
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config["ITEMS_PER_PAGE"]
    items = _visible_announcements()
    start = (page - 1) * per_page
    return render_template(
        "parents/announcements.html",
        announcements=items[start : start + per_page],
        total=len(items),
        page=page,
        per_page=per_page,
    )


@parents_bp.get("/calendario")
@login_required
@role_required("parent")
def calendar():
    today = date.today()
    return render_template(
        "parents/calendar.html",
        upcoming=_visible_events(today, today + timedelta(days=180)),
        today=today,
        generated_at=utcnow(),
    )
