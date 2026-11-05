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
- **NUEVA CANAÁN NOTICIAS**: muro público de publicaciones con fotografía, categorías,
  búsqueda, reacciones «me gusta» y comentarios del público.
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
- Noticias del muro: publicaciones con fotografía, fijado, borrador/publicado,
  archivo y moderación de los comentarios del público (admin y dirección).
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
| Noticias del muro (publicaciones y moderación) | ✅ | ✅ | — | — |
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
- **Base de datos:** SQLite viene incluido con Python y es el valor por defecto en
  local. En producción se usa PostgreSQL de **Supabase** (el controlador
  `psycopg[binary]` ya está en `requirements.txt`; no requiere compilador).

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
| `python tools/migrate_sqlite_to_postgres.py --dry-run` | Muestra qué datos se copiarían a PostgreSQL (ver sección 7.2). |
| `python tools/migrate_sqlite_to_postgres.py --target "postgresql://..."` | Copia los datos de SQLite a Supabase. |

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
│   ├── news/                # muro público NUEVA CANAÁN NOTICIAS (fotos, likes, comentarios)
│   ├── news_admin/          # panel de noticias: publicaciones y moderación
│   ├── admin/               # panel de administración y dirección
│   ├── teachers/            # panel docente
│   ├── parents/             # panel de familias
│   ├── messages/            # mensajería interna y notificaciones
│   ├── templates/           # plantillas Jinja2 (públicas, paneles, errores)
│   └── static/              # css/styles.css, css/news.css, js/app.js, js/news.js, img/
├── instance/                # base SQLite local (no se versiona)
├── tests/                   # pruebas automatizadas con pytest
├── tools/
│   └── migrate_sqlite_to_postgres.py   # copia los datos de SQLite a Supabase
├── config.py                # configuración por entorno (SQLite o PostgreSQL)
├── run.py                   # servidor de desarrollo
├── wsgi.py                  # punto de entrada para Gunicorn
├── requirements.txt
├── render.yaml              # Blueprint de Render
├── Procfile                 # comando de arranque (Render/Railway/Heroku)
├── supabase_schema.sql      # DDL de PostgreSQL (generado, opcional)
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
- Comentarios del muro de noticias con campo trampa antispam, límite por sesión/IP y
  moderación desde el panel; las fotografías se entregan por una ruta controlada
  (`/noticias/foto/<id>`) que no expone el disco y oculta las de borradores.
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
flujos de comunicados, calendario, tareas, asistencia, notas y mensajería, el muro
de noticias (filtros, fotografías, «me gusta», comentarios, antispam y moderación) y
una prueba de humo que recorre todas las rutas `GET` con cada rol y verifica que los
enlaces internos de cada panel sean accesibles (sin 403/404) para ese rol.

Las pruebas usan una base SQLite temporal: **no** modifican `instance/nueva_canaan.db`.

---

## 7. Despliegue en producción (Render + Supabase)

Arquitectura:

```
Navegador  →  Render (Gunicorn + Flask)  →  Supabase (PostgreSQL)
```

- **Render** ejecuta la aplicación y sirve el sitio. Su disco es **efímero**.
- **Supabase** aloja la base de datos PostgreSQL, así los datos sobreviven a cada
  despliegue, reinicio o suspensión del plan gratuito de Render.
- En local se sigue usando **SQLite** sin tocar nada (`instance/nueva_canaan.db`):
  `config.py` elige el motor según `DATABASE_URL`.

### 7.1 Crear el proyecto en Supabase y obtener la cadena de conexión

1. Cree una cuenta en <https://supabase.com> y un **New project**. Guarde la
   contraseña de la base de datos que le pida el asistente.
2. Espere a que termine el aprovisionamiento (2–3 minutos).
3. Vaya a **Project Settings → Database → Connection string** y copie la variante
   **Session pooler** (puerto `5432`, host `aws-0-<region>.pooler.supabase.com`):

   ```
   postgresql://postgres.abcdefghijklm:TU_CLAVE@aws-0-us-east-1.pooler.supabase.com:5432/postgres
   ```

   - Use el **pooler**, no la conexión directa (`db.<ref>.supabase.co`): la directa
     sólo publica IPv6 y Render no siempre puede alcanzarla.
   - El **Transaction pooler** (puerto `6543`) también sirve; `config.py` desactiva
     las sentencias preparadas que ese modo no admite.
   - Deje el esquema `postgresql://` tal cual: el código lo convierte en
     `postgresql+psycopg://` y añade `sslmode=require` automáticamente.

### 7.2 Migrar los datos locales a Supabase (una sola vez)

Con el entorno virtual activo, desde la raíz del proyecto:

```powershell
# 1) Ver qué se copiaría (no escribe nada ni se conecta a Supabase)
python tools\migrate_sqlite_to_postgres.py --dry-run

# 2) Copiar: crea las tablas, copia los registros y ajusta los contadores
python tools\migrate_sqlite_to_postgres.py --target "postgresql://postgres.xxxx:CLAVE@aws-0-us-east-1.pooler.supabase.com:5432/postgres"

# 3) Comprobar que todas las tablas tienen el mismo número de filas
python tools\migrate_sqlite_to_postgres.py --target "postgresql://..." --verify-only
```

- Se copian usuarios (con el *hash* de la contraseña, así que **nadie tiene que
  cambiarla**), estudiantes, cursos, comunicados, eventos, notas, asistencia,
  mensajes, notificaciones y ajustes institucionales.
- Si el destino ya tuviera datos, el script se detiene; use `--truncate` para
  reemplazarlos (vacía las tablas del destino antes de copiar).
- Si algún texto excede el largo definido en el modelo, se lista y el script se
  detiene antes de copiar; `--allow-truncate-strings` lo recorta.
- `--print-sql` genera `supabase_schema.sql` con el DDL equivalente, por si prefiere
  crear las tablas pegándolo en **Supabase → SQL Editor**.
- Si su base de Supabase ya existía antes de agregar el **muro de noticias**, cree sólo
  las tablas nuevas (`news_posts`, `news_images`, `news_comments`, `news_reactions`)
  sin copiar datos: `python tools/migrate_sqlite_to_postgres.py --target "postgresql://..."
  --schema-only`. `create_all` no toca las tablas que ya existen. Si el comando avisa
  que faltan tablas en el origen, ejecute antes `flask --app run.py init-db`.

> Después de migrar **no ejecute `seed-demo`** ni vuelva a correr la migración con
> `--truncate` sobre Supabase: los datos reales ya están ahí.

### 7.3 Desplegar en Render con el Blueprint (recomendado)

1. Suba el proyecto a un repositorio de GitHub/GitLab.
2. En Render: **New → Blueprint**, seleccione el repositorio y confirme.
3. Render crea el *Web Service* `nueva-canaan` (plan gratuito) con:
   - `buildCommand`: `pip install --upgrade pip && pip install -r requirements.txt`
   - `startCommand`: `python -m app.cli init-and-seed && gunicorn wsgi:app --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT`
   - `healthCheckPath`: `/`
   - `PYTHON_VERSION=3.12.6`, `FLASK_ENV=production`, `SESSION_COOKIE_SECURE=true`
   - `SECRET_KEY` generada automáticamente por Render
4. Cuando Render pida las variables marcadas con `sync: false`:
   - `DATABASE_URL`: la cadena de Supabase del paso 7.1 (**obligatoria**).
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME`: déjelas vacías si ya migró los
     datos; sólo hacen falta si arranca con la base vacía (crean la primera cuenta).
5. Espere el despliegue y abra la URL `https://nueva-canaan.onrender.com`.
6. Inicie sesión con sus credenciales de siempre: son las de la base migrada.

### 7.4 Alternativa manual (sin Blueprint)

1. **New → Web Service**, runtime Python 3, build
   `pip install --upgrade pip && pip install -r requirements.txt`.
2. Start command:
   ```bash
   python -m app.cli init-and-seed && gunicorn wsgi:app --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
   ```
3. Variables de entorno mínimas: `FLASK_ENV=production`, `SECRET_KEY`,
   `SESSION_COOKIE_SECURE=true`, `DATABASE_URL` y, si la base está vacía,
   `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_NAME`.
4. No hace falta disco persistente: la base de datos está en Supabase.

> `Procfile` incluye el mismo comando de arranque para plataformas que lo usen
> (Railway, Heroku). En Render tiene prioridad el *Start Command* del panel o el
> `startCommand` de `render.yaml`.

### 7.5 Archivos subidos (galería y adjuntos)

La base de datos ya no depende del disco de Render, pero **los archivos sí**: el
sistema de archivos de un *Web Service* es efímero y las imágenes subidas se
pierden en cada despliegue. Opciones:

1. **Plan de pago + disco persistente**: descomente el bloque `disk` al final de
   `render.yaml` y defina `UPLOAD_FOLDER=/var/data/uploads`.
2. **Supabase Storage** (recomendado a futuro): requiere adaptar las funciones de
   `app/utils.py` que guardan y leen archivos.

Mientras no se resuelva, suba las imágenes justo después de desplegar o guarde una
copia local de `instance/uploads` como respaldo.

### 7.6 Copias de seguridad

- Supabase (plan gratuito) guarda respaldos diarios durante 7 días: **Database →
  Backups**.
- Respaldo manual: `pg_dump "postgresql://postgres.xxxx:CLAVE@aws-0-...:5432/postgres" > respaldo.sql`
- Localmente: copie `instance/nueva_canaan.db` y `instance/uploads/`.
- Para volver a cargar un respaldo en Supabase: **SQL Editor** (consulta el archivo)
  o `psql "postgresql://..." -f respaldo.sql`.

### 7.7 Verificación después del despliegue

1. Portada, institución, calendario y formulario de contacto cargan.
2. Inicio de sesión con cada rol (administración, dirección, docente, familia, estudiante).
3. Crear un comunicado y comprobar que aparece en el panel y en la portada.
4. Registrar asistencia o una nota, cerrar sesión y volver a entrar: si persiste,
   se está leyendo de Supabase.
5. Crear un usuario nuevo y subir una imagen: confirma que los `INSERT` funcionan y
   que los identificadores no chocan (secuencias ya ajustadas por el script).

### 7.8 Problemas frecuentes

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `ModuleNotFoundError: psycopg` | build sin el controlador | revise `requirements.txt` y redespliegue |
| timeout o `could not translate host name` | conexión directa (IPv6) o host mal copiado | use la cadena del *Session pooler* |
| `prepared statement "s0" already exists` | Transaction pooler sin desactivar sentencias preparadas | no edite `config.py`: ya lo hace en el puerto 6543 |
| `SSL connection is required` | falta `sslmode` en la URL | mantenga `DATABASE_SSLMODE=require` |
| `duplicate key value violates unique constraint` | secuencias sin ajustar | vuelva a ejecutar el script con `--truncate` |
| El sitio da error 500 y los datos «desaparecen» | `DATABASE_URL` vacía → Render usa SQLite efímero | defina la variable en Render |

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
- La base SQLite local está pensada para una única instancia con pocas decenas de
  usuarios concurrentes; en producción se usa PostgreSQL (Supabase), que sí admite
  varios procesos. El *pool* de conexiones está limitado en `config.py`
  (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`) para no agotar el límite del plan gratuito.
- Los archivos subidos (galería, adjuntos de comunicados y fotografías del muro de
  noticias) viven en el disco de Render y se pierden al redesplegar; requieren disco
  persistente o Supabase Storage (ver sección 7.5).

