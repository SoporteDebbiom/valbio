# Resultados de Validación — suite bioanalítica

Aplicación web para registrar y calcular validaciones de métodos bioanalíticos
(HPLC / LC-MS/MS) en un laboratorio farmacéutico. Reproduce las hojas del libro
de Excel original con las mismas fórmulas (promedio, desviación estándar muestral,
CV %, % de desviación, % de recobro, factor de matriz normalizado, acarreo,
regresión ponderada y % de error), verificadas contra Excel.

Es un espacio de trabajo compartido: varias personas entran a la vez, crean y
editan las mismas hojas, y todo queda registrado.

## Qué incluye

- **Trabajo compartido en línea.** Todas las hojas son del equipo. Cualquier usuario
  autenticado puede abrir, crear y editar. Se guarda quién creó cada hoja y quién la
  modificó por última vez. Si dos personas editan el mismo módulo, al guardar se
  avisa del conflicto y se puede recargar o sobrescribir.
- **Presencia y actividad.** Un indicador muestra quién está conectado en ese momento.
  La página de actividad lista accesos y cambios (creó, modificó, eliminó) y se
  actualiza sola. Es visible para todos los usuarios.
- **Respaldos.** Copias de toda la base en formato JSON. Se generan de forma
  automática cada cierto tiempo mientras se trabaja, se pueden generar a mano,
  descargar y restaurar. Funciona igual con SQLite o PostgreSQL.
- **Acceso por roles.** Empleado y Administrador. La gestión de usuarios y los
  respaldos quedan reservados al administrador.
- **Importar de Excel.** Cada módulo tiene un botón "Importar de Excel" que acepta
  `.xlsx` y `.xlsm` (con macros). Al subir el archivo se abre un asistente donde se
  elige la hoja del libro, se indica si la primera fila son encabezados y se **mapea
  cada columna al campo correspondiente** (o, en los módulos por niveles, la columna de
  réplicas y la concentración nominal de cada nivel). El asistente **recuerda el último
  mapeo** de cada módulo, y en la tabla personalizada permite **importar varias hojas de
  una vez** (cada una se agrega como una tabla). Las macros nunca se ejecutan.
- **Tablas al estilo del libro de Excel.** Las tablas usan un formato limpio y
  bordeado, con encabezados en negrita, título de sección y un bloque de
  molécula/código/unidad, similar al machote de Excel.
- **Informe en PDF.** Cada hoja genera un informe imprimible y descargable en PDF con,
  por cada módulo, los **datos capturados** y los **resultados** con sus dictámenes.
- **Sin secretos en el código.** La clave de sesión, la base de datos y la contraseña
  del administrador se leen de variables de entorno. No hay contraseñas, llaves ni
  direcciones embebidas en el código.

## Seguridad

- Contraseñas almacenadas con hash y sal (Werkzeug); nunca en texto plano.
- Consultas a través del ORM de SQLAlchemy (sin concatenar SQL).
- Autoescape de plantillas (Jinja2) y protección CSRF en cada formulario (Flask-WTF).
- Cookies `HttpOnly` y `SameSite`; en producción se marcan `Secure`.
- Cabeceras `Content-Security-Policy`, `X-Frame-Options` y `X-Content-Type-Options`.
- En producción se exige definir `SECRET_KEY`; si falta, la aplicación no arranca.

## Estructura

```
valbio/
├── run.py                # arranque en desarrollo
├── config.py             # configuración (lee variables de entorno)
├── requirements.txt
├── render.yaml           # despliegue en Render
├── Procfile
├── .env.example          # plantilla de variables (sin valores reales)
├── app/
│   ├── __init__.py       # application factory
│   ├── extensions.py     # db, login, csrf
│   ├── models.py         # User, Project, ModuleData, Activity, SystemState
│   ├── backup.py         # respaldos JSON (manual y automático)
│   ├── auth/             # acceso y administración de usuarios
│   ├── main/             # listado de hojas
│   ├── validation/       # módulos de cálculo y motor de fórmulas
│   ├── collab/           # presencia y actividad
│   ├── backups/          # respaldos (administrador)
│   ├── templates/
│   └── static/
├── scripts/seed.py       # crea el administrador inicial
└── tests/                # pruebas (cálculo e integración)
```

## Cómo correrlo en tu equipo

```
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Abre http://localhost:5000. La primera vez se crea el usuario `admin`. Si no
defines `ADMIN_PASSWORD`, se genera una contraseña temporal que se imprime en la
consola; cámbiala al entrar.

Para fijar tus propias credenciales y clave, copia `.env.example` a `.env` y
complétalo.

## Usuarios y credenciales

Las cuentas de usuario se guardan en la base de datos, **nunca en el código**. El
repositorio no contiene ningún usuario ni contraseña, y `.gitignore` excluye la base
de datos (`*.db`) y el archivo `.env`, así que esos datos no llegan a GitHub.

- La primera vez se crea un único administrador (usuario `admin`, o el de
  `ADMIN_USERNAME`). Su contraseña sale de `ADMIN_PASSWORD`; si no la defines, se
  genera una aleatoria que se imprime una sola vez en la consola.
- Los demás usuarios los da de alta el administrador desde la sección Usuarios.
- Desde la terminal: `flask list-users` muestra las cuentas (sin contraseñas) y
  `flask create-admin` crea un administrador pidiendo la contraseña en el momento,
  sin escribirla en ningún archivo.

## Concurrencia y base de datos

Por defecto usa SQLite, configurado en modo WAL y con espera ante bloqueos, lo que
permite que varias personas trabajen a la vez en equipos pequeños. Para uso real
con muchos usuarios concurrentes conviene PostgreSQL: define la variable
`DATABASE_URL` y la aplicación la usa automáticamente.

## Respaldos

- Automáticos: se crea una copia cada `BACKUP_INTERVAL_HOURS` (6 por defecto)
  conforme se usa la aplicación, conservando las últimas `BACKUP_KEEP`.
- Manuales: desde la sección Respaldos, botón "Generar ahora" o "Descargar respaldo".
- Por línea de comandos: `flask backup` crea una copia y `flask restore archivo.json`
  la restaura.

En servidores con disco temporal (como el plan gratuito de Render) los archivos en
disco se pierden al redesplegar; en ese caso descarga respaldos con regularidad o
usa PostgreSQL, cuyo proveedor conserva los datos.

## Pruebas

```
pytest
```

## Despliegue

Ver `DESPLIEGUE.md` para subir el proyecto a GitHub y publicarlo en Render con un
enlace público.
