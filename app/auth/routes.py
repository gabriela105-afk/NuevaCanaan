"""Autenticación: inicio/cierre de sesión, perfil y cambio de contraseña."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User
from ..utils import (
    clean,
    client_ip,
    dashboard_url,
    is_valid_email,
    record_audit,
    validate_password,
)

auth_bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str | None:
    """Sólo permite redirecciones internas (evita open redirect)."""
    if not target:
        return None
    target = target.strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(dashboard_url(current_user))

    next_url = _safe_next(request.args.get("next") or request.form.get("next"))
    email = ""

    if request.method == "POST":
        email = clean(request.form.get("email"), 180).lower()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        errors: list[str] = []
        if not email or not is_valid_email(email):
            errors.append("Ingrese un correo electrónico válido.")
        if not password:
            errors.append("Ingrese su contraseña.")

        user = User.query.filter_by(email=email).first() if email else None

        if user is not None and user.is_locked:
            current_app.logger.warning("Intento en cuenta bloqueada: %s", user.id)
            flash(
                "La cuenta está bloqueada temporalmente por demasiados intentos "
                "fallidos. Intente más tarde o comuníquese con la institución.",
                "error",
            )
            return render_template("auth/login.html", email=email, next_url=next_url), 429

        if not errors:
            if user is None or not user.check_password(password):
                if user is not None:
                    user.register_failed_login(
                        current_app.config["LOGIN_MAX_ATTEMPTS"],
                        current_app.config["LOGIN_LOCK_MINUTES"],
                    )
                    record_audit("login_failed", "user", user.id, "Contraseña incorrecta")
                    db.session.commit()
                errors.append("Correo electrónico o contraseña incorrectos.")
            elif not user.is_active:
                errors.append(
                    "Su cuenta está desactivada. Comuníquese con la administración "
                    "de la institución."
                )

        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("auth/login.html", email=email, next_url=next_url)

        user.register_successful_login(client_ip())
        record_audit("login", "user", user.id, "Inicio de sesión correcto")
        db.session.commit()
        login_user(user, remember=remember)

        flash(f"Bienvenido(a), {user.full_name}.", "success")
        if user.must_change_password:
            flash(
                "Por seguridad debe actualizar su contraseña antes de continuar.",
                "warning",
            )
            return redirect(url_for("auth.change_password"))
        return redirect(next_url or dashboard_url(user))

    return render_template("auth/login.html", email=email, next_url=next_url)


@auth_bp.post("/logout")
@login_required
def logout():
    user_label = current_user.full_name
    record_audit("logout", "user", current_user.id, "Cierre de sesión")
    db.session.commit()
    logout_user()
    flash(f"Sesión finalizada. Hasta pronto, {user_label}.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        full_name = clean(request.form.get("full_name"), 160)
        phone = clean(request.form.get("phone"), 40)
        errors = []
        if len(full_name) < 5:
            errors.append("Ingrese su nombre completo (mínimo 5 caracteres).")
        if not errors:
            current_user.full_name = full_name
            current_user.phone = phone or None
            record_audit("profile_update", "user", current_user.id, "Actualizó sus datos")
            db.session.commit()
            flash("Sus datos personales se actualizaron correctamente.", "success")
            return redirect(url_for("auth.profile"))
        for message in errors:
            flash(message, "error")
    return render_template("auth/profile.html")


@auth_bp.route("/cambiar-contrasena", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirmation = request.form.get("confirm_password") or ""

        errors = validate_password(new_password, confirmation)
        if not current_user.check_password(current_password):
            errors.insert(0, "La contraseña actual no es correcta.")
        if new_password and current_user.check_password(new_password):
            errors.append("La nueva contraseña debe ser distinta de la actual.")

        if errors:
            for message in errors:
                flash(message, "error")
        else:
            current_user.set_password(new_password)
            current_user.must_change_password = False
            current_user.failed_login_attempts = 0
            current_user.locked_until = None
            record_audit("password_change", "user", current_user.id, "Cambió su contraseña")
            db.session.commit()
            flash("Contraseña actualizada correctamente.", "success")
            return redirect(dashboard_url(current_user))

    return render_template("auth/change_password.html")

