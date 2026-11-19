from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pymongo import MongoClient
from pymongo.errors import PyMongoError


class Command(BaseCommand):
    help = "Comprueba la conexión a MongoDB sin modificar datos."

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        try:
            with MongoClient(database["HOST"], **database["OPTIONS"]) as client:
                client[database["NAME"]].command("ping")
        except PyMongoError:
            raise CommandError(
                "No se pudo conectar a MongoDB. Revisa MONGODB_URI en backend/.env, "
                "las credenciales y que el servidor esté disponible."
            ) from None
        self.stdout.write(self.style.SUCCESS("Conexión a MongoDB correcta."))
