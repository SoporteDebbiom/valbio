"""Punto de entrada. Ejecuta:  python run.py
En producción usa un servidor WSGI:  gunicorn 'app:create_app()'
"""
import os
from app import create_app

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    # host=127.0.0.1 por seguridad; cámbialo a 0.0.0.0 sólo si lo necesitas.
    app.run(host="127.0.0.1", port=5000, debug=app.config.get("DEBUG", False))
