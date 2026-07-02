"""Formularios de autenticación (Flask-WTF: CSRF + validación de entrada)."""
from flask_wtf import FlaskForm
from wtforms import PasswordField, RadioField, StringField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField("Usuario", validators=[DataRequired()])
    password = PasswordField("Contraseña", validators=[DataRequired()])


class NewUserForm(FlaskForm):
    username = StringField("Usuario", validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Contraseña", validators=[DataRequired(), Length(min=6)])
    role = RadioField("Nivel", choices=[("Empleado", "Empleado"),
                                        ("Administrador", "Administrador")],
                      default="Empleado")
