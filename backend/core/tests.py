import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.test import Client
from pymongo.errors import ConnectionFailure, DuplicateKeyError

from core.storage import COLLECTIONS, serialize, to_document, validate_record


class RecordApiTests(TestCase):
    def setUp(self):
        self.access_patch = patch("core.access.current_user", return_value={"_id": "test-admin", "nombre": "Administración de prueba", "rol": "admin"})
        self.access_patch.start()
        self.addCleanup(self.access_patch.stop)
        self.db = MagicMock()
        self.collection = self.db.__getitem__.return_value
        self.collection.find.return_value.sort.return_value = []
        self.collection.find_one.return_value = None
        self.collection.replace_one.return_value.matched_count = 1
        self.patch = patch("core.views.database", return_value=self.db)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.review_patch = patch("core.views.apply_review", side_effect=lambda db, resource, document: document)
        self.review_patch.start()
        self.addCleanup(self.review_patch.stop)
        self.client = Client(enforce_csrf_checks=True, HTTP_HOST="localhost")
        self.token = self.client.get("/api/estado/").json()["csrfToken"]
        self.professional = {"id": "test-persona", "nombre": "Persona de prueba", "profesion": "Diseño", "estado": "revision"}

    def write(self, method, url, value):
        return getattr(self.client, method)(url, data=json.dumps(value),
            content_type="application/json", HTTP_X_CSRFTOKEN=self.token)

    def test_initial_read_does_not_insert_anything(self):
        result = self.client.get("/api/estado/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["state"], {key: [] for key in COLLECTIONS})
        self.collection.insert_one.assert_not_called()
        self.collection.update_one.assert_not_called()
        self.assertIn("no-store", result.headers["Cache-Control"])

    def test_create_one_person_in_its_own_collection(self):
        result = self.write("post", "/api/profesionales/", {"record": self.professional})
        self.assertEqual(result.status_code, 201)
        self.db.__getitem__.assert_called_with("profesionales")
        inserted = self.collection.insert_one.call_args.args[0]
        self.assertEqual(inserted["_id"], "test-persona")
        self.assertEqual(inserted["nombre"], "Persona de prueba")
        self.assertNotIn("state", inserted)

    def test_update_checks_version_and_identity(self):
        result = self.write("put", "/api/profesionales/test-persona/", {"record": self.professional, "version": 1})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.collection.replace_one.call_args.args[0], {"_id": "test-persona", "_version": 1})
        self.collection.replace_one.return_value.matched_count = 0
        result = self.write("put", "/api/profesionales/test-persona/", {"record": self.professional, "version": 1})
        self.assertEqual(result.status_code, 409)
        result = self.write("put", "/api/profesionales/otro/", {"record": self.professional, "version": 1})
        self.assertEqual(result.status_code, 400)

    def test_csrf_and_validation_prevent_writes(self):
        response = self.client.post("/api/profesionales/", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.write("post", "/api/profesionales/", {"record": {}}).status_code, 400)
        self.assertEqual(self.write("post", "/api/no-existe/", {"record": self.professional}).status_code, 404)
        injected = {**self.professional, "$set": {"nombre": "otro"}}
        self.assertEqual(self.write("post", "/api/profesionales/", {"record": injected}).status_code, 400)
        self.collection.insert_one.assert_not_called()

    def test_rejects_missing_references(self):
        service = {"id": "test-servicio", "titulo": "Servicio", "profesionalId": "inexistente", "precio": 1000, "disponible": True}
        self.assertEqual(self.write("post", "/api/servicios/", {"record": service}).status_code, 400)
        self.collection.insert_one.assert_not_called()

    def test_duplicate_and_connection_errors(self):
        self.collection.insert_one.side_effect = DuplicateKeyError("duplicate")
        self.assertEqual(self.write("post", "/api/profesionales/", {"record": self.professional}).status_code, 409)
        self.collection.insert_one.side_effect = ConnectionFailure("offline")
        with self.assertLogs("core.views", level="ERROR"):
            self.assertEqual(self.write("post", "/api/profesionales/", {"record": self.professional}).status_code, 503)

    def test_dates_are_bson_dates_and_money_is_integer(self):
        record = {"id": "historial-test", "tipo": "Prueba", "titulo": "Prueba", "descripcion": "Prueba", "fecha": "2026-10-15T12:00:00Z"}
        document = to_document("historial", record)
        self.assertEqual(document["fecha"], datetime(2026, 10, 15, 12, tzinfo=timezone.utc))
        self.assertEqual(serialize(document), record)
        with self.assertRaises(ValueError):
            validate_record("servicios", {"id": "servicio", "titulo": "Servicio", "profesionalId": "test", "precio": True, "disponible": True}, self.db)
