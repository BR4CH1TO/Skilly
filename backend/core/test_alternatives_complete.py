"""Ejecución individual de las alternativas pendientes en MongoDB descartable.

Cada método identifica el escenario del libro 02 y verifica respuesta y efecto
persistido. Las modificaciones de fechas/archivos pertenecen solo al laboratorio.
"""

import copy
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from pymongo.errors import DuplicateKeyError

from . import contracts as engine
from . import test_contracts as fixtures
from .business import book
from .storage import serialize, to_document
from .test_delivery import pdf_bytes


@skipUnless(os.getenv("SKILLY_INTEGRATION") == "1", "Requiere MongoDB temporal.")
class CompleteAlternativeTests(TestCase):
    """Contrasta cada alternativa con API y persistencia reales aisladas."""

    def setUp(self):
        self.case = fixtures.ContractIntegrationTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.db = self.case.db
        self.fx = self.case.fixture

    def call(self, role, url, data=None, method="post"):
        return self.fx.call(self.case.clients[role], url, data, method)

    def contract(self):
        return self.db.contratos.find_one({"_id": self.case.id})

    def assert_rejected(self, role, action, **data):
        before = self.contract()
        self.case.op(role, action, 400, **data)
        self.assertEqual(self.contract(), before)

    def profile_upload(self, content):
        profile = self.db.profesionales.find_one({"_id": self.case.pid})
        client = self.case.clients["profesional"]
        token = client.get("/api/auth/sesion/").json()["csrfToken"]
        return client.post(
            f"/api/profesionales/{self.case.pid}/documentos/",
            data={
                "version": profile["_version"],
                "tipo": "cv",
                "archivo": SimpleUploadedFile("respaldo.pdf", content),
            },
            HTTP_X_CSRFTOKEN=token,
        )

    def new_request(self, accepted=False, slot=None):
        slot = slot or engine.stamp(engine.now() + timedelta(days=5))
        sid = self.contract()["servicioId"]
        response = self.call(
            "empresa",
            "/api/cuenta/solicitudes/",
            {
                "servicioId": sid,
                "fecha": slot,
                "claveOperacion": uuid4().hex,
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        rid = response.json()["record"]["id"]
        if accepted:
            self.assertEqual(
                self.call(
                    "profesional",
                    "/api/cuenta/responder/",
                    {
                        "id": rid,
                        "estado": "aceptada",
                    },
                ).status_code,
                200,
            )
        return rid

    def fresh_proposal(self):
        agenda = self.db.agendas.find_one({"_id": self.case.aid})
        agenda = {
            k: v
            for k, v in agenda.items()
            if not k.startswith("_")
            and k
            not in (
                "contratoId",
                "contratoVersion",
                "resumenContrato",
                "claveOperacion",
            )
        }
        agenda.update(
            id=uuid4().hex,
            solicitudId=self.new_request(accepted=True),
            fecha=engine.stamp(engine.now() + timedelta(days=7)),
            estado="propuesto",
            pagoEstado="espera",
        )
        self.db.agendas.insert_one(to_document("agendas", agenda))
        data = copy.deepcopy(self.case.data)
        data["agendaId"] = agenda["id"]
        return data

    def pending_resolution(self):
        self.case.start()
        self.case.op(
            "empresa",
            "reclamar",
            categoria="cancelacion",
            detalle="Solicito revisar el servicio y su devolución por falta de entrega.",
        )
        iid = self.contract()["incidencias"][0]["id"]
        self.case.op(
            "profesional",
            "responder",
            incidenciaId=iid,
            detalle="Acepto revisar los antecedentes y la devolución del importe.",
        )
        self.case.op(
            "admin",
            "proponer_resolucion",
            incidenciaId=iid,
            detalle="Propuesta motivada de devolución completa del importe de prueba.",
            devolucion=150000,
        )
        return iid

    def test_alt_05_01_foreign_terms_are_private(self):
        """ALT-05-01: una empresa ajena no descarga condiciones privadas."""
        other = self.fx.client()
        self.fx.call(
            other,
            "/api/auth/login/",
            {"correo": "other@example.com", "password": self.fx.password},
        )
        r = other.get(f"/api/contratos/{self.case.id}/condiciones/")
        self.assertEqual(r.status_code, 400)
        self.assertNotIn(self.contract()["politica"]["documento"], r.content.decode())

    def test_alt_05_02_accepted_snapshot_survives_policy_change(self):
        """ALT-05-02: el acuerdo conserva el documento aceptado originalmente."""
        self.case.op(
            "profesional",
            "aceptar",
            acepto=True,
            hashTerminos=engine.terms_snapshot()["sha256"],
        )
        original = self.contract()["politica"]
        changed = {**original, "documento": "<p>Política posterior de laboratorio</p>"}
        changed["sha256"] = hashlib.sha256(changed["documento"].encode()).hexdigest()
        with patch("core.contracts.terms_snapshot", return_value=changed):
            self.assertNotEqual(
                self.case.clients["empresa"]
                .get("/api/contratos/politica/")
                .json()["sha256"],
                original["sha256"],
            )
            r = self.case.clients["empresa"].get(
                f"/api/contratos/{self.case.id}/condiciones/"
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content.decode(), original["documento"])
        self.assertEqual(hashlib.sha256(r.content).hexdigest(), original["sha256"])

    def test_alt_06_01_stale_profile_does_not_overwrite(self):
        """ALT-06-01: versión anterior se rechaza sin cambiar el perfil."""
        before = self.db.profesionales.find_one({"_id": self.case.pid})
        r = self.call(
            "profesional",
            "/api/cuenta/perfil/",
            {
                "version": before["_version"] - 1,
                "record": {"resumen": "Cambio obsoleto de prueba."},
            },
            "put",
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.db.profesionales.find_one({"_id": self.case.pid}), before)

    def test_alt_06_02_protected_fields_cannot_be_changed(self):
        """ALT-06-02: ni estado ni documentos se cambian mediante edición general."""
        before = self.db.profesionales.find_one({"_id": self.case.pid})
        for change in [{"estado": "validado"}, {"documentos": []}]:
            r = self.call(
                "profesional",
                "/api/cuenta/perfil/",
                {"version": before["_version"], "record": change},
                "put",
            )
            self.assertEqual(r.status_code, 400)
            self.assertEqual(
                self.db.profesionales.find_one({"_id": self.case.pid}), before
            )

    def test_alt_07_01_forged_pdf_never_replaces_evidence(self):
        """ALT-07-01: PDF aparente produce 400 sin sustituir respaldo."""
        before = self.db.profesionales.find_one({"_id": self.case.pid})
        r = self.profile_upload(b"%PDF-fake\narbitrary content\n%%EOF")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.profesionales.find_one({"_id": self.case.pid}), before)

    def test_alt_07_02_encrypted_pdf_never_replaces_evidence(self):
        """ALT-07-02: PDF cifrado produce 400 sin sustituir respaldo."""
        before = self.db.profesionales.find_one({"_id": self.case.pid})
        self.assertEqual(
            self.profile_upload(pdf_bytes(encrypted=True)).status_code, 400
        )
        self.assertEqual(self.db.profesionales.find_one({"_id": self.case.pid}), before)

    def test_alt_07_03_tampered_pdf_is_not_downloaded(self):
        """ALT-07-03: una huella distinta impide transmitir el archivo."""
        item = self.db.profesionales.find_one({"_id": self.case.pid})["documentos"][0]
        path = Path(self.fx.files) / (item["id"] + ".pdf")
        path.write_bytes(path.read_bytes() + b"\n%alteracion-laboratorio")
        r = self.case.clients["profesional"].get(
            f"/api/profesionales/{self.case.pid}/documentos/{item['id']}/"
        )
        self.assertEqual(r.status_code, 409)
        self.assertIn("no coincide", r.json()["error"])

    def interview_data(self):
        return {
            "version": self.db.validaciones.find_one({"_id": self.case.pid})[
                "_version"
            ],
            "resultado": "aprobada",
            "responsable": "Responsable de prueba",
            "observaciones": "Antecedentes de entrevista para el laboratorio.",
            "fecha": engine.stamp(engine.now() - timedelta(hours=1)),
            "enlace": "https://example.com/entrevista",
        }

    def test_alt_09_01_future_interview_cannot_be_approved(self):
        """ALT-09-01: no registrar un resultado antes de realizar la entrevista."""
        before = self.db.validaciones.find_one({"_id": self.case.pid})
        data = self.interview_data()
        data["fecha"] = engine.stamp(engine.now() + timedelta(days=1))
        r = self.call("admin", f"/api/profesionales/{self.case.pid}/entrevista/", data)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.validaciones.find_one({"_id": self.case.pid}), before)

    def test_alt_09_02_interview_requires_https(self):
        """ALT-09-02: un enlace HTTP se rechaza sin guardar resultado."""
        before = self.db.validaciones.find_one({"_id": self.case.pid})
        data = self.interview_data()
        data["enlace"] = "http://example.com/entrevista"
        r = self.call("admin", f"/api/profesionales/{self.case.pid}/entrevista/", data)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.validaciones.find_one({"_id": self.case.pid}), before)

    def service_record(self):
        old = self.db.servicios.find_one({"_id": self.contract()["servicioId"]})
        fields = [
            "titulo",
            "descripcion",
            "categoria",
            "duracion",
            "precio",
            "entregables",
        ]
        return old, {k: old[k] for k in fields}

    def test_alt_10_01_short_title_saves_as_correction(self):
        """ALT-10-01: guardar no publica un servicio con título insuficiente."""
        old, record = self.service_record()
        record["titulo"] = "Corto"
        r = self.call(
            "profesional",
            "/api/cuenta/servicios/",
            {"id": old["_id"], "version": old["_version"], "record": record},
            "put",
        )
        self.assertEqual(r.status_code, 200)
        saved = self.db.servicios.find_one({"_id": old["_id"]})
        self.assertFalse(saved["disponible"])
        self.assertEqual(saved["revision"]["estado"], "correccion")

    def test_alt_10_02_zero_price_saves_as_correction(self):
        """ALT-10-02: precio cero no habilita la publicación."""
        old, record = self.service_record()
        record["precio"] = 0
        r = self.call(
            "profesional",
            "/api/cuenta/servicios/",
            {"id": old["_id"], "version": old["_version"], "record": record},
            "put",
        )
        self.assertEqual(r.status_code, 200)
        saved = self.db.servicios.find_one({"_id": old["_id"]})
        self.assertFalse(saved["disponible"])
        check = next(
            x for x in saved["revision"]["comprobaciones"] if x["codigo"] == "SER-04"
        )
        self.assertEqual(check["resultado"], "pendiente")

    def test_alt_11_01_missing_reference_does_not_insert(self):
        """ALT-11-01: la referencia inexistente impide crear el registro."""
        before = self.db.servicios.count_documents({})
        r = self.call(
            "admin",
            "/api/servicios/",
            {
                "record": {
                    "id": uuid4().hex,
                    "titulo": "Servicio de prueba",
                    "profesionalId": "ausente",
                    "precio": 1000,
                    "disponible": False,
                }
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.servicios.count_documents({}), before)

    def test_alt_11_02_direct_payment_writes_are_denied(self):
        """ALT-11-02: POST y PUT genéricos no modifican pagos."""
        before = list(self.db.pagos.find().sort("_id", 1))
        for url, method in [("/api/pagos/", "post"), ("/api/pagos/ausente/", "put")]:
            self.assertEqual(
                self.call(
                    "admin", url, {"record": {}, "version": 1}, method
                ).status_code,
                403,
            )
        self.assertEqual(list(self.db.pagos.find().sort("_id", 1)), before)

    def test_alt_12_01_past_and_distant_availability_are_rejected(self):
        """ALT-12-01: horarios fuera de 180 días no reemplazan disponibilidad."""
        before = self.db.profesionales.find_one({"_id": self.case.pid})
        for days in [-1, 181]:
            r = self.call(
                "profesional",
                f"/api/profesionales/{self.case.pid}/disponibilidad/",
                {
                    "version": before["_version"],
                    "horarios": [engine.stamp(engine.now() + timedelta(days=days))],
                },
                "put",
            )
            self.assertEqual(r.status_code, 400)
            self.assertEqual(
                self.db.profesionales.find_one({"_id": self.case.pid}), before
            )

    def test_alt_12_02_equivalent_slots_are_deduplicated(self):
        """ALT-12-02: dos representaciones del mismo instante guardan un horario."""
        before = self.db.profesionales.find_one({"_id": self.case.pid})
        when = engine.now() + timedelta(days=5)
        r = self.call(
            "profesional",
            f"/api/profesionales/{self.case.pid}/disponibilidad/",
            {
                "version": before["_version"],
                "horarios": [engine.stamp(when), when.isoformat()],
            },
            "put",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            len(
                self.db.profesionales.find_one({"_id": self.case.pid})["disponibilidad"]
            ),
            1,
        )

    def test_alt_13_01_withdrawn_service_cannot_be_requested(self):
        """ALT-13-01: oferta retirada no crea una solicitud."""
        sid = self.contract()["servicioId"]
        self.db.servicios.update_one({"_id": sid}, {"$set": {"disponible": False}})
        before = self.db.solicitudes.count_documents({})
        r = self.call(
            "empresa",
            "/api/cuenta/solicitudes/",
            {
                "servicioId": sid,
                "fecha": engine.stamp(engine.now() + timedelta(days=5)),
                "claveOperacion": uuid4().hex,
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.solicitudes.count_documents({}), before)

    def test_alt_13_02_request_key_cannot_change_payload(self):
        """ALT-13-02: clave repetida con otra fecha no duplica solicitud."""
        data = {
            "servicioId": self.contract()["servicioId"],
            "fecha": engine.stamp(engine.now() + timedelta(days=5)),
            "claveOperacion": uuid4().hex,
        }
        self.assertEqual(
            self.call("empresa", "/api/cuenta/solicitudes/", data).status_code, 201
        )
        before = self.db.solicitudes.count_documents({})
        data["fecha"] = engine.stamp(engine.now() + timedelta(days=6))
        self.assertEqual(
            self.call("empresa", "/api/cuenta/solicitudes/", data).status_code, 400
        )
        self.assertEqual(self.db.solicitudes.count_documents({}), before)

    def test_alt_14_01_expired_request_is_not_answered(self):
        """ALT-14-01: la solicitud vencida no se acepta."""
        rid = self.new_request()
        self.db.solicitudes.update_one(
            {"_id": rid}, {"$set": {"expiracion": engine.now() - timedelta(seconds=1)}}
        )
        before = self.db.solicitudes.find_one({"_id": rid})
        self.assertEqual(
            self.call(
                "profesional",
                "/api/cuenta/responder/",
                {"id": rid, "estado": "aceptada"},
            ).status_code,
            409,
        )
        self.assertEqual(self.db.solicitudes.find_one({"_id": rid}), before)

    def test_alt_14_02_answered_request_is_not_changed(self):
        """ALT-14-02: segunda respuesta no reemplaza la primera."""
        rid = self.new_request(accepted=True)
        before = self.db.solicitudes.find_one({"_id": rid})
        self.assertEqual(
            self.call(
                "profesional",
                "/api/cuenta/responder/",
                {"id": rid, "estado": "rechazada"},
            ).status_code,
            409,
        )
        self.assertEqual(self.db.solicitudes.find_one({"_id": rid}), before)

    def test_alt_15_01_concurrent_bookings_have_one_winner(self):
        """ALT-15-01: dos solicitudes simultáneas no ocupan el mismo horario."""
        slot = engine.stamp((engine.now() + timedelta(days=6)).replace(microsecond=0))
        self.db.profesionales.update_one(
            {"_id": self.case.pid}, {"$addToSet": {"disponibilidad": slot}}
        )
        ids = [self.new_request(accepted=True, slot=slot) for _ in range(2)]

        def reserve(rid):
            try:
                book(self.db, self.case.users["empresa"], rid, slot, uuid4().hex)
                return "reservado"
            except (ValueError, DuplicateKeyError):
                return "rechazado"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, ids))
        self.assertEqual(sorted(results), ["rechazado", "reservado"])
        self.assertEqual(
            self.db.agendas.count_documents(
                {"profesionalId": self.case.pid, "fecha": engine.date(slot)}
            ),
            1,
        )

    def test_alt_15_02_booking_replay_keeps_same_identity(self):
        """ALT-15-02: reintento de reserva devuelve una agenda única."""
        slot = engine.stamp((engine.now() + timedelta(days=6)).replace(microsecond=0))
        self.db.profesionales.update_one(
            {"_id": self.case.pid}, {"$addToSet": {"disponibilidad": slot}}
        )
        rid = self.new_request(accepted=True, slot=slot)
        key = uuid4().hex
        first = book(self.db, self.case.users["empresa"], rid, slot, key)
        second = book(self.db, self.case.users["empresa"], rid, slot, key)
        self.assertEqual(first["_id"], second["_id"])
        self.assertEqual(self.db.agendas.count_documents({"solicitudId": rid}), 1)

    def test_alt_16_01_stage_sum_must_equal_agreed_price(self):
        """ALT-16-01: suma de etapas inconsistente no crea acuerdo."""
        data = self.fresh_proposal()
        data["hitos"][0]["neto"] -= 1
        before = self.db.contratos.count_documents({})
        r = self.call("empresa", "/api/contratos/", data)
        self.assertEqual(r.status_code, 400)
        self.assertIn("suma", r.json()["error"])
        self.assertEqual(self.db.contratos.count_documents({}), before)

    def test_alt_16_02_naive_deadline_is_rejected(self):
        """ALT-16-02: vence requiere zona horaria explícita."""
        data = self.fresh_proposal()
        data["hitos"][0]["vence"] = (
            (engine.now() + timedelta(days=10)).replace(tzinfo=None).isoformat()
        )
        before = self.db.contratos.count_documents({})
        r = self.call("empresa", "/api/contratos/", data)
        self.assertEqual(r.status_code, 400)
        self.assertIn("zona", r.json()["error"])
        self.assertEqual(self.db.contratos.count_documents({}), before)

    def test_alt_17_02_acceptance_requires_consent_and_hash(self):
        """ALT-17-02: consentimiento ausente o hash distinto no acepta."""
        self.assert_rejected(
            "profesional",
            "aceptar",
            acepto=False,
            hashTerminos=engine.terms_snapshot()["sha256"],
        )
        self.assert_rejected(
            "profesional", "aceptar", acepto=True, hashTerminos="obsoleto"
        )

    def test_alt_18_01_funding_requires_both_acceptances(self):
        """ALT-18-01: no ingresar dinero de prueba sin ambas aceptaciones."""
        self.assert_rejected("empresa", "financiar")
        self.assertEqual(self.contract()["movimientos"], [])

    def test_alt_18_02_funding_replay_has_one_movement(self):
        """ALT-18-02: reintento financiero no duplica ingreso."""
        self.case.op(
            "profesional",
            "aceptar",
            acepto=True,
            hashTerminos=engine.terms_snapshot()["sha256"],
        )
        data = {
            "accion": "financiar",
            "hitoId": self.case.hid,
            "version": self.contract()["_version"],
            "claveOperacion": uuid4().hex,
        }
        for _ in range(2):
            self.assertEqual(
                self.call(
                    "empresa", f"/api/contratos/{self.case.id}/", data
                ).status_code,
                200,
            )
        self.assertEqual(len(self.contract()["movimientos"]), 1)
        self.assertEqual(self.contract()["hitos"][0]["financiado"], 150000)

    def test_alt_19_02_start_requires_confirmed_inputs(self):
        """ALT-19-02: financiación sola no habilita inicio."""
        self.case.op(
            "profesional",
            "aceptar",
            acepto=True,
            hashTerminos=engine.terms_snapshot()["sha256"],
        )
        self.case.op("empresa", "financiar")
        self.assert_rejected("profesional", "iniciar")
        self.assertEqual(self.contract()["hitos"][0]["estado"], "financiado")

    def test_alt_20_02_acceptance_requires_a_delivery(self):
        """ALT-20-02: etapa en ejecución no se acepta como entregada."""
        self.case.start()
        self.assert_rejected("empresa", "aceptar_entrega")
        self.assertEqual(self.contract()["hitos"][0]["estado"], "en_ejecucion")

    def proposed_change(self):
        self.case.start()
        self.case.op(
            "profesional",
            "proponer_cambio",
            vence=engine.stamp(engine.now() + timedelta(days=12)),
            detalle="Cambio solicitado con antecedentes del laboratorio.",
        )
        return self.contract()["cambios"][0]["id"]

    def test_alt_21_01_author_cannot_accept_own_change(self):
        """ALT-21-01: la contraparte debe aceptar el cambio de fecha."""
        cid = self.proposed_change()
        self.assert_rejected("profesional", "aceptar_cambio", cambioId=cid)

    def test_alt_21_02_only_one_pending_change_per_stage(self):
        """ALT-21-02: no acumular propuestas pendientes de una etapa."""
        self.proposed_change()
        self.assert_rejected(
            "empresa",
            "proponer_cambio",
            vence=engine.stamp(engine.now() + timedelta(days=13)),
            detalle="Segunda propuesta que aún no corresponde admitir.",
        )
        self.assertEqual(len(self.contract()["cambios"]), 1)

    def open_dispute(self):
        self.case.start()
        self.case.op(
            "empresa",
            "reclamar",
            categoria="entrega",
            detalle="Incidencia de prueba por falta de conformidad con la entrega.",
        )

    def test_alt_22_01_duplicate_dispute_is_rejected(self):
        """ALT-22-01: una etapa no acumula incidencias abiertas duplicadas."""
        self.open_dispute()
        self.assert_rejected(
            "empresa",
            "reclamar",
            categoria="otro",
            detalle="Una segunda incidencia no debe reemplazar la primera.",
        )
        self.assertEqual(len(self.contract()["incidencias"]), 1)

    def test_alt_22_02_dispute_blocks_release_even_after_acceptance(self):
        """ALT-22-02: liquidación bloqueada por incidencia no resuelta."""
        self.case.start()
        self.case.op(
            "profesional",
            "entregar",
            detalle="Entrega completa de laboratorio para revisión de la empresa.",
        )
        self.case.op("empresa", "aceptar_entrega")
        self.case.op(
            "empresa",
            "reclamar",
            categoria="entrega",
            detalle="Incidencia abierta antes de liberar los fondos de prueba.",
        )
        self.assert_rejected("admin", "liquidar")
        self.assertEqual(
            engine.finances(self.contract()["hitos"][0])["retenido"], 150000
        )

    def test_alt_23_01_refund_requires_both_consents(self):
        """ALT-23-01: un solo consentimiento no habilita reembolso."""
        iid = self.pending_resolution()
        self.case.op("empresa", "aceptar_resolucion", incidenciaId=iid, acepto=True)
        self.assert_rejected("admin", "devolver")
        self.assertEqual(len(self.contract()["movimientos"]), 1)

    def test_alt_23_02_resolution_cannot_exceed_held_funds(self):
        """ALT-23-02: no resolver devolución por encima de saldo retenido."""
        self.open_dispute()
        iid = self.contract()["incidencias"][0]["id"]
        self.case.op(
            "profesional",
            "responder",
            incidenciaId=iid,
            detalle="Aporto antecedentes para revisar esta incidencia de prueba.",
        )
        self.assert_rejected(
            "admin",
            "proponer_resolucion",
            incidenciaId=iid,
            detalle="Una propuesta no puede devolver más dinero que el retenido.",
            devolucion=150001,
        )

    def test_alt_24_01_reconsideration_requires_another_reviewer(self):
        """ALT-24-01: mismo administrador no resuelve reconsideración."""
        iid = self.pending_resolution()
        self.case.op(
            "empresa",
            "reconsiderar",
            incidenciaId=iid,
            detalle="Solicito segunda revisión por antecedentes no considerados.",
        )
        self.assert_rejected(
            "admin",
            "proponer_resolucion",
            incidenciaId=iid,
            detalle="El primer revisor no puede aprobar su propia reconsideración.",
        )

    def test_alt_24_02_reconsideration_requires_reason(self):
        """ALT-24-02: motivo corto no abre reconsideración."""
        iid = self.pending_resolution()
        self.assert_rejected(
            "empresa", "reconsiderar", incidenciaId=iid, detalle="corto"
        )

    def test_alt_25_01_pending_delivery_cannot_be_released(self):
        """ALT-25-01: una entrega en revisión no permite liquidación."""
        self.case.start()
        self.case.op(
            "profesional",
            "entregar",
            detalle="Entrega de prueba aún pendiente de aceptación de la empresa.",
        )
        self.assert_rejected("admin", "liquidar")
        self.assertEqual(
            engine.finances(self.contract()["hitos"][0])["retenido"], 150000
        )

    def test_alt_26_02_delay_alert_never_debits_funds(self):
        """ALT-26-02: vencimiento emite aviso sin descontar fondos."""
        self.case.start()
        before = self.contract()
        later = engine.date(before["hitos"][0]["vence"]) + timedelta(hours=72)
        with patch("core.contracts.now", return_value=later):
            engine.monitor(self.db)
            self.assertGreater(
                engine.penalty(self.contract()["hitos"][0])["estimada"], 0
            )
        after = self.contract()
        self.assertTrue(any(a["clave"].startswith("retraso:") for a in after["avisos"]))
        self.assertEqual(after["movimientos"], before["movimientos"])
        self.assertEqual(engine.finances(after["hitos"][0])["retenido"], 150000)

    def legacy_agenda(self, state):
        a = self.db.agendas.find_one({"_id": self.case.aid})
        a = {
            k: v
            for k, v in a.items()
            if not k.startswith("_")
            and k
            not in (
                "contratoId",
                "contratoVersion",
                "contratoRequerido",
                "resumenContrato",
                "claveOperacion",
                "evaluacion",
            )
        }
        a.update(
            id=uuid4().hex,
            solicitudId=self.new_request(accepted=True),
            fecha=engine.stamp(engine.now() + timedelta(days=8)),
            estado=state,
            pagoEstado="finalizado" if state == "finalizado" else "espera",
        )
        self.db.agendas.insert_one(to_document("agendas", a))
        return a["id"]

    def test_alt_27_01_early_legacy_rating_is_rejected(self):
        """ALT-27-01: no evaluar seguimiento anterior sin finalizar."""
        aid = self.legacy_agenda("confirmado")
        before = self.db.agendas.find_one({"_id": aid})
        r = self.call(
            "empresa",
            "/api/operaciones/",
            {
                "agendaId": aid,
                "version": 1,
                "accion": "evaluar",
                "evaluacion": {
                    "nota": 5,
                    "comentario": "Evaluación anticipada de laboratorio.",
                },
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.agendas.find_one({"_id": aid}), before)

    def test_alt_27_02_rating_outside_scale_is_rejected(self):
        """ALT-27-02: nota 6 no persiste aunque el servicio haya finalizado."""
        aid = self.legacy_agenda("finalizado")
        before = self.db.agendas.find_one({"_id": aid})
        r = self.call(
            "empresa",
            "/api/operaciones/",
            {
                "agendaId": aid,
                "version": 1,
                "accion": "evaluar",
                "evaluacion": {
                    "nota": 6,
                    "comentario": "Fuera de escala de uno a cinco.",
                },
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.agendas.find_one({"_id": aid}), before)

    def test_alt_28_01_foreign_attention_is_not_visible_or_mutable(self):
        """ALT-28-01: la petición ajena no se lista ni reabre."""
        r = self.call(
            "empresa",
            "/api/atencion/",
            {
                "tipo": "consulta",
                "detalle": "Consulta privada del laboratorio sobre mi cuenta.",
            },
        )
        item = r.json()["records"][0]
        before = self.db.atencion.find_one({"_id": item["id"]})
        other = self.fx.client()
        self.fx.call(
            other,
            "/api/auth/login/",
            {"correo": "other@example.com", "password": self.fx.password},
        )
        self.assertEqual(other.get("/api/atencion/").json()["records"], [])
        r = self.fx.call(
            other,
            "/api/atencion/",
            {
                "id": item["id"],
                "version": item["version"],
                "accion": "reabrir",
                "detalle": "No corresponde acceder a una petición ajena.",
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.atencion.find_one({"_id": item["id"]}), before)

    def test_alt_28_02_unknown_attention_type_is_not_inserted(self):
        """ALT-28-02: categoría inválida no crea atención."""
        before = self.db.atencion.count_documents({})
        r = self.call(
            "empresa",
            "/api/atencion/",
            {
                "tipo": "arbitrario",
                "detalle": "Texto válido pero tipo de solicitud no reconocido.",
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.atencion.count_documents({}), before)

    def restriction(self):
        return self.call(
            "admin",
            "/api/contratos/cuentas/",
            {
                "usuarioId": self.case.users["empresa"]["_id"],
                "version": 0,
                "urgente": True,
                "detalle": "Restricción preventiva del laboratorio para verificar el acceso conservado.",
            },
        )

    def test_alt_29_01_restriction_preserves_account_and_existing_agreements(self):
        """ALT-29-01: restricción bloquea nuevas compras, no reclamaciones."""
        self.assertEqual(self.restriction().status_code, 200)
        before = self.db.solicitudes.count_documents({})
        r = self.call(
            "empresa",
            "/api/cuenta/solicitudes/",
            {
                "servicioId": self.contract()["servicioId"],
                "fecha": engine.stamp(engine.now() + timedelta(days=5)),
                "claveOperacion": uuid4().hex,
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("restricción", r.json()["error"])
        self.assertEqual(self.db.solicitudes.count_documents({}), before)
        for url in ["/api/cuenta/", "/api/contratos/"]:
            self.assertEqual(self.case.clients["empresa"].get(url).status_code, 200)
        self.assertEqual(
            self.call(
                "empresa",
                "/api/atencion/",
                {
                    "tipo": "cuenta",
                    "detalle": "Solicito revisión y conservo mis derechos de consulta.",
                },
            ).status_code,
            200,
        )
        client = self.fx.client()
        self.assertEqual(
            self.fx.call(
                client,
                "/api/auth/login/",
                {"correo": "company@example.com", "password": self.fx.password},
            ).status_code,
            200,
        )

    def test_alt_29_02_stale_control_version_cannot_replace_restriction(self):
        """ALT-29-02: versión obsoleta no reemplaza restricción vigente."""
        self.assertEqual(self.restriction().status_code, 200)
        before = self.db.usuarios.find_one({"_id": self.case.users["empresa"]["_id"]})
        self.assertEqual(self.restriction().status_code, 400)
        self.assertEqual(self.db.usuarios.find_one({"_id": before["_id"]}), before)

    def test_alt_30_01_company_cannot_configure_operator(self):
        """ALT-30-01: empresa no consulta ni edita operador."""
        before = list(self.db.configuracion.find())
        self.assertEqual(
            self.case.clients["empresa"].get("/api/contratos/operador/").status_code,
            403,
        )
        self.assertEqual(
            self.call("empresa", "/api/contratos/operador/", {}).status_code, 403
        )
        self.assertEqual(list(self.db.configuracion.find()), before)

    def test_alt_31_01_impossible_holiday_is_not_inserted(self):
        """ALT-31-01: fecha imposible no entra al calendario."""
        before = self.db.feriados.count_documents({})
        r = self.call(
            "admin",
            "/api/contratos/feriados/",
            {"fecha": "2026-02-30", "nombre": "Fecha imposible de prueba"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.db.feriados.count_documents({}), before)

    def test_alt_31_02_reprojection_does_not_duplicate_events(self):
        """ALT-31-02: la misma proyección conserva los eventos y saldos."""
        self.case.start()
        contract = self.contract()
        before_events = list(
            self.db.historial.find({"contratoId": self.case.id}).sort("_id", 1)
        )
        before_payment = self.db.pagos.find_one({"agendaId": self.case.aid})
        engine.project(self.db, contract)
        engine.project(self.db, contract)
        self.assertEqual(
            list(self.db.historial.find({"contratoId": self.case.id}).sort("_id", 1)),
            before_events,
        )
        self.assertEqual(
            self.db.pagos.find_one({"agendaId": self.case.aid}), before_payment
        )
