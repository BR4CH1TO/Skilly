import os
from datetime import datetime, timezone, timedelta
from unittest import TestCase, skipUnless
from unittest.mock import patch
from uuid import uuid4
from . import contracts as e
from .test_integration import RealIntegrationTests


class ContractRulesTests(TestCase):
    def test_grace_full_periods_and_cap(self):
        due=datetime(2026,10,1,tzinfo=timezone.utc);h={'neto':100000,'vence':e.stamp(due)}
        for hours,result in [(24,0),(47,0),(48,1000),(72,2000),(600,10000)]:
            self.assertEqual(e.penalty(h,due+timedelta(hours=hours))['estimada'],result)
    def test_fractional_pesos_round_down_after_multiplication(self):
        due=datetime(2026,10,1,tzinfo=timezone.utc);h={'neto':155,'vence':e.stamp(due)}
        self.assertEqual(e.penalty(h,due+timedelta(hours=72))['estimada'],3)
    def test_agreed_exclusions_not_counted(self):
        due=datetime(2026,10,1,tzinfo=timezone.utc);h={'neto':100000,'vence':e.stamp(due),'suspensiones':[{'desde':e.stamp(due),'hasta':e.stamp(due+timedelta(hours=24))}]}
        self.assertEqual(e.penalty(h,due+timedelta(hours=72))['estimada'],1000)
    def test_commission_excludes_service_refund(self):
        f=e.finances({'neto':100000,'estado':'aceptado','financiado':100000,'devolucionServicio':20000,'compensacion':2000})
        self.assertEqual(f['comision'],8000);self.assertEqual(f['netoProfesional'],70000);self.assertEqual(f['devolucionTotal'],22000)
    def test_no_debit_from_estimate(self):
        self.assertEqual(e.finances({'neto':100000,'estado':'en_ejecucion','financiado':100000})['retenido'],100000)


@skipUnless(os.getenv('SKILLY_INTEGRATION')=='1','Activa SKILLY_INTEGRATION=1 para MongoDB temporal.')
class ContractIntegrationTests(TestCase):
    def setUp(self):
        self.fixture=RealIntegrationTests();self.fixture.setUp();self.addCleanup(self.fixture.cleanup)
        # Reutiliza usuarios y servicios completamente validados; los datos son aislados.
        self.fixture.test_complete_flow_permissions_and_recovery()
        self.db=self.fixture.db;self.clients={};self.users={}
        for role,email in [('empresa','company@example.com'),('profesional','pro@example.com'),('admin','admin@example.com')]:
            self.clients[role]=self.fixture.client();self.assertEqual(self.fixture.call(self.clients[role],'/api/auth/login/',{'correo':email,'password':self.fixture.password}).status_code,200);self.users[role]=self.db.usuarios.find_one({'correo':email})
        a=self.db.agendas.find_one({'estado':'propuesto'});self.aid=a['_id'];self.pid=a['profesionalId']
        policy=e.terms_snapshot();self.data={'agendaId':self.aid,'acepto':True,'versionTerminos':policy['version'],'hashTerminos':policy['sha256'],'alcance':'Diseño de un prototipo completo.','entregables':'Interfaz, archivos y documentación.','exclusiones':'No incluye desarrollo de software.','insumos':'La empresa aporta textos e imágenes.','propiedad':'Licencia de uso del resultado según acuerdo.','hitos':[{'nombre':'Entrega final','neto':a['precioAcordado'],'vence':e.stamp(e.now()+timedelta(days=10)),'criterios':'Prototipo accesible y con las pantallas acordadas.'}]}
        r=self.fixture.call(self.clients['empresa'],'/api/contratos/',self.data);self.assertEqual(r.status_code,201,r.content);self.id=r.json()['record']['id'];self.hid=r.json()['record']['hitos'][0]['id']
    def op(self,role,action,expected=200,**extra):
        c=self.db.contratos.find_one({'_id':self.id})
        data={'accion':action,'version':c['_version'],'claveOperacion':uuid4().hex,'hitoId':self.hid,**extra}
        r=self.fixture.call(self.clients[role],f'/api/contratos/{self.id}/',data)
        self.assertEqual(r.status_code,expected,r.content)
        return r.json().get('record')
    def start(self):
        self.op('profesional','aceptar',acepto=True,hashTerminos=e.terms_snapshot()['sha256'])
        self.op('empresa','financiar');self.op('empresa','insumos',detalle='Textos y archivos puestos a disposición.');self.op('profesional','iniciar')
    def test_accept_fund_deliver_release_and_replay(self):
        self.op('empresa','financiar',400)
        self.start();self.op('empresa','aceptar_entrega',400);self.op('profesional','entregar',detalle='Prototipo completo entregado con evidencia verificable.')
        self.op('admin','liquidar',400);self.op('empresa','aceptar_entrega')
        c=self.db.contratos.find_one({'_id':self.id});data={'accion':'liquidar','hitoId':self.hid,'version':c['_version'],'claveOperacion':uuid4().hex}
        for _ in range(2): self.assertEqual(self.fixture.call(self.clients['admin'],f'/api/contratos/{self.id}/',data).status_code,200)
        c=self.db.contratos.find_one({'_id':self.id});self.assertEqual(c['estado'],'cerrado');f=e.finances(c['hitos'][0]);self.assertEqual(f['retenido'],0)
        self.assertEqual(len(c['movimientos']),3);self.assertEqual(c['hitos'][0]['comisionCobrada'],15000)
        self.assertEqual(self.db.agendas.find_one({'_id':self.aid})['estado'],'finalizado')
        self.op('empresa','evaluar',nota=5,detalle='Servicio de prueba satisfactorio.')
    def test_dispute_requires_both_consents_before_refund(self):
        self.start();self.op('empresa','reclamar',categoria='cancelacion',detalle='Solicito cancelar el trabajo y revisar el avance útil entregado.')
        c=self.db.contratos.find_one({'_id':self.id});iid=c['incidencias'][0]['id']
        self.op('admin','proponer_resolucion',400,incidenciaId=iid,detalle='Devolución completa por falta de entrega.',devolucion=150000)
        self.op('profesional','responder',incidenciaId=iid,detalle='Acepto que no hay trabajo útil entregado y solicito devolver el importe.')
        self.op('admin','proponer_resolucion',incidenciaId=iid,detalle='Devolución completa, respaldada por las respuestas de ambas partes.',devolucion=150000)
        self.op('admin','devolver',400);self.op('empresa','aceptar_resolucion',incidenciaId=iid,acepto=True);self.op('admin','devolver',400)
        self.op('profesional','aceptar_resolucion',incidenciaId=iid,acepto=True);self.op('admin','devolver')
        c=self.db.contratos.find_one({'_id':self.id});self.assertEqual(c['hitos'][0]['reembolsado'],150000);self.assertEqual(e.finances(c['hitos'][0])['retenido'],0)
    def test_change_requires_counterparty_and_foreign_is_denied(self):
        self.start();old=self.db.contratos.find_one({'_id':self.id})['hitos'][0]['vence']
        self.op('profesional','proponer_cambio',vence=e.stamp(e.now()+timedelta(days=12)),detalle='Se propone ampliar la entrega por un cambio solicitado.')
        c=self.db.contratos.find_one({'_id':self.id});change=c['cambios'][0]['id'];self.assertEqual(c['hitos'][0]['vence'],old)
        self.op('profesional','aceptar_cambio',400,cambioId=change);self.op('empresa','aceptar_cambio',cambioId=change)
        self.assertNotEqual(self.db.contratos.find_one({'_id':self.id})['hitos'][0]['vence'],old)
        other=self.fixture.client();self.fixture.call(other,'/api/auth/login/',{'correo':'other@example.com','password':self.fixture.password})
        self.assertEqual(other.get(f'/api/contratos/{self.id}/').status_code,400)
        self.assertEqual(other.get(f'/api/contratos/{self.id}/condiciones/').status_code,400)
    def test_stale_and_failed_projection_recover(self):
        self.op('profesional','aceptar',acepto=True,hashTerminos=e.terms_snapshot()['sha256'])
        c=self.db.contratos.find_one({'_id':self.id});data={'accion':'financiar','hitoId':self.hid,'version':c['_version'],'claveOperacion':uuid4().hex}
        with patch('core.contracts.project',side_effect=RuntimeError('interruption')):
            with self.assertRaises(RuntimeError):e.mutate(self.db,self.users['empresa'],self.id,data)
        from .contract_views import reconcile
        reconcile(self.db)
        c=self.db.contratos.find_one({'_id':self.id});self.assertNotIn('_syncPendiente',c);self.assertEqual(c['hitos'][0]['financiado'],150000)
        self.assertEqual(self.fixture.call(self.clients['empresa'],f'/api/contratos/{self.id}/',{**data,'claveOperacion':uuid4().hex}).status_code,400)
    def test_silence_reminds_without_acceptance(self):
        self.start();self.op('profesional','entregar',detalle='Entrega completa para revisión del cliente.')
        later=e.now()+timedelta(days=15)
        with patch('core.contracts.now',return_value=later):
            e.monitor(self.db);e.monitor(self.db)
        c=self.db.contratos.find_one({'_id':self.id});self.assertEqual(c['hitos'][0]['estado'],'en_revision');self.assertEqual(len(c['incidencias']),1);self.assertTrue(c['avisos']);self.assertEqual(len(c['movimientos']),1)
    def test_private_evidence_access_and_integrity(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .test_delivery import pdf_bytes
        c=self.db.contratos.find_one({'_id':self.id});client=self.clients['empresa'];token=client.get('/api/auth/sesion/').json()['csrfToken']
        r=client.post(f'/api/contratos/{self.id}/archivos/',data={'version':c['_version'],'hitoId':self.hid,'claveOperacion':uuid4().hex,'archivo':SimpleUploadedFile('evidencia.pdf',pdf_bytes())},HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code,201,r.content);fid=r.json()['record']['archivos'][0]['id']
        url=f'/api/contratos/{self.id}/archivos/{fid}/';response=self.clients['profesional'].get(url);self.assertEqual(response.status_code,200);response.close()
        self.assertEqual(self.fixture.client().get(url).status_code,401)
        other=self.fixture.client();self.fixture.call(other,'/api/auth/login/',{'correo':'other@example.com','password':self.fixture.password})
        self.assertEqual(other.get(url).status_code,400)
    def test_reconsideration_requires_different_reviewer(self):
        self.start();self.op('empresa','reclamar',categoria='entrega',detalle='Solicito revisar el servicio por falta de entregables acordados.')
        iid=self.db.contratos.find_one({'_id':self.id})['incidencias'][0]['id']
        self.op('profesional','responder',incidenciaId=iid,detalle='Aporto mis antecedentes y propongo revisar el expediente.')
        self.op('admin','proponer_resolucion',incidenciaId=iid,detalle='Propuesta inicial fundamentada para resolver esta incidencia.')
        self.op('empresa','reconsiderar',incidenciaId=iid,detalle='Solicito una segunda revisión por antecedentes que no fueron considerados.')
        self.op('admin','proponer_resolucion',400,incidenciaId=iid,detalle='El mismo revisor no puede resolver esta reconsideración.')
    def test_restriction_preserves_login_and_existing_agreements(self):
        company=self.users['empresa'];r=self.fixture.call(self.clients['admin'],'/api/contratos/cuentas/',{'usuarioId':company['_id'],'version':0,'urgente':True,'detalle':'Medida preventiva de prueba por evidencia de suplantación de cuenta.'})
        self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(self.clients['empresa'].get('/api/contratos/').status_code,200)
        self.assertEqual(self.clients['empresa'].get('/api/cuenta/').status_code,200)
        r=self.fixture.call(self.clients['empresa'],'/api/cuenta/solicitudes/',{'servicioId':self.data['agendaId']})
        self.assertEqual(r.status_code,400)
        self.assertIn('restricción',r.json()['error'])
        r=self.fixture.call(self.clients['empresa'],'/api/atencion/',{'tipo':'cuenta','detalle':'Solicito revisión de la restricción y aporto antecedentes verificables.'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.clients['empresa'].get('/api/contratos/cuentas/').status_code,403)
    def test_privacy_requests_remain_private(self):
        r=self.fixture.call(self.clients['empresa'],'/api/atencion/',{'tipo':'supresion','detalle':'Solicito revisar la eliminación de mis datos personales.'});self.assertEqual(r.status_code,200)
        item=r.json()['records'][0]
        other=self.fixture.client();self.fixture.call(other,'/api/auth/login/',{'correo':'other@example.com','password':self.fixture.password})
        self.assertEqual(other.get('/api/atencion/').json()['records'],[])
        response=self.fixture.call(other,'/api/atencion/',{'id':item['id'],'version':item['version'],'accion':'reabrir','detalle':'Intento de acceder a una solicitud ajena.'});self.assertEqual(response.status_code,400)
        response=self.fixture.call(self.clients['admin'],'/api/atencion/',{'id':item['id'],'version':item['version'],'accion':'responder','detalle':'Se revisarán los datos sujetos a conservación y los que pueden suprimirse.'});self.assertEqual(response.status_code,200)
    def test_holidays_skip_weekends_and_configured_dates(self):
        self.db.feriados.insert_one({'_id':'2026-11-02','nombre':'Feriado de prueba'})
        due=e.business_due(self.db,'2026-10-30T15:00:00Z',1)
        self.assertEqual(e.date(due).astimezone(e.ZONE).date().isoformat(),'2026-11-03')
    def test_new_flow_cannot_use_legacy_payment(self):
        a=self.db.agendas.find_one({'_id':self.aid});r=self.fixture.call(self.clients['profesional'],'/api/operaciones/',{'accion':'confirmar','agendaId':self.aid,'version':a['_version']})
        self.assertEqual(r.status_code,400)
        self.assertIn('acuerdo',r.json()['error'])
