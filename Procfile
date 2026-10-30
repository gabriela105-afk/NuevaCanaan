# Procfile: comando de arranque estándar (Render, Railway, Heroku…).
# En Render tiene prioridad el "Start Command" del panel o `startCommand` de
# render.yaml, que es exactamente este mismo comando.
web: gunicorn wsgi:app --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
