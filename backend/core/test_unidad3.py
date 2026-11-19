"""Regresión de alternativas de negocio y límites de seguridad de la Unidad 3."""
import os
from unittest import TestCase, skipUnless
from . import test_contracts as fixtures


@skipUnless(os.getenv('SKILLY_INTEGRATION') == '1', 'Requiere MongoDB temporal.')
class Unit3IntegrationTests(TestCase):
    def setUp(self):
        self.case = fixtures.ContractIntegrationTests()
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()

    def test_rejected_proposal_has_no_financing(self):
        case = self.case
        case.op('profesional', 'rechazar_acuerdo', detalle='El alcance propuesto no corresponde al servicio ofrecido.')
        record = case.db.contratos.find_one({'_id': case.id})
        self.assertTrue(all(stage['estado'] == 'cancelado' for stage in record['hitos']))
        self.assertEqual(record['movimientos'], [])
        case.op('empresa', 'financiar', 400)

    def test_correction_cycle_preserves_both_deliveries(self):
        case = self.case
        case.start()
        case.op('profesional', 'entregar', detalle='Primera entrega del prototipo para revisión de la empresa.')
        case.op('empresa', 'observar', detalle='Corregir el contraste de los controles del prototipo.')
        case.op('profesional', 'respuesta_correccion', detalle='Se revisará el contraste manteniendo el alcance acordado.')
        case.op('profesional', 'entregar', detalle='Segunda entrega con el contraste de los controles corregido.')
        case.op('empresa', 'aceptar_entrega')
        record = case.db.contratos.find_one({'_id': case.id})
        self.assertEqual(len(record['hitos'][0]['entregas']), 2)
        self.assertEqual(record['hitos'][0]['estado'], 'aceptado')
        self.assertEqual(sum(m['tipo'] == 'ingreso' for m in record['movimientos']), 1)

    def test_company_cannot_register_professional_progress(self):
        case = self.case
        case.start()
        before = case.db.contratos.find_one({'_id': case.id})['_version']
        case.op('empresa', 'avance', 400, detalle='Una empresa no puede registrar avances del profesional.')
        self.assertEqual(case.db.contratos.find_one({'_id': case.id})['_version'], before)

    def test_operator_details_do_not_enable_real_payments(self):
        case = self.case
        response = case.fixture.call(case.clients['admin'], '/api/contratos/operador/', {
            'razonSocial': 'Operador de demostración de laboratorio', 'rut': 'No verificado',
            'domicilio': 'Dirección de demostración del laboratorio', 'correo': 'operador@example.invalid',
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()['pagosRealesHabilitados'])
        self.assertFalse(response.json()['record']['verificado'])
        self.assertEqual(case.clients['empresa'].get('/api/contratos/operador/').status_code, 403)

    def test_failed_login_attempts_are_limited(self):
        case = self.case
        client = case.fixture.client()
        statuses = []
        for _ in range(11):
            response = case.fixture.call(client, '/api/auth/login/', {
                'correo': 'fallos@example.invalid', 'password': 'Clave-incorrecta-2026!',
            })
            statuses.append(response.status_code)
        self.assertEqual(statuses[:10], [401] * 10)
        self.assertEqual(statuses[-1], 429)
