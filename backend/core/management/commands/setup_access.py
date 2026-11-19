from django.core.management.base import BaseCommand
from core.access import setup_access
from core.storage import database

class Command(BaseCommand):
    help = "Crea índices de cuentas, sesiones y control de intentos."
    def handle(self, *args, **options):
        setup_access(database())
        self.stdout.write(self.style.SUCCESS("Accesos preparados. Usa create_admin para crear la cuenta de administración."))
