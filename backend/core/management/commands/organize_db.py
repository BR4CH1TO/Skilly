import os
import tempfile

from bson import BSON
from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError

from core.storage import COLLECTIONS, database, ensure_indexes, record_id, serialize, to_document


def migrate_database(db, backup_path=None):
    legacy = db.datos.find_one({"_id": "skilly"})
    if legacy is None:
        ensure_indexes(db)
        return None, {name: db[name].count_documents({}) for name in COLLECTIONS.values()}
    # Una copia BSON completa fuera del proyecto conserva todos los tipos originales.
    if backup_path is None:
        descriptor, backup_path = tempfile.mkstemp(prefix="skilly-before-migration-", suffix=".bson")
        with os.fdopen(descriptor, "wb") as backup:
            backup.write(BSON.encode(legacy))
    else:
        with open(backup_path, "xb") as backup:
            backup.write(BSON.encode(legacy))
    counts = {}
    for key, name in COLLECTIONS.items():
        records = legacy["state"][key]
        identifiers = [record_id(record) for record in records]
        if len(identifiers) != len(set(identifiers)):
            raise CommandError(f"Hay identificadores duplicados en {name}; se conserva la colección original.")
        for record in records:
            document = to_document(name, record)
            existing = db[name].find_one({"_id": document["_id"]})
            if existing is not None and serialize(existing) != serialize(document):
                raise CommandError(f"El registro {document['_id']} ya existe con otros datos; no se sobrescribe.")
            db[name].update_one({"_id": document["_id"]}, {"$setOnInsert": document}, upsert=True)
            saved = db[name].find_one({"_id": document["_id"]})
            if serialize(saved) != serialize(document):
                raise CommandError(f"No se pudo verificar {name}/{document['_id']}.")
        counts[name] = len(records)
    ensure_indexes(db)
    # No retira la estructura anterior si recibió cambios durante la migración.
    deleted = db.datos.delete_one({"_id": "skilly", "version": legacy["version"]})
    if deleted.deleted_count != 1:
        raise CommandError("Los datos originales cambiaron durante la migración. Se conserva el origen y la copia BSON.")
    if db.datos.count_documents({}) == 0:
        db.datos.drop()
    return backup_path, counts


class Command(BaseCommand):
    help = "Migra el documento antiguo a colecciones independientes y crea sus índices."

    def handle(self, *args, **options):
        try:
            backup, counts = migrate_database(database())
        except (PyMongoError, ValueError) as error:
            raise CommandError(f"No se pudo completar la organización: {error}") from error
        if backup:
            self.stdout.write(f"Copia de seguridad fuera del proyecto: {backup}")
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count} registros")
        self.stdout.write(self.style.SUCCESS("Colecciones e índices preparados."))
