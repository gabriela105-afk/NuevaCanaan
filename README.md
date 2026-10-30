# Plataforma web institucional — Colegio Técnico Humanístico Nueva Canaán

Aplicación web institucional desarrollada con **Flask** y **SQLite**, pensada para
publicarse en **Render**. Incluye el sitio público, la autenticación y tres paneles
privados (administración/dirección, docentes y familias).

> **Aviso sobre los datos:** todos los datos institucionales que no fueron
> proporcionados por el colegio (dirección, teléfonos, misión, historia, nombres de
> autoridades, fotografías, etc.) están marcados como **«Por definir»** o como
> **DEMO**. No se inventó información oficial: debe completarse desde el panel de
> administración o en el archivo `.env`.

---

## 1. Funcionalidades

### Sitio público
- Portada con presentación, accesos rápidos, últimos comunicados y próximas actividades.
- Página institucional (historia, misión, visión, autoridades — textos editables).
- Comunicados publicados con detalle, categoría y prioridad.
- Calendario de actividades con vista mensual navegable.
- Galería de imágenes administrable.
- Formulario de contacto con validación, campo trampa antispam y límite por IP.

### Autenticación
- Inicio de sesión por correo y contraseña, con `remember me` opcional.
- Contraseñas almacenadas con *hash* (`pbkdf2:sha256`), nunca en texto plano.
- Bloqueo temporal de la cuenta tras varios intentos fallidos.
- Cambio de contraseña obligatorio en la primera sesión de cuentas creadas por la
  administración.
- Perfil editable, cierre de sesión por `POST` y protección CSRF en todos los formularios.
- Redirecciones internas validadas (sin *open redirect*).

### Panel de administración / dirección
- Tablero con indicadores institucionales.
- Comunicados: borrador/publicado, público/interno, fijado, vencimiento y envío de
  notificaciones a los destinatarios (admin y dirección).
- Calendario: actividades públicas e internas (admin y dirección).
- Galería: carga y eliminación de imágenes (admin y dirección).
- Buzón del formulario de contacto, notificaciones internas, ajustes institucionales
  y registro de auditoría (admin y dirección).
- Usuarios, estudiantes, familias, docentes y cursos con sus vínculos y asignaciones
  (sólo rol **admin**).

### Roles y permisos

| Sección | Admin | Dirección | Docente | Familia |
| --- | --- | --- | --- | --- |
| Usuarios, roles y contraseñas | ✅ | — | — | — |
| Cursos, estudiantes, familias y docentes | ✅ | — | — | — |
| Comunicados, calendario, galería y configuración | ✅ | ✅ | — | — |
| Auditoría y buzón del formulario de contacto | ✅ | ✅ | — | — |
| Avisos, asistencia, notas y tareas de sus cursos | — | — | ✅ | — |
| Sus hijos/as, comunicados, calendario y mensajería | — | — | — | ✅ |

El rol **dirección** es de tipo *staff*: publica y supervisa el contenido
institucional, pero la gestión de cuentas y de datos académicos queda reservada al
rol **admin** (`admin_required`). Los intentos de acceso fuera del rol devuelven
**403** y quedan registrados en la auditoría.

### Panel docente
- Cursos y materias asignadas (aislamiento estricto: sólo los propios).
- Tareas, actividades y evaluaciones con fecha de entrega y puntaje máximo.
- Registro de asistencia por fecha.
- Registro y edición de calificaciones.
- Avisos para sus cursos.

### Panel de familias
- Resumen con los hijos/as vinculados (sólo los propios: acceso a otro estudiante
  devuelve **403**).
- Detalle por estudiante: asistencia, calificaciones y tareas próximas.
- Comunicados y calendario filtrados según el rol.
- Mensajería interna con dirección/administración.
- Notificaciones y perfil.

---

## 2. Requisitos

- Python **3.11 o superior** (probado con 3.12).
- `pip` y entorno virtual (`venv`).
- En Windows no se usa Gunicorn; se ejecuta con `python run.py`.

---

## 3. Instalación local

### Windows (PowerShell)
```powershell
cd nueva-canaan
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# Edite .env y defina SECRET_KEY, ADMIN_EMAIL y ADMIN_PASSWORD

flask --app run.py init-db        # crea tablas + ajustes + administrador
flask --app run.py seed-demo      # opcional: datos ficticios de demostración
python run.py                     # http://127.0.0.1:5000
```

### Linux / macOS
```bash
cd nueva-canaan
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
flask --app run.py init-db
flask --app run.py seed-demo
python run.py
```

> El archivo `.env` se carga automáticamente al iniciar la aplicación
> (`python-dotenv`), sin necesidad de exportar las variables en la terminal.
> Si cambia algún valor de `.env`, reinicie el servidor. En Render las variables
> se definen en el panel *Environment* del servicio.

### Comandos disponibles
| Comando | Descripción |
| --- | --- |
| `flask --app run.py init-db` | Crea las tablas y los ajustes institucionales mínimos. |
| `flask --app run.py init-and-seed` | Igual que `init-db` (lo usa Render al arrancar). |
| `flask --app run.py seed-demo` | Carga datos **ficticios** marcados con `(DEMO)`. |
| `flask --app run.py seed-demo --force` | Vuelve a crear los datos demo si faltan. |
| `flask --app run.py create-admin --email X --password Y --name Z` | Crea otra cuenta administradora. |

### Cuentas de demostración
Contraseña común: **`Demo12345`** (sólo tras ejecutar `seed-demo`).

| Rol | Correo |
| --- | --- |
| Administración | `admin@nuevacanaan.edu` (definido en `.env`) |
| Dirección | `direccion@nuevacanaan.edu` |
| Docente | `docente1@nuevacanaan.edu` / `docente2@nuevacanaan.edu` |
| Familia | `padre1@nuevacanaan.edu` / `padre2@nuevacanaan.edu` |

La cuenta administradora creada por `.env` solicita cambiar la contraseña en el
primer inicio de sesión. **No use estas cuentas en producción sin cambiar la clave.**

---

## 4. Estructura del proyecto

```
nueva-canaan/
├── app/
│   ├── __init__.py          # fábrica de la aplicación, filtros y contexto global
│   ├── extensions.py        # SQLAlchemy, LoginManager, CSRF, Migrate
│   ├── models.py            # usuarios, cursos, estudiantes, notas, mensajes, etc.
│   ├── utils.py             # permisos, validaciones, ajustes, auditoría, notificaciones
│   ├── cli.py               # comandos init-db / seed-demo / create-admin
│   ├── main/                # sitio público (portada, institución, calendario, contacto)
│   ├── auth/                # login, logout, perfil, cambio de contraseña
│   ├── announcements/       # comunicados públicos
│   ├── admin/               # panel de administración y dirección
│   ├── teachers/            # panel docente
│   ├── parents/             # panel de familias
│   ├── messages/            # mensajería interna y notificaciones
│   ├── templates/           # plantillas Jinja2 (públicas, paneles, errores)
│   └── static/              # css/styles.css, js/app.js, img/
├── instance/                # base SQLite local (no se versiona)
├── tests/                   # pruebas automatizadas con pytest
├── config.py                # configuración por entorno
├── run.py                   # servidor de desarrollo
├── wsgi.py                  # punto de entrada para Gunicorn
├── requirements.txt
├── render.yaml              # Blueprint de Render
└── .env.example
```

---

## 5. Seguridad implementada

- Contraseñas con *hash* Werkzeug `pbkdf2:sha256`; nunca se guardan ni registran en claro.
- CSRF activo en todos los formularios (`Flask-WTF`), también en los `POST` de
  eliminación y cierre de sesión.
- Control de acceso por rol (`admin_required`, `staff_required`, `teacher_required`,
  `parent_required`) y verificación de pertenencia: un docente sólo accede a sus cursos
  y una familia sólo a los estudiantes vinculados a su cuenta.
- Bloqueo temporal de la cuenta tras `LOGIN_MAX_ATTEMPTS` intentos fallidos.
- Cookies `HttpOnly`, `SameSite=Lax` y `Secure` en producción (`SESSION_COOKIE_SECURE`).
- Validación y limpieza de entradas; límite de tamaño de subida (`MAX_UPLOAD_MB`).
- Nombres de archivo saneados con `secure_filename` y verificación de extensión.
- Registro de auditoría de acciones administrativas (sin datos sensibles).
- Mensajes de error genéricos en el login para no revelar si un correo existe.
- Cabeceras `X-Content-Type-Options`, `X-Frame-Options` y `Referrer-Policy`.

Si el sitio se sirve por HTTPS, mantenga `SESSION_COOKIE_SECURE=true` (valor por
defecto en `render.yaml`). En local con `http://127.0.0.1` debe permanecer en `false`.

---

## 6. Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest        # Windows
python -m pytest                            # Linux / macOS
```

Cubren el sitio público y el formulario de contacto, la autenticación (bloqueo,
CSRF, cambio de contraseña), la autorización por rol y el aislamiento de datos, los
flujos de comunicados, calendario, tareas, asistencia, notas y mensajería, y una
prueba de humo que recorre todas las rutas `GET` con cada rol y verifica que los
enlaces internos de cada panel sean accesibles (sin 403/404) para ese rol.

Las pruebas usan una base SQLite temporal: **no** modifican `instance/nueva_canaan.db`.

---

## 7. Despliegue en Render

### 7.1 Con Blueprint (`render.yaml` incluido)

1. Suba el proyecto a un repositorio de GitHub/GitLab.
2. En Render: **New → Blueprint**, seleccione el repositorio y confirme.
3. Render crea el *Web Service* `nueva-canaan` con:
   - `buildCommand`: `pip install -r requirements.txt`
   - `startCommand`: `python -m app.cli init-and-seed && gunicorn wsgi:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT`
   - Disco persistente de 1 GB montado en `/var/data`
   - `DATABASE_URL=sqlite:////var/data/nueva_canaan.db`
   - `UPLOAD_FOLDER=/var/data/uploads`
   - `SECRET_KEY` generada automáticamente
4. Complete manualmente `ADMIN_EMAIL`, `ADMIN_PASSWORD` y `ADMIN_NAME` (marcados con
   `sync: false`); si no los define, no se creará ninguna cuenta administradora.
5. Espere el despliegue y abra la URL `https://nueva-canaan.onrender.com`.
6. Inicie sesión con la cuenta administradora y **cambie la contraseña**.

### 7.2 Manual (sin Blueprint)

1. **New → Web Service**, runtime Python 3, build `pip install -r requirements.txt`.
2. Start command:
   ```bash
   python -m app.cli init-and-seed && gunicorn wsgi:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
   ```
3. Variables de entorno mínimas: `FLASK_ENV=production`, `SECRET_KEY`,
   `SESSION_COOKIE_SECURE=true`, `DATABASE_URL`, `UPLOAD_FOLDER`, `ADMIN_EMAIL`,
   `ADMIN_PASSWORD`, `ADMIN_NAME`.
4. Añada un disco persistente y móntelo en `/var/data` **antes** del primer arranque
   si quiere conservar los datos.

### 7.3 Persistencia de SQLite (lea esto antes de publicar)

- El sistema de archivos de un *Web Service* de Render es **efímero**: sin disco
  persistente, la base SQLite y las imágenes subidas se pierden en cada despliegue,
  reinicio o *spin down*.
- El disco persistente de Render **requiere un plan de pago** (el plan gratuito no lo
  incluye). Verifique el plan contratado; `render.yaml` declara `plan: starter`.
- Use **un solo worker**: SQLite no admite escrituras concurrentes de varios procesos.
  El comando de arranque ya fija `--workers 1 --threads 4`.
- `python -m app.cli init-and-seed` es idempotente: crea tablas y ajustes que falten y no
  duplica usuarios existentes.
- Para un volumen de datos importante o varias instancias, migre a PostgreSQL: defina
  `DATABASE_URL=postgresql://...` e instale el controlador correspondiente
  (`pip install "psycopg[binary]"` y añádalo a `requirements.txt`).

### 7.4 Copias de seguridad

Con disco persistente, descargue periódicamente `/var/data/nueva_canaan.db` (y la
carpeta `uploads/`). Localmente basta con copiar `instance/nueva_canaan.db`.
También puede recrear el esquema y los datos mínimos con `flask --app run.py init-db`.

---

## 8. Datos institucionales pendientes de completar

Estos valores se dejaron como **«Por definir»** o **DEMO** de forma intencional, para
no inventar información oficial. Se editan desde **Administración → Ajustes**
(o en `.env` para los tres primeros):

| Dato | Dónde se edita |
| --- | --- |
| Logotipo oficial | `INSTITUTION_LOGO` en `.env` o `app/static/img/logo.svg` |
| Imagen de portada | `INSTITUTION_COVER` en `.env` o `app/static/img/portada.svg` |
| Favicon | `INSTITUTION_FAVICON` en `.env` |
| Dirección, teléfonos, correo, horarios | Administración → Ajustes |
| Misión, visión, historia, valores | Administración → Ajustes |
| Nombres de autoridades | Administración → Ajustes |
| Redes sociales y ubicación | Administración → Ajustes |
| Fotografías de la galería | Administración → Galería |

Los archivos `logo.svg` y `portada.svg` incluidos son **marcadores de posición**
generados para que el sitio funcione; reemplácelos por los oficiales cuando estén
disponibles (mismos nombres y rutas o ajuste las variables de entorno).

---

## 9. Limitaciones conocidas

- **No se envían correos, SMS ni mensajes de WhatsApp.** Las notificaciones son
  internas (aparecen en el panel de cada usuario). Para correo haría falta configurar
  un servidor SMTP y una tarea en segundo plano.
- No hay integración con sistemas externos de gestión académica ni pagos.
- La mensajería es interna entre usuarios de la plataforma; no hay adjuntos en mensajes
  (sólo imágenes en la galería y en los comunicados).
- La autenticación de dos factores no está implementada.
- SQLite está pensado para una única instancia con pocas decenas de usuarios
  concurrentes.

