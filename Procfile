# Procfile: comando de arranque estándar (Render, Railway, Heroku…).
# En Render se usa el `startCommand` de render.yaml, que ejecuta
# `python -m app.cli init-and-seed` antes de este comando.
web: gunicorn wsgi:app --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
