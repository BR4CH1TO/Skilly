from django.core.management.base import BaseCommand
from bson import BSON
import os
import tempfile

from core.storage import database, ensure_indexes
from core.workflow import review_profile, review_service


class Command(BaseCommand):
    help = "Prepara índices y revisiones verificables, conservando los registros existentes."

    def handle(self, *args, **options):
        db = database()
        snapshot = {name: list(db[name].find()) for name in db.list_collection_names()}
        descriptor, backup_path = tempfile.mkstemp(prefix="skilly-before-workflow-", suffix=".bson")
        with os.fdopen(descriptor, "wb") as backup:
            backup.write(BSON.encode({"collections": snapshot}))
        self.stdout.write(f"Copia anterior fuera del proyecto: {backup_path}")
        ensure_indexes(db)
        for profile in db.profesionales.find({}, {"_id": 1}):
            result = review_profile(db, profile["_id"])
            self.stdout.write(f"Profesional {profile['_id']}: {result['estado']}")
        for service in db.servicios.find({}, {"_id": 1}):
            review_service(db, service["_id"])
        self.stdout.write(self.style.SUCCESS("Recorrido y revisiones automáticas preparados."))
