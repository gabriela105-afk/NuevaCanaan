"""Punto de entrada WSGI usado por Gunicorn en Render."""

from app import create_app

app = create_app()
