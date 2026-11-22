"""Notificaciones internas y mensajería entre usuarios de la plataforma."""

from __future__ import annotations

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

from ..extensions import db
from ..models import Message, Notification, User, utcnow
from ..utils import clean, clean_multiline, notify, record_audit

messages_bp = Blueprint("messages", __name__)


# ---------------------------------------------------------------------------
# Notificaciones
# ---------------------------------------------------------------------------
@messages_bp.get("/notificaciones")
@login_required
def notifications():
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config["ITEMS_PER_PAGE"] * 2
    pagination = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    return render_template(
        "notifications.html",
        pagination=pagination,
        notifications=pagination.items,
    )


@messages_bp.post("/notificaciones/<int:notification_id>/leer")
@login_required
def read_notification(notification_id: int):
    notification = db.session.get(Notification, notification_id)
    if notification is None or notification.user_id != current_user.id:
        abort(404)
    if notification.read_at is None:
        notification.read_at = utcnow()
        db.session.commit()
    if notification.link:
        return redirect(notification.link)
    return redirect(url_for("messages.notifications"))


@messages_bp.post("/notificaciones/leer-todas")
@login_required
def read_all_notifications():
    updated = Notification.query.filter_by(
        user_id=current_user.id, read_at=None
    ).update({"read_at": utcnow()}, synchronize_session=False)
    db.session.commit()
    flash(
        f"Se marcaron {updated} notificaciones como leídas."
        if updated
        else "No tenía notificaciones pendientes.",
        "info",
    )
    return redirect(url_for("messages.notifications"))


# ---------------------------------------------------------------------------
# Mensajería interna
# ---------------------------------------------------------------------------
def _allowed_recipients() -> list[User]:
    """Destinatarios permitidos según el rol (las familias escriben a dirección)."""
    if current_user.is_staff:
        query = User.query.filter(User.is_active.is_(True), User.id != current_user.id)
    else:
        query = User.query.filter(
            User.is_active.is_(True),
            User.role.in_(("admin", "direction")),
            User.id != current_user.id,
        )
    return query.order_by(User.role, User.full_name).all()


def _accessible_message(message_id: int) -> Message:
    message = db.session.get(Message, message_id)
    if message is None:
        abort(404)
    if (
        current_user.id not in (message.sender_id, message.recipient_id)
        and not current_user.is_staff
    ):
        abort(403)
    return message


@messages_bp.get("/mensajes")
@login_required
def inbox():
    view = request.args.get("vista", "recibidos")
    page = request.args.get("page", 1, type=int)
    per_page = current_app.config["ITEMS_PER_PAGE"]

    query = Message.query
    if view == "enviados":
        query = query.filter(Message.sender_id == current_user.id)
    else:
        view = "recibidos"
        query = query.filter(Message.recipient_id == current_user.id)

    pagination = query.order_by(Message.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template(
        "messages/inbox.html",
        pagination=pagination,
        messages=pagination.items,
        view=view,
    )


@messages_bp.route("/mensajes/nuevo", methods=["GET", "POST"])
@login_required
def compose():
    recipients = _allowed_recipients()
    form = {"recipient_id": 0, "subject": "", "body": ""}

    if request.method == "POST":
        try:
            recipient_id = int(request.form.get("recipient_id", "0"))
        except (TypeError, ValueError):
            recipient_id = 0
        subject = clean(request.form.get("subject"), 160)
        body = clean_multiline(request.form.get("body"), 4000)
        form = {"recipient_id": recipient_id, "subject": subject, "body": body}

        allowed_ids = {user.id for user in recipients}
        errors: list[str] = []
        if recipient_id not in allowed_ids:
            errors.append("Seleccione un destinatario válido.")
        if len(subject) < 4:
            errors.append("Escriba un asunto de al menos 4 caracteres.")
        if len(body) < 10:
            errors.append("El mensaje debe tener al menos 10 caracteres.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            recipient = db.session.get(User, recipient_id)
            message = Message(
                sender_id=current_user.id,
                recipient_id=recipient.id,
                subject=subject,
                body=body,
            )
            db.session.add(message)
            db.session.flush()
            notify(
                recipient,
                f"Nuevo mensaje de {current_user.full_name}",
                subject,
                url_for("messages.detail", message_id=message.id),
                category="message",
            )
            record_audit(
                "message_send", "message", message.id, f"Para usuario {recipient.id}"
            )
            db.session.commit()
            flash("Mensaje enviado correctamente.", "success")
            return redirect(url_for("messages.detail", message_id=message.id))

    return render_template("messages/compose.html", recipients=recipients, form=form)


@messages_bp.get("/mensajes/<int:message_id>")
@login_required
def detail(message_id: int):
    message = _accessible_message(message_id)
    if message.recipient_id == current_user.id and message.read_at is None:
        message.read_at = utcnow()
        db.session.commit()

    root_id = message.parent_id or message.id
    thread = (
        Message.query.filter((Message.id == root_id) | (Message.parent_id == root_id))
        .order_by(Message.created_at)
        .all()
    )
    return render_template("messages/detail.html", message=message, thread=thread)


@messages_bp.post("/mensajes/<int:message_id>/responder")
@login_required
def reply(message_id: int):
    original = _accessible_message(message_id)
    body = clean_multiline(request.form.get("body"), 4000)

    if len(body) < 5:
        flash("Escriba una respuesta de al menos 5 caracteres.", "error")
        return redirect(url_for("messages.detail", message_id=original.id))

    other_id = (
        original.recipient_id
        if original.sender_id == current_user.id
        else original.sender_id
    )
    subject = original.subject
    if not subject.startswith("Re:"):
        subject = f"Re: {subject}"
    answer = Message(
        sender_id=current_user.id,
        recipient_id=other_id,
        subject=subject[:160],
        body=body,
        parent_id=original.parent_id or original.id,
    )
    db.session.add(answer)
    db.session.flush()
    notify(
        db.session.get(User, other_id),
        f"Respuesta de {current_user.full_name}",
        subject,
        url_for("messages.detail", message_id=answer.id),
        category="message",
    )
    db.session.commit()
    flash("Respuesta enviada.", "success")
    return redirect(url_for("messages.detail", message_id=answer.id))

