import json
from unittest import TestCase
from unittest.mock import MagicMock, patch
from django.test import Client
from core.portal_views import visible_catalog


class AccessTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")

    def test_public_home_and_session_do_not_require_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode()
        response.close()
        self.assertIn("Explorar servicios", content)
        self.assertNotIn("validationList", content)
        session = self.client.get("/api/auth/sesion/")
        self.assertIsNone(session.json()["user"])
        self.assertIn("csrfToken", session.json())

    def test_internal_api_and_files_are_not_public(self):
        for route in ["/api/estado/", "/api/profesionales/", "/api/revisiones/", "/api/cuenta/", "/api/profesionales/other/documentos/00000000-0000-0000-0000-000000000001/"]:
            self.assertEqual(self.client.get(route).status_code, 401, route)
        self.assertEqual(self.client.get("/panel/").status_code, 302)
        self.assertEqual(self.client.get("/cuenta/").status_code, 302)

    def test_company_cannot_access_admin_api_or_interview(self):
        with patch("core.access.current_user", return_value={"_id":"company","rol":"empresa","perfilId":"company-profile"}):
            self.assertEqual(self.client.get("/api/estado/").status_code, 403)
            self.assertEqual(self.client.post("/api/profesionales/person/entrevista/", data="{}",content_type="application/json").status_code,403)

    def test_professional_cannot_access_another_profiles_files(self):
        with patch("core.access.current_user", return_value={"_id":"professional","rol":"profesional","perfilId":"own-profile"}), patch("core.workflow_views.database") as db:
            response=self.client.post("/api/profesionales/other-profile/documentos/")
            self.assertEqual(response.status_code,403)
            db.assert_not_called()

    def test_register_cannot_choose_admin_role(self):
        with patch("core.auth_views.rate_limit",return_value=True),patch("core.auth_views.database") as db:
            response=self.client.post("/api/auth/registro/",data=json.dumps({"nombre":"Usuario prueba","correo":"test@example.com","password":"A-long-valid-passphrase-982!","rol":"admin"}),content_type="application/json")
            self.assertEqual(response.status_code,400)
            db.assert_not_called()

    def test_public_catalog_is_a_projection_without_internal_data(self):
        profiles=MagicMock();services=MagicMock()
        profiles.find.return_value.sort.return_value.skip.return_value.limit.return_value=[{"_id":"p1","id":"p1","nombre":"Pública","estado":"validado","correo":"private@example.com","documentos":[{"private":True}],"entrevista":{"observaciones":"privado"}}]
        services.aggregate.return_value=[{"items":[{"id":"s1","titulo":"Servicio","profesionalId":"p1","professional":{"nombre":"Pública"},"revision":{"huella":"private"}}],"total":[{"value":1}],"categories":[]}]
        profiles.count_documents.return_value=1
        db=MagicMock();db.profesionales=profiles;db.servicios=services
        result=visible_catalog(db)
        encoded=json.dumps(result)
        self.assertNotIn("private",encoded)
        self.assertNotIn("entrevista",encoded)
        self.assertNotIn("revision",encoded)
        self.assertEqual(profiles.find.call_args.args[0]["estado"],"validado")
        self.assertEqual(services.aggregate.call_args.args[0][0]["$match"]["disponible"],True)

    def test_csrf_remains_required_on_login(self):
        response=Client(enforce_csrf_checks=True,HTTP_HOST="localhost").post("/api/auth/login/",data="{}",content_type="application/json")
        self.assertEqual(response.status_code,403)
