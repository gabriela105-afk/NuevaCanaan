"""Prueba de humo: recorre todas las rutas GET registradas con cada rol.

Sirve para detectar plantillas rotas, ``url_for`` inexistentes y errores 500
en vistas que no se cubren con las pruebas funcionales.
"""

from __future__ import annotations

import pytest

from app import create_app  # noqa: F401  (asegura el paquete importable)

ALLOWED_STATUS = {200, 302, 400, 403, 404}
ROLE_CREDENTIALS = {
    "admin": "admin@test.local",
    "direction": "direccion@test.local",
    "teacher": "docente@test.local",
    "parent": "tutor@test.local",
}


def _get_rules(app):
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods or rule.endpoint == "static":
            continue
        if rule.arguments:
            continue
        yield rule.rule


def _login(client, email):
    return client.post(
        "/login", data={"email": email, "password": "ClaveSegura123"}
    )


@pytest.mark.parametrize("role", sorted(ROLE_CREDENTIALS))
def test_all_get_routes_render_without_server_error(app, client, role):
    _login(client, ROLE_CREDENTIALS[role])

    failures = []
    for path in _get_rules(app):
        response = client.get(path)
        if response.status_code not in ALLOWED_STATUS:
            failures.append(f"{role} GET {path} -> {response.status_code}")

    assert not failures, "\n".join(failures)


def test_anonymous_get_routes_render_without_server_error(app, client):
    failures = []
    for path in _get_rules(app):
        response = client.get(path)
        if response.status_code not in ALLOWED_STATUS:
            failures.append(f"anónimo GET {path} -> {response.status_code}")
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("role", sorted(ROLE_CREDENTIALS))
def test_no_broken_internal_links_on_dashboard(app, client, role):
    """Cada enlace interno del panel debe ser accesible para ese rol."""
    import re

    _login(client, ROLE_CREDENTIALS[role])
    landing = {
        "admin": "/admin/",
        "direction": "/admin/",
        "teacher": "/docentes/",
        "parent": "/portal/",
    }[role]
    body = client.get(landing).get_data(as_text=True)

    broken = []
    for href in set(re.findall(r'href="(/[^"#?]*)"', body)):
        response = client.get(href)
        if response.status_code in (403, 404) or response.status_code >= 500:
            broken.append(f"{href} ({response.status_code})")

    assert not broken, f"Enlaces inaccesibles para {role} en {landing}: {broken}"
