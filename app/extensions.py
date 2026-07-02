"""Instancias únicas de las extensiones, inicializadas en la fábrica de la app."""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()             # ORM: consultas parametrizadas -> sin inyección SQL
login_manager = LoginManager()
csrf = CSRFProtect()          # token anti-CSRF en todos los formularios POST

login_manager.login_view = "auth.login"
login_manager.login_message = "Inicia sesión para continuar."
login_manager.login_message_category = "info"
