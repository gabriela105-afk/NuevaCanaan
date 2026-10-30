"""Páginas públicas: inicio, institución, galería, calendario y contacto."""

from __future__ import annotations

import calendar as pycalendar
import time
from datetime import date, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import Announcement, ContactMessage, Event, User, utcnow
from ..utils import (
    clean,
    clean_multiline,
    client_ip,
    gallery_images,
    is_valid_email,
    notify_many,
)

main_bp = Blueprint("main", __name__)

CONTACT_LIMIT = 5
CONTACT_WINDOW_SECONDS = 3600


def _visible_events(date_from: date, date_to: date) -> list[Event]:
    """Eventos del rango visibles para el usuario actual."""
    events = (
        Event.query.filter(
            Event.start_date >= date_from,
            Event.start_date <= date_to,
            Event.is_cancelled.is_(False),
        )
        .order_by(Event.start_date, Event.start_time)
        .all()
    )
    user = current_user if current_user.is_authenticated else None
    return [event for event in events if event.is_visible_to(user)]


def _contact_rate_limited() -> bool:
    """Límite simple de envíos por sesión (además del campo trampa)."""
    now = time.time()
    stamps = [
        s for s in session.get("contact_submissions", []) if now - s < CONTACT_WINDOW_SECONDS
    ]
    if len(stamps) >= CONTACT_LIMIT:
        session["contact_submissions"] = stamps
        return True
    stamps.append(now)
    session["contact_submissions"] = stamps
    return False


@main_bp.get("/")
def index():
    today = date.today()
    announcements = (
        Announcement.query.filter(
            Announcement.status == "published",
            Announcement.audience == "public",
            or_(Announcement.expires_at.is_(None), Announcement.expires_at >= today),
        )
        .order_by(
            Announcement.is_pinned.desc(),
            Announcement.published_at.desc(),
            Announcement.id.desc(),
        )
        .limit(4)
        .all()
    )
    events = _visible_events(today, today + timedelta(days=90))[:4]
    return render_template(
        "index.html",
        announcements=announcements,
        events=events,
        gallery=gallery_images()[:6],
    )


@main_bp.get("/institucion")
def institucion():
    return render_template("institucion.html", gallery=gallery_images()[:3])


@main_bp.get("/galeria")
def galeria():
    return render_template("galeria.html", gallery=gallery_images())


@main_bp.get("/calendario")
def calendario():
    today = date.today()
    try:
        year = int(request.args.get("anio", today.year))
        month = int(request.args.get("mes", today.month))
    except (TypeError, ValueError):
        year, month = today.year, today.month
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        year, month = today.year, today.month

    start = date(year, month, 1)
    end = date(year, month, pycalendar.monthrange(year, month)[1])
    events = _visible_events(start, end)

    by_date: dict[date, list[Event]] = {}
    for event in events:
        by_date.setdefault(event.start_date, []).append(event)

    weeks = []
    for week in pycalendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        weeks.append(
            [
                {
                    "date": day,
                    "in_month": day.month == month,
                    "is_today": day == today,
                    "events": by_date.get(day, []),
                }
                for day in week
            ]
        )

    previous_month = (start - timedelta(days=1)).replace(day=1)
    next_month = (end + timedelta(days=1)).replace(day=1)
    upcoming = _visible_events(today, today + timedelta(days=120))[:6]

    return render_template(
        "calendario.html",
        weeks=weeks,
        month_name=f"{pycalendar.month_name[month].capitalize()} {year}",
        month=month,
        year=year,
        previous_month=previous_month,
        next_month=next_month,
        month_events=events,
        upcoming=upcoming,
    )


@main_bp.route("/contacto", methods=["GET", "POST"])
def contacto():
    form = {"name": "", "email": "", "phone": "", "subject": "", "body": ""}

    if request.method == "POST":
        form = {
            "name": clean(request.form.get("name"), 120),
            "email": clean(request.form.get("email"), 180).lower(),
            "phone": clean(request.form.get("phone"), 40),
            "subject": clean(request.form.get("subject"), 160),
            "body": clean_multiline(request.form.get("body"), 3000),
        }
        honeypot = clean(request.form.get("website"), 100)

        errors: list[str] = []
        if honeypot:
            errors.append("No fue posible procesar el formulario.")
        if len(form["name"]) < 3:
            errors.append("Ingrese su nombre completo.")
        if form["email"] and not is_valid_email(form["email"]):
            errors.append("El correo electrónico no es válido.")
        if len(form["subject"]) < 4:
            errors.append("Indique un asunto para su mensaje.")
        if len(form["body"]) < 15:
            errors.append("El mensaje debe tener al menos 15 caracteres.")

        if not errors and _contact_rate_limited():
            errors.append(
                "Ha enviado varios mensajes en poco tiempo. "
                "Espere unos minutos antes de volver a intentarlo."
            )

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            message = ContactMessage(
                name=form["name"],
                email=form["email"] or None,
                phone=form["phone"] or None,
                subject=form["subject"],
                body=form["body"],
                ip_address=client_ip(),
            )
            db.session.add(message)
            db.session.commit()

            staff = User.query.filter(
                User.role.in_(("admin", "direction")), User.is_active.is_(True)
            ).all()
            notify_many(
                staff,
                "Nuevo mensaje desde el formulario de contacto",
                f"{form['name']} — {form['subject']}",
                url_for("admin.contact_messages"),
                category="contact",
            )
            db.session.commit()
            current_app.logger.info("Formulario de contacto recibido (id=%s)", message.id)
            flash(
                "Su mensaje fue enviado correctamente. La institución se comunicará "
                "con usted a la brevedad posible.",
                "success",
            )
            return redirect(url_for("main.contacto"))

    return render_template("contacto.html", form=form, now=utcnow())

