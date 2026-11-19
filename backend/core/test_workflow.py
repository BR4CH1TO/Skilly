from unittest import TestCase
from unittest.mock import patch

from django.test import Client, override_settings

from core.workflow import profile_checks, profile_result, service_result


class WorkflowRuleTests(TestCase):
    def profile(self):
        return {"nombre": "Persona de prueba", "profesion": "Diseño", "ubicacion": "Santiago, Chile",
            "resumen": "Experiencia profesional en diseño de productos y servicios digitales.",
            "habilidades": ["Diseño", "Investigación"],
            "documentos": [{"tipo": "cv", "formatoComprobado": True}, {"tipo": "formacion", "formatoComprobado": True}]}

    def test_missing_documents_never_pass_automatically(self):
        p = self.profile(); p["documentos"] = []
        result = profile_result(p, {"resultado": "aprobada"})
        self.assertEqual(result["estado"], "revision")
        self.assertEqual(len([c for c in result["comprobaciones"] if c["resultado"] == "pendiente"]), 2)

    def test_documents_alone_never_replace_human_interview(self):
        result = profile_result(self.profile(), {})
        self.assertEqual(result["estado"], "revision")
        self.assertEqual(result["etapa"], "Pendiente de entrevista")

    def test_interview_approval_completes_process(self):
        self.assertEqual(profile_result(self.profile(), {"resultado": "aprobada"})["estado"], "validado")
        self.assertEqual(profile_result(self.profile(), {"resultado": "rechazada", "observaciones": "No cumple requisitos."})["estado"], "rechazado")
        self.assertEqual(profile_result(self.profile(), {"resultado": "segunda"})["estado"], "segunda")

    def test_service_requires_deliverables_and_validated_profile(self):
        service = {"titulo": "Diseño de producto", "descripcion": "Diseño de un producto digital con investigación y pruebas de uso.", "precio": 20000, "categoria": "Diseño", "duracion": "Dos semanas", "entregables": "Prototipo navegable y documentación."}
        self.assertEqual(service_result(service, {"estado": "validado"})["estado"], "correccion")
        validated = {"estado": "validado", "validacionProceso": "proof"}
        self.assertEqual(service_result(service, validated)["estado"], "publicado")
        service["entregables"] = ""
        result = service_result(service, validated)
        self.assertEqual(result["estado"], "correccion")
        self.assertEqual(next(c for c in result["comprobaciones"] if c["codigo"] == "SER-06")["resultado"], "pendiente")

    def test_false_document_metadata_does_not_pass(self):
        p = self.profile();p["documentos"][0]["formatoComprobado"] = "true"
        self.assertFalse(all(c["resultado"] == "aprobado" for c in profile_checks(p)))

    @override_settings(SKILLY_INTERVIEW_KEY="secret-test")
    def test_interview_requires_admin_before_database_access(self):
        with patch("core.workflow_views.database") as db:
            response = Client(HTTP_HOST="localhost").post("/api/profesionales/test/entrevista/", data={}, content_type="application/json")
            self.assertEqual(response.status_code, 401)
            db.assert_not_called()
