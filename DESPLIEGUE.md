# Guía rápida: subir a GitHub y publicar el link

Esta app es de **Python (Flask)**. Por eso:

- **GitHub** guarda el código y te da el link del repositorio (ej. `github.com/tuusuario/valbio`).
- Para tener un link que **abra la aplicación**, se conecta el repo a un servidor
  gratuito (**Render**), que te da una URL tipo `https://valbio.onrender.com`.

No necesitas instalar nada ni usar la terminal.

---

## Paso 1 — Descomprime el proyecto

Descomprime `valbio.zip`. Tendrás una carpeta llamada **`valbio`** con todos los
archivos. (No subas el `.zip`; sube los archivos de adentro.)

---

## Paso 2 — Súbelo a GitHub (desde el navegador)

1. Entra a <https://github.com> y crea una cuenta (gratis) si no tienes.
2. Arriba a la derecha: **＋ → New repository**.
3. Ponle un nombre, por ejemplo `valbio`. Déjalo **Public** o **Private** (cualquiera sirve).
   No marques "Add a README". Da clic en **Create repository**.
4. En la página del repo nuevo, haz clic en **uploading an existing file**
   (o en **Add file → Upload files**).
5. **Arrastra la carpeta `valbio`** (o todo su contenido) a esa zona. Espera a que suban todos los archivos.
6. Abajo, clic en **Commit changes**.

> ⚠️ **No subas el archivo `.env`.** Contiene tu contraseña y debe quedarse solo en
> tu computadora. Este método de arrastrar en el navegador **no** respeta las
> exclusiones automáticas, así que antes de arrastrar borra el `.env` de la carpeta
> (o no lo selecciones). La contraseña se la das a Render aparte, en el Paso 3. Si en vez de
> arrastrar usas la herramienta `git`, el `.env` se excluye solo y no hace falta borrarlo.

Listo: ese es tu **link de GitHub** (el código). Ya puedes compartirlo.

---

## Paso 3 — Publica el link que funciona (Render, gratis)

1. Entra a <https://render.com> y regístrate con **Continuar con GitHub** (así conecta tu repo solo).
2. En el panel: **New → Blueprint**.
3. Selecciona el repositorio `valbio`. Render detecta el archivo `render.yaml` y
   propone el servicio **valbio** (plan **Free**).
4. Te pedirá el valor de **ADMIN_PASSWORD**: escribe la contraseña que quieras
   para tu usuario administrador. (La clave secreta `SECRET_KEY` la genera Render solo.)
5. Clic en **Apply** / **Create**. Espera unos minutos a que diga **Live**.
6. Arriba verás la URL: `https://valbio-XXXX.onrender.com`. **Ese es tu link.**

Para entrar: usuario **admin** y la contraseña que pusiste en el paso 4.

> Si no aparece la opción Blueprint, usa **New → Web Service**, conecta el repo y
> escribe a mano:
> - **Build Command:** `pip install -r requirements.txt`
> - **Start Command:** `gunicorn run:app --bind 0.0.0.0:$PORT`
> - En **Environment**, agrega `FLASK_ENV = production` y una `SECRET_KEY` larga.

---

## Cosas que conviene saber del plan gratis

- **Se "duerme" tras 15 min sin uso** y tarda ~1 minuto en despertar en la primera
  visita. Es normal en el plan gratuito; para "siempre encendido" hay planes de pago.
- **Los datos pueden reiniciarse** entre despliegues, porque el plan gratis usa una
  base SQLite temporal. Para que los datos **persistan**, crea una base **PostgreSQL**
  en Render y agrega la variable `DATABASE_URL` (la app la usa automáticamente).
- **Cada vez que subas cambios a GitHub, Render vuelve a publicar solo.**

---

## ¿Solo quieres el código en GitHub, sin servidor?

Con el **Paso 2** basta. Tendrás el link del repositorio para compartir o respaldar.
Recuerda: ese link muestra el código, no ejecuta la app. Para una versión que abra
sin servidor, usa el prototipo de un solo archivo HTML como demostración.
