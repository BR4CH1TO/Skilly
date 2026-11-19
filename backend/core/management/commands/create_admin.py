from getpass import getpass
from uuid import uuid4
from datetime import datetime, timezone
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from core.access import setup_access
from core.auth_views import normalized_email, valid_password
from core.storage import database

class Command(BaseCommand):
    help = "Crea una cuenta administradora; la contraseña se solicita sin mostrarla."
    def add_arguments(self, parser):
        parser.add_argument("--email")
        parser.add_argument("--name", default="Administración Skilly")
    def handle(self, *args, **options):
        try:
            email = normalized_email(options['email'] or input("Correo de administración: "))
            password = getpass("Contraseña (mínimo 8 caracteres): ")
            valid_password(password)
            if getpass("Repite la contraseña: ") != password:
                raise ValueError("Las contraseñas no coinciden.")
            db=database();setup_access(db)
            if db.usuarios.find_one({"correo":email}):
                raise ValueError("Ese correo ya tiene una cuenta; no se modifica su rol.")
            db.usuarios.insert_one({"_id":str(uuid4()),"nombre":options['name'],"correo":email,"passwordHash":make_password(password),"rol":"admin","activo":True,"fecha":datetime.now(timezone.utc)})
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS("Cuenta administradora creada. Inicia sesión desde la vitrina."))
