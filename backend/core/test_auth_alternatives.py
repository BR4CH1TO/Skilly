"""Alternativas observables de registro y acceso; MongoDB real solo en integración."""

import json
import os
from unittest import TestCase, skipUnless
from unittest.mock import patch

from django.test import Client

from . import test_integration as fixtures
from .auth_views import normalized_email, valid_password
from .contracts import terms_snapshot


class PasswordContractTests(TestCase):
    """Verifica bordes exactos sin sustituir la política configurada de Django."""

    def test_seven_characters_are_rejected(self):
        with self.assertRaises(ValueError):
            valid_password("Qz7!xP2")

    def test_eight_non_common_characters_are_accepted(self):
        self.assertIsNone(valid_password("Qz7!xP2#"))

    def test_128_characters_are_accepted(self):
        self.assertIsNone(valid_password("Qz7!xP2#" * 16))

    def test_129_characters_are_rejected(self):
        with self.assertRaises(ValueError):
            valid_password("Qz7!xP2#" * 16 + "x")

    def test_common_password_is_rejected(self):
        with self.assertRaises(ValueError):
            valid_password("password")

    def test_numeric_password_is_rejected(self):
        with self.assertRaises(ValueError):
            valid_password("9361752840")

    def test_missing_password_is_rejected(self):
        with self.assertRaises(ValueError):
            valid_password(None)

    def test_non_text_password_is_rejected(self):
        with self.assertRaises(ValueError):
            valid_password(9361752840)

    def test_email_is_trimmed_and_casefolded(self):
        self.assertEqual(
            normalized_email("  CUENTA@example.com  "), "cuenta@example.com"
        )

    def test_invalid_email_is_rejected(self):
        with self.assertRaises(ValueError):
            normalized_email("sin-arroba")

    def test_malformed_json_returns_400(self):
        response = Client(HTTP_HOST="localhost").post(
            "/api/auth/login/",
            data="{",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "JSON inválido.")

    def test_json_array_is_not_an_auth_command(self):
        response = Client(HTTP_HOST="localhost").post(
            "/api/auth/login/",
            data="[]",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Se requiere un objeto JSON.")

    def test_invalid_password_never_reaches_account_insert(self):
        with (
            patch("core.auth_views.rate_limit", return_value=True),
            patch("core.auth_views.database") as db,
        ):
            response = Client(HTTP_HOST="localhost").post(
                "/api/auth/registro/",
                data=json.dumps({"correo": "nuevo@example.com", "password": "corta"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)
        db.assert_not_called()


@skipUnless(os.getenv("SKILLY_INTEGRATION") == "1", "Requiere MongoDB temporal.")
class AuthAlternativeIntegrationTests(TestCase):
    """Comprueba persistencia, sesión y errores de acceso en una base descartable."""

    def setUp(self):
        self.fixture = fixtures.RealIntegrationTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def registration(self, **changes):
        policy = terms_snapshot()
        data = {
            "nombre": "Cuenta de alternativa",
            "correo": "nuevo@example.com",
            "password": self.fixture.password,
            "rol": "empresa",
            "mayorEdad": True,
            "aceptoTerminos": True,
            "hashTerminos": policy["sha256"],
        }
        data.update(changes)
        return self.fixture.call(self.fixture.client(), "/api/auth/registro/", data)

    def test_duplicate_normalized_email_keeps_one_account(self):
        self.assertEqual(self.registration().status_code, 201)
        self.assertEqual(
            self.registration(correo=" NUEVO@EXAMPLE.COM ").status_code, 409
        )
        self.assertEqual(self.fixture.db.usuarios.count_documents({}), 1)
        self.assertEqual(self.fixture.db.empresas.count_documents({}), 1)

    def test_outdated_terms_do_not_create_account_or_profile(self):
        self.assertEqual(self.registration(hashTerminos="obsoleto").status_code, 400)
        self.assertEqual(self.fixture.db.usuarios.count_documents({}), 0)
        self.assertEqual(self.fixture.db.empresas.count_documents({}), 0)

    def test_missing_consent_does_not_create_account(self):
        self.assertEqual(self.registration(aceptoTerminos=False).status_code, 400)
        self.assertEqual(self.fixture.db.usuarios.count_documents({}), 0)

    def test_wrong_and_unknown_credentials_share_error(self):
        self.fixture.signup("existente@example.com", "empresa")
        results = [
            self.fixture.call(
                self.fixture.client(),
                "/api/auth/login/",
                {
                    "correo": email,
                    "password": "Incorrecta-2026!Qz",
                },
            )
            for email in ["existente@example.com", "ausente@example.com"]
        ]
        self.assertEqual([r.status_code for r in results], [401, 401])
        self.assertEqual(results[0].json(), results[1].json())
        self.assertEqual(results[0].json()["error"], "Correo o contraseña incorrectos.")
        self.assertTrue(all("skilly_session" not in r.cookies for r in results))

    def test_logout_prevents_reuse_of_previous_cookie(self):
        client = self.fixture.signup("salida@example.com", "empresa")
        token = client.cookies["skilly_session"].value
        response = self.fixture.call(client, "/api/auth/logout/")
        self.assertEqual(response.status_code, 200)
        previous = self.fixture.client()
        previous.cookies["skilly_session"] = token
        self.assertEqual(previous.get("/api/cuenta/").status_code, 401)
