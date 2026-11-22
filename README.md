# Muro institucional Nueva Canaán

Aplicación web mínima para publicar noticias del **Colegio Técnico Humanístico Nueva Canaán**. Los visitantes ven el muro sin iniciar sesión; una única cuenta administradora puede publicar y eliminar noticias con fotografías.

## Qué hace

- Página principal pública con el nombre de Nueva Canaán y las publicaciones ordenadas de la más reciente a la más antigua.
- Muro con tarjetas blancas sobre fondo gris claro, fotografías en cuadrícula y diseño adaptable a celulares.
- Inicio de sesión exclusivo para el administrador. No existe registro público de usuarios.
- Cuadro para escribir una noticia, seleccionar varias fotografías y presionar **Publicar**.
- Las publicaciones aparecen automáticamente en el muro.
- El administrador puede eliminar una publicación y sus fotografías.
- No se agregaron dependencias nuevas: se reutilizan las que ya estaban en `requirements.txt`.

## Tecnologías

| Componente | Uso |
| --- | --- |
| Python 3.12.6 + Flask | Aplicación web |
| Flask-SQLAlchemy / SQLAlchemy 2.0 | Acceso a datos |
| SQLite | Base de datos local por defecto (`instance/nueva_canaan.db`) |
| PostgreSQL / Supabase | Opcional mediante `DATABASE_URL` en producción |
| Flask-Login | Sesión del único administrador |
| Flask-WTF / CSRFProtect | Protección de formularios |
| Jinja2 | Plantillas HTML |
| Gunicorn | Servidor en Render |

No se usa Pillow ni almacenamiento externo. Las imágenes se validan por extensión, tamaño y firma binaria, y se guardan en el sistema de archivos.

## Estructura

```text
app/
  __init__.py        fábrica de Flask, filtros, errores y cabeceras
  cli.py             init-db, init-and-seed y create-admin
  extensions.py      SQLAlchemy, Flask-Login y CSRF
  models.py          Admin, Post y PostImage
  routes.py          muro público, login, publicar, eliminar e imágenes
  utils.py           texto, fechas, validación y guardado de fotos
  templates/         base, muro, login y errores
  static/            CSS, JS y logo
config.py            configuración y conexión a la base de datos
instance/            base SQLite y fotografías (no se versiona)
tests/               pruebas automatizadas
run.py / wsgi.py     entradas local y de Gunicorn
Procfile             comando web
render.yaml          configuración del servicio en Render
requirements.txt     dependencias existentes (sin cambios)
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

Abrir `http://127.0.0.1:5000`. El correo y la contraseña iniciales se toman de `ADMIN_EMAIL` y `ADMIN_PASSWORD` en `.env` (o de las variables de entorno de Render). La contraseña se guarda como hash PBKDF2 en la tabla `admins`; nunca en texto plano.

También se puede iniciar con:

```powershell
flask --app run.py run
```

## Rutas principales

| Método | Ruta | Acceso | Función |
| --- | --- | --- | --- |
| GET | `/` | Público | Muro de publicaciones |
| GET/POST | `/login` | Público | Acceso del administrador |
| POST | `/logout` | Administrador | Cerrar sesión |
| POST | `/publicar` | Administrador | Crear publicación con fotos |
| POST | `/publicaciones/<id>/eliminar` | Administrador | Eliminar publicación |
| GET | `/imagenes/<id>` | Público | Servir una fotografía |

## Pruebas

```powershell
python -m pytest -q
```

Las pruebas cubren:

- visualización pública sin sesión;
- rechazo de credenciales incorrectas;
- login correcto y aparición del cuadro de publicación;
- publicación con dos fotografías y acceso a las imágenes;
- orden de las publicaciones (más recientes primero);
- eliminación de la publicación y de sus archivos;
- rechazo de archivos que no son imágenes;
- respuesta 404 para imágenes inexistentes;
- subida a Supabase con bucket, ruta relativa y URL correctos;
- uso de URLs firmadas cuando el bucket es privado;
- migración aditiva de `post_images` sin perder filas existentes.

Resultado actual: **14 pruebas aprobadas**.

## Base de datos

- **Local / por defecto:** SQLite en `instance/nueva_canaan.db`.
- **Producción opcional:** si existe `DATABASE_URL`, se usa esa conexión (por ejemplo PostgreSQL de Supabase). El código normaliza la URL y mantiene el soporte existente.
- Tablas nuevas: `admins`, `posts` y `post_images`. Se crean automáticamente con `db.create_all()` al ejecutar `init-and-seed`.
- Si la base ya tenía las tablas del sistema anterior, **permanecen intactas** pero la versión simplificada no las utiliza ni las muestra. No se migraron publicaciones antiguas porque la base local tenía `news_posts` vacío.
- Para empezar de cero en local: detener el servidor, borrar `instance/nueva_canaan.db` y ejecutar de nuevo `python -m app.cli init-and-seed`.

## Fotografías

- En producción las fotografías nuevas se guardan en **Supabase Storage**
  (`SUPABASE_STORAGE_BUCKET`, por defecto `nueva-canaan`) y sobreviven a los
  reinicios y redespliegues de Render.
- Variables requeridas en Render: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
  `SUPABASE_STORAGE_BUCKET=nueva-canaan` y `STORAGE_BACKEND=supabase`.
  `SUPABASE_SERVICE_KEY` es secreta y nunca se incluye en el repositorio.
- La migración de arranque agrega `storage` y `url` a `post_images` sin borrar
  filas. Las fotografías anteriores quedan con `storage=local` y siguen
  mostrándose desde `instance/uploads/` mientras exista el archivo.
- El bucket `nueva-canaan` puede ser privado. En ese caso
  `/imagenes/<id>` redirige a una **URL firmada temporal** generada en el
  servidor; no es necesario hacer público el bucket.
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

- Si `DATABASE_URL` apunta a Supabase/PostgreSQL, las publicaciones persisten entre despliegues. Las fotografías siguen en el disco efímero y se pierden al redesplegar.
- Para conservar también las fotografías se necesita un **disco persistente** (plan de pago):
  1. Descomentar el bloque `disk` de `render.yaml`.
  2. Definir `UPLOAD_FOLDER=/var/data/uploads`.
- Si se desea SQLite persistente en ese disco, definir además:
  `DATABASE_URL=sqlite:////var/data/nueva_canaan.db`.
- Si no se configura nada, la aplicación funciona, pero la base y las fotos pueden perderse al redesplegar en el plan gratuito.

## Limpieza realizada

Se eliminaron los módulos y pantallas que ya no se utilizan:

- administración general, alumnos, docentes, padres y cursos;
- calendario, galería administrativa, comunicados y notificaciones;
- buzón de mensajes y formulario de contacto;
- comentarios, reacciones y moderación de noticias;
- migraciones Alembic, esquema SQL de Supabase y script de migración anterior;
- plantillas, CSS y JavaScript de los módulos retirados.

Antes de eliminar se verificó que no fueran necesarios para Flask, Gunicorn, Render ni para las rutas que quedaron.

## Seguridad

- Un solo tipo de cuenta: administrador. No hay registro público ni recuperación automática de contraseña.
- Contraseña almacenada con hash PBKDF2 (`werkzeug.security`).
- CSRF activo en todos los formularios.
- Cookies `HttpOnly`, `SameSite=Lax` y `Secure` en producción.
- Cabeceras de seguridad (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` y `Permissions-Policy`).
- Validación de archivos en el servidor y protección contra rutas maliciosas.

## Notas

- La copia de seguridad previa a la simplificación se guardó fuera del repositorio, en `D:\gabby\backups\`.
- La aplicación no incluye comentarios, reacciones, calendario, galería, contacto ni paneles adicionales: solo el muro, el acceso y la publicación de noticias.
