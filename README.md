# Portal institucional Nueva Canaán

Aplicación web del **Colegio Técnico Humanístico Nueva Canaán**. Integra el sitio
público (muro de noticias, comunicados, galería, calendario y contacto) con
paneles privados para administración, dirección, docentes y familias.

## Qué hace

- Sitio público con noticias, comunicados, galería institucional, calendario y
  formulario de contacto; no expone datos personales de estudiantes.
- Paneles con acceso por rol: administración, dirección, docentes y familias.
- Gestión de usuarios, estudiantes, cursos, familias, docentes, comunicados,
  eventos, galería y mensajes de contacto.
- Panel académico: escala institucional, años escolares, trimestres, materias,
  asignación de materias a cursos, calificaciones y observaciones pedagógicas.
- Cada alta, cambio o eliminación de calificación queda en un historial de
  auditoría; los trimestres pueden cerrarse para bloquear notas.
- Portal de familias con acceso **sólo a sus estudiantes**: asistencia, notas,
  observaciones publicadas, tareas y comunicados.
- Panel docente para gestionar tareas, asistencia, notas y comunicados de sus
  cursos.
- Las fotografías nuevas se guardan en Supabase Storage (o en disco local durante
  el desarrollo) para que sobrevivan a los redespliegues de Render.

## Tecnologías

| Componente | Uso |
| --- | --- |
| Python 3.12.6 + Flask | Aplicación web |
| Flask-SQLAlchemy / SQLAlchemy 2.0 | Acceso a datos |
| SQLite | Base de datos local por defecto (`instance/nueva_canaan.db`) |
| PostgreSQL / Supabase | Opcional mediante `DATABASE_URL` en producción |
| Flask-Login | Sesión y control de acceso por rol |
| Flask-WTF / CSRFProtect | Protección de formularios |
| Jinja2 | Plantillas HTML |
| Supabase Storage / disco local | Fotografías y adjuntos |
| Gunicorn | Servidor en Render |

No se usa Pillow: las imágenes se validan por extensión, tamaño y firma binaria.
La escala de calificación tampoco está fijada en el código; la define la
institución desde el panel académico.

## Estructura

```text
app/
  __init__.py        fábrica de Flask, filtros, errores y cabeceras
  academic/          panel académico (notas, materias, trimestres, auditoría)
  admin/             administración de usuarios, cursos, familias y contenido
  announcements/     comunicados públicos
  auth/              login, perfil y cambio de contraseña
  main/              sitio público, contacto y calendario
  messages/          mensajes y notificaciones entre usuarios
  news/              muro público de noticias
  news_admin/        administración del muro y comentarios
  parents/           portal de familias
  teachers/          panel docente
  cli.py             init-db, init-and-seed y create-admin
  extensions.py      SQLAlchemy, Flask-Login, CSRF y Migrate
  models.py          usuarios, cursos, estudiantes, notas, noticias, etc.
  schema.py          creación de tablas y columnas nuevas al arrancar
  storage.py         Supabase Storage y almacenamiento local
  utils.py           permisos, validaciones, auditoría y formato
  templates/         sitio público y paneles por rol
  static/            CSS, JS, logo e imágenes del sitio
config.py            configuración y conexión a la base de datos
instance/            base SQLite y fotografías locales (no se versiona)
tests/               pruebas automatizadas con pytest
tools/               check_supabase.py (diagnóstico de sólo lectura)
run.py / wsgi.py     entradas local y de Gunicorn
Procfile             comando web
render.yaml          configuración del servicio en Render
requirements.txt     dependencias del proyecto
```

## Puesta en marcha local

Desde la carpeta del proyecto:

```powershell
# 1. Activar el entorno virtual existente
.\.venv\Scripts\Activate.ps1

# 2. Crear/verificar las tablas y la cuenta administradora
python -m app.cli init-and-seed

# 3. Iniciar el servidor local
python run.py
```

Abrir `http://127.0.0.1:5000`. El correo y la contraseña iniciales se toman de
`ADMIN_EMAIL` y `ADMIN_PASSWORD` en `.env` (o de las variables de entorno de
Render). La contraseña se guarda como hash PBKDF2 en la tabla `users`; nunca en
texto plano.

También se puede iniciar con:

```powershell
flask --app run.py run
```

## Rutas principales

| Ruta | Acceso | Función |
| --- | --- | --- |
| `/` | Público | Portada y muro de publicaciones |
| `/noticias`, `/noticias/<id>` | Público | Muro y detalle de noticias |
| `/comunicados` | Público / familias | Comunicados institucionales |
| `/galeria`, `/calendario`, `/contacto` | Público | Galería, calendario y contacto |
| `/login`, `/perfil` | Público / autenticado | Acceso y datos de la cuenta |
| `/admin/` | Administración | Panel general |
| `/admin/usuarios`, `/admin/estudiantes`, `/admin/familias` | Administración | Gestión de personas |
| `/admin/cursos`, `/admin/docentes` | Administración | Cursos y docentes |
| `/admin/academico/` | Administración / dirección | Panel académico |
| `/admin/academico/configuracion` | Administración | Escala institucional |
| `/admin/academico/anios` | Administración / dirección | Años y trimestres |
| `/admin/academico/materias` | Administración / dirección | Materias |
| `/admin/academico/asignaciones` | Administración / dirección | Materias por curso |
| `/admin/academico/notas` | Administración / dirección | Registro de calificaciones |
| `/admin/academico/observaciones` | Administración / dirección | Observaciones pedagógicas |
| `/admin/academico/historial` | Administración / dirección | Auditoría de notas |
| `/portal/` | Familias | Panel de la familia |
| `/portal/hijos/<id>` | Familias | Notas, asistencia y observaciones del estudiante |
| `/docentes/` | Docentes | Panel docente |
| `/docentes/cursos/<id>` | Docentes | Curso, asistencia y notas |

Las rutas con identificadores verifican en el servidor que el curso o estudiante
pertenezca al usuario autenticado; no basta con ocultar enlaces en la interfaz.

## Pruebas

```powershell
python -m pytest
```

Las pruebas cubren, entre otros flujos:

- sitio público, noticias, filtros, comentarios y respuestas 404;
- autenticación, bloqueo por intentos y cambio de contraseña;
- autorización por rol y aislamiento entre familias y docentes;
- administración de estudiantes, cursos, familias y comunicados;
- panel académico: escala, años, trimestres, materias, asignaciones, notas,
  observaciones, cierre de trimestre e historial de cambios;
- visualización de notas y observaciones por las familias, sin exponer las
  observaciones internas;
- asistencia y calificaciones registradas por docentes;
- prueba de humo de todas las rutas GET con cada rol;
- subida a Supabase con bucket, ruta relativa y URL correctos;
- uso de URLs firmadas cuando el bucket es privado;
- migración aditiva de `post_images` sin perder filas existentes.

Resultado actual: **consulte la salida de `python -m pytest`**.

## Base de datos

- **Local / por defecto:** SQLite en `instance/nueva_canaan.db`.
- **Producción opcional:** si existe `DATABASE_URL`, se usa esa conexión (por
  ejemplo PostgreSQL de Supabase). El código normaliza la URL.
- El esquema se crea y actualiza al arrancar: `db.create_all()` crea las tablas
  faltantes y `app/schema.py` agrega columnas nuevas sin borrar datos.
- `python -m app.cli init-and-seed` prepara las tablas y la cuenta administradora
  inicial; `seed-demo` agrega datos ficticios identificados como `(DEMO)`.
- Para empezar de cero en local: detener el servidor, borrar
  `instance/nueva_canaan.db` y ejecutar de nuevo
  `python -m app.cli init-and-seed`.

## Fotografías y adjuntos

- En producción las fotografías nuevas se guardan en **Supabase Storage**
  (`SUPABASE_STORAGE_BUCKET`, por defecto `nueva-canaan`) y sobreviven a los
  reinicios y redespliegues de Render.
- Variables requeridas en Render: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
  `SUPABASE_STORAGE_BUCKET=nueva-canaan` y `STORAGE_BACKEND=supabase`.
  `SUPABASE_SERVICE_KEY` es secreta y nunca se incluye en el repositorio.
- En desarrollo, sin credenciales de Supabase, se guardan en
  `instance/uploads/` (configurable con `UPLOAD_FOLDER`). El backend se elige
  con `STORAGE_BACKEND=auto|supabase|local`.
- La base guarda `storage`, `path` y `url`; si el bucket es privado se generan
  URLs firmadas temporales. Las fotografías antiguas del disco local se siguen
  mostrando como archivos heredados.
- La migración de arranque agrega `storage` y `url` a `post_images` sin borrar
  filas. Las tablas del portal (`news_images` y `media_files`) incluyen esas
  columnas desde su creación. Las fotografías anteriores quedan con
  `storage=local` y siguen mostrándose desde `instance/uploads/` mientras
  exista el archivo.
- El bucket `nueva-canaan` puede ser privado. En ese caso las rutas de imagen
  (`/noticias/foto/<id>`) redirigen a una **URL firmada temporal** generada en
  el servidor; no es necesario hacer público el bucket.
- Si las variables de Supabase faltan, el arranque registra
  `Almacenamiento de fotografías: backend=... configurado=False ...` y las
  subidas fallan con un mensaje visible en lugar de guardar en el disco efímero
  cuando `STORAGE_BACKEND=supabase`.
- Se permiten PNG, JPG/JPEG y WEBP. Cada archivo se valida por firma binaria
  (sin Pillow), se renombra con `secure_filename` + UUID y se guarda en el
  backend activo.
- Límites: `MAX_ATTACHMENT_MB=5` por fotografía y `MAX_UPLOAD_MB=8` para el
  envío completo. No se redimensionan las imágenes para no agregar dependencias.

## Render y GitHub

Se conserva el mismo repositorio y el mismo servicio de Render:

- `Procfile` y `requirements.txt` se mantienen.
- `render.yaml` conserva el servicio `nueva-canaan`, la región, el plan, las variables y el comando de arranque:
  `python -m app.cli init-and-seed && gunicorn wsgi:app ...`
- No se cambiaron innecesariamente las variables de entorno existentes.

### Persistencia

El sistema de archivos del plan gratuito de Render es **efímero**:

- Si `DATABASE_URL` apunta a Supabase/PostgreSQL, las publicaciones persisten
  entre despliegues.
- Las fotografías nuevas se guardan en **Supabase Storage** cuando están definidos
  `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` y `SUPABASE_STORAGE_BUCKET`. El backend se
  activa con `STORAGE_BACKEND=supabase`.
- `SUPABASE_URL` debe ser la **URL base del proyecto**
  (`https://<ref>.supabase.co`), sin `/rest/v1` ni `/storage/v1`. El código tolera
  esos sufijos, pero la configuración correcta evita errores de ruta.
- El bucket puede ser privado: con `SUPABASE_STORAGE_PUBLIC=false` la aplicación
  genera URLs firmadas temporales para mostrar las fotografías.
- Las fotografías antiguas con `storage='local'` no se migran automáticamente:
  sus archivos vivían en el disco efímero y pueden haberse perdido.
- Alternativa con **disco persistente** (plan de pago):
  1. Descomentar el bloque `disk` de `render.yaml`.
  2. Definir `UPLOAD_FOLDER=/var/data/uploads` y `STORAGE_BACKEND=local`.
- Si se desea SQLite persistente en ese disco, definir además:
  `DATABASE_URL=sqlite:////var/data/nueva_canaan.db`.
- Si no se configura nada, la aplicación funciona, pero la base y las fotos
  pueden perderse al redesplegar en el plan gratuito.

### Supabase preparado (proyecto `kznbowtnjankvyqsntfu`)

La base PostgreSQL del proyecto está activa (región `us-east-2`, PostgreSQL 17).
Las tablas de la aplicación se crean con `init-and-seed` o al arrancar con
`DATABASE_URL` configurada.

| Dato | Valor |
| --- | --- |
| Proyecto | `kznbowtnjankvyqsntfu` |
| Pooler (IPv4) | `aws-1-us-east-2.pooler.supabase.com` |
| Usuario | `postgres.kznbowtnjankvyqsntfu` |
| Puerto transacción | `6543` (recomendado para Render) |
| Puerto sesión | `5432` |
| Base | `postgres` |

> La conexión directa (`db.kznbowtnjankvyqsntfu.supabase.co`) es solo IPv6;
> Render debe usar el **pooler**.

Pasos:

1. Supabase → **Project Settings → Database**: copiar o restablecer la
   contraseña de la base.
2. En local, agregar a `.env` (no se versiona):
   ```text
   DATABASE_URL=postgresql://postgres.kznbowtnjankvyqsntfu:CONTRASEÑA@aws-1-us-east-2.pooler.supabase.com:6543/postgres
   ```
3. Comprobar la conexión sin modificar nada:
   ```powershell
   python tools/check_supabase.py
   ```
4. Crear las tablas y el administrador (solo con autorización):
   ```powershell
   python -m app.cli init-and-seed
   ```
5. En Render → **Environment**, agregar la misma `DATABASE_URL` y hacer
   **Manual Deploy → Deploy latest commit**. En Logs debe aparecer
   `Base de datos en uso: postgresql+psycopg://...@aws-1-us-east-2.pooler.supabase.com:6543/postgres`.

La contraseña debe ir codificada si contiene `@`, `:`, `/`, `#` o `?` (por
ejemplo `@` → `%40`). `config.py` ya desactiva las sentencias preparadas
cuando el puerto es `6543`, requisito del pooler en modo transacción.

> Desde algunas redes domésticas el pooler responde lento o de forma
> intermitente (`connection timeout expired` en una de sus IPs). `config.py`
> limita cada intento con `DB_CONNECT_TIMEOUT` (10 s por defecto) y libpq pasa
> a la siguiente dirección. Si en local las páginas tardan demasiado, bajar ese
> valor en `.env` (por ejemplo 4). En Render no suele ser necesario.

### Asistente conectado por MCP

El archivo `.vscode/mcp.json` (no se versiona) declara el servidor MCP remoto
oficial de Supabase en modo **solo lectura**, limitado al proyecto:

```text
https://mcp.supabase.com/mcp?project_ref=kznbowtnjankvyqsntfu&read_only=true
```

- En VS Code: paleta de comandos → **MCP: List Servers** → iniciar `supabase`
  y completar el inicio de sesión OAuth en el navegador.
- En Cline: **MCP Servers → Remote Servers → Add**, con el mismo nombre y URL.
- `read_only=true` impide crear, alterar o borrar datos. Para habilitar
  escrituras hay que quitar ese parámetro de forma deliberada.
- El servidor remoto usa OAuth; no requiere `SUPABASE_ACCESS_TOKEN` ni
  Node.js. El token `sbp_...` solo se usa con la variante local
  (`npx @supabase/mcp-server-supabase`).

### Diagnóstico: «las publicaciones no se guardan en Render»

1. Abrir **Render → servicio `nueva-canaan` → Logs** y buscar la línea de arranque `Base de datos en uso: ...`.
   - Si empieza por `sqlite:`, la aplicación está usando el disco efímero y las
     publicaciones desaparecen al redesplegar, reiniciar o suspenderse el
     servicio por inactividad. Además verá el aviso `ATENCIÓN: se está usando
     SQLite en el disco EFÍMERO de Render`.
   - Si empieza por `postgresql+psycopg:`, la base es persistente; un fallo al
     publicar será entonces un error de conexión/escritura, visible en Logs con
     el mensaje `No se pudo guardar la publicación`.
2. Revisar **Render → Environment** que exista `DATABASE_URL` (en `render.yaml`
   está con `sync: false`, por lo que **no** se crea automáticamente) y que
   apunte a la cadena *Session pooler* o *Transaction pooler* de Supabase.
3. Tras guardar la variable, Render vuelve a desplegar. El comando
   `init-and-seed` crea las tablas faltantes y el administrador definido en
   `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
4. Las publicaciones creadas antes de configurar `DATABASE_URL` se pierden: la
   base SQLite efímera ya no existe. Hay que volver a publicarlas.
5. Las fotografías necesitan Supabase Storage o un disco persistente
   (`UPLOAD_FOLDER`); guardar sólo la base en Supabase no conserva las fotos
   locales antiguas.

## Roles y permisos

| Rol | Alcance |
| --- | --- |
| `admin` | Configuración general, usuarios, académico, contenido y auditoría |
| `direction` | Gestión académica y consulta, sin administración de usuarios |
| `teacher` | Sólo sus cursos: tareas, asistencia, notas y comunicados |
| `parent` | Sólo sus estudiantes vinculados: notas, asistencia, observaciones visibles y comunicados |

Los permisos se comprueban en cada vista del servidor. Las notas nunca se
publican en páginas abiertas y las observaciones internas no se muestran a las
familias.

## Seguridad

- No hay registro público ni recuperación automática de contraseña; las cuentas
  las crea la administración.
- Contraseñas con hash PBKDF2 (`werkzeug.security`) y bloqueo temporal tras
  varios intentos fallidos.
- CSRF activo en todos los formularios.
- Cookies `HttpOnly`, `SameSite=Lax` y `Secure` en producción.
- Cabeceras de seguridad (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy` y `Permissions-Policy`).
- Validación de archivos en el servidor y protección contra rutas maliciosas.
- Historial `GradeChange` para cada alta, modificación o eliminación de nota.

## Notas

- La copia de seguridad previa a la restauración se guardó fuera del repositorio,
  en `D:\gabby\backups\`.
- Las credenciales de Supabase (`SUPABASE_SERVICE_KEY`) y la contraseña de la
  base nunca deben incluirse en el repositorio ni en capturas de pantalla.
- La migración de fotografías locales antiguas a Supabase Storage y los datos de
  demostración deben ejecutarse con autorización expresa de la institución.
