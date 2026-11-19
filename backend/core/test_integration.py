"""Pruebas reales optativas: SKILLY_INTEGRATION=1 python manage.py test core."""
import os
import json
from datetime import datetime, timezone, timedelta
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch
from contextlib import ExitStack
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from pymongo import MongoClient
from django.conf import settings
from django.test import Client, override_settings
from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from .storage import ensure_indexes,to_document
from .access import setup_access, COOKIE
from .test_delivery import pdf_bytes


@skipUnless(os.getenv('SKILLY_INTEGRATION')=='1','Activa SKILLY_INTEGRATION=1 para pruebas con MongoDB temporal.')
class RealIntegrationTests(TestCase):
    def setUp(self):
        config=settings.DATABASES['default']
        self.mongo=MongoClient(config['HOST'],**config['OPTIONS']);self.name='skilly_integration_'+uuid4().hex;self.db=self.mongo[self.name]
        self.stack=ExitStack();self.addCleanup(self.cleanup)
        ensure_indexes(self.db);setup_access(self.db)
        for module in ['access','auth_views','views','portal_views','workflow_views','business_views','contract_views']:
            self.stack.enter_context(patch('core.'+module+'.database',return_value=self.db))
        self.files=self.stack.enter_context(TemporaryDirectory(prefix='skilly-docs-integration-'))
        self.stack.enter_context(override_settings(PRIVATE_DOCUMENT_ROOT=self.files))
        self.password='Entrega-Skilly-Segura-2026!'
    def cleanup(self):
        self.stack.close();self.mongo.drop_database(self.name);self.mongo.close()
    def client(self):return Client(enforce_csrf_checks=True,HTTP_HOST='localhost')
    def call(self,client,path,data=None,method='post'):
        token=client.get('/api/auth/sesion/').json()['csrfToken']
        return getattr(client,method)(path,data=json.dumps(data or {}),content_type='application/json',HTTP_X_CSRFTOKEN=token)
    def signup(self,email,role):
        from .contracts import terms_snapshot
        c=self.client();r=self.call(c,'/api/auth/registro/',{'nombre':'Cuenta de prueba','correo':email,'password':self.password,'rol':role,'aceptoTerminos':True,'mayorEdad':True,'hashTerminos':terms_snapshot()['sha256']})
        self.assertEqual(r.status_code,201,r.content);return c
    def test_complete_flow_permissions_and_recovery(self):
        company=self.signup('company@example.com','empresa');other=self.signup('other@example.com','empresa');pro=self.signup('pro@example.com','profesional')
        profile=pro.get('/api/cuenta/').json();pid=profile['profile']['id']
        slot=(datetime.now(timezone.utc)+timedelta(days=2)).replace(minute=0,second=0,microsecond=0).isoformat()
        response=self.call(pro,'/api/cuenta/perfil/',{'version':profile['version'],'record':{'profesion':'Diseñador de productos','ubicacion':'Santiago, Chile','resumen':'Experiencia en diseño de productos digitales y servicios para empresas.','habilidades':['Diseño','Investigación'],'disponibilidad':[slot]}},'put')
        self.assertEqual(response.status_code,200,response.content)
        for kind in ['cv','formacion']:
            profile=pro.get('/api/cuenta/').json();token=pro.get('/api/auth/sesion/').json()['csrfToken']
            r=pro.post(f'/api/profesionales/{pid}/documentos/',data={'version':profile['version'],'tipo':kind,'archivo':SimpleUploadedFile(kind+'.pdf',pdf_bytes())},HTTP_X_CSRFTOKEN=token)
            self.assertEqual(r.status_code,201,r.content)
        self.db.usuarios.insert_one({'_id':'admin','nombre':'Admin de prueba','correo':'admin@example.com','rol':'admin','activo':True,'passwordHash':make_password(self.password)})
        admin=self.client();self.assertEqual(self.call(admin,'/api/auth/login/',{'correo':'admin@example.com','password':self.password}).status_code,200)
        v=self.db.validaciones.find_one({'_id':pid})
        r=self.call(admin,f'/api/profesionales/{pid}/entrevista/',{'version':v['_version'],'resultado':'aprobada','responsable':'Equipo de prueba','observaciones':'Entrevista de demostración de integración, aprobada.','fecha':(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),'enlace':'https://example.com/entrevista'})
        self.assertEqual(r.status_code,200,r.content)
        r=self.call(pro,'/api/cuenta/servicios/',{'record':{'titulo':'Diseño de interfaz profesional','categoria':'Diseño','descripcion':'Diseño y prototipado de una interfaz digital con pruebas de usabilidad.','precio':150000,'duracion':'Dos semanas','entregables':'Prototipo navegable y guía de componentes.'}})
        self.assertEqual(r.status_code,201,r.content);sid=r.json()['record']['id'];self.assertTrue(r.json()['record']['disponible'])
        self.assertEqual(self.client().get('/api/estado/').status_code,401)
        self.assertEqual(company.get('/api/estado/').status_code,403)
        request_data={'servicioId':sid,'fecha':slot,'claveOperacion':uuid4().hex}
        r=self.call(company,'/api/cuenta/solicitudes/',request_data);self.assertEqual(r.status_code,201,r.content);rid=r.json()['record']['id']
        self.assertEqual(self.call(company,'/api/cuenta/solicitudes/',request_data).status_code,200)
        self.assertEqual(len(other.get('/api/cuenta/').json()['solicitudes']),0)
        self.assertEqual(self.call(pro,'/api/cuenta/responder/',{'id':rid,'estado':'aceptada'}).status_code,200)
        booking={'accion':'agendar','solicitudId':rid,'fecha':slot,'claveOperacion':uuid4().hex}
        r=self.call(company,'/api/operaciones/',booking);self.assertEqual(r.status_code,200,r.content);aid=r.json()['record']['id']
        self.assertEqual(self.call(company,'/api/operaciones/',booking).json()['record']['id'],aid)
        self.assertEqual(self.db.agendas.count_documents({'solicitudId':rid}),1)
        agenda=self.db.agendas.find_one({'_id':aid})
        self.assertEqual(self.call(other,'/api/operaciones/',{'agendaId':aid,'version':agenda['_version'],'accion':'cancelar'}).status_code,400)
        self.assertEqual(self.call(company,'/api/operaciones/',{'agendaId':aid,'version':agenda['_version'],'accion':'pagar'}).status_code,400)
        # Compatibilidad de expedientes anteriores al flujo contractual. Los nuevos se prueban en test_contracts.
        self.db.agendas.update_one({'_id':aid},{'$unset':{'contratoRequerido':''}})
        for client,action in [(pro,'confirmar'),(pro,'realizar'),(company,'pagar'),(company,'finalizar')]:
            a=self.db.agendas.find_one({'_id':aid})
            r=self.call(client,'/api/operaciones/',{'agendaId':aid,'version':a['_version'],'accion':action})
            self.assertEqual(r.status_code,200,r.content)
        payment=self.db.pagos.find_one({'agendaId':aid});self.assertEqual(payment['estado'],'finalizado');self.assertEqual(payment['monto'],150000)
        a=self.db.agendas.find_one({'_id':aid})
        r=self.call(company,'/api/operaciones/',{'agendaId':aid,'version':a['_version'],'accion':'evaluar','evaluacion':{'nota':5,'comentario':'Evaluación de prueba.'}})
        self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(self.db.pagos.find_one({'agendaId':aid})['evaluacion']['nota'],5)
        self.assertEqual(self.call(admin,f'/api/pagos/{payment["_id"]}/',{'record':{},'version':1},'put').status_code,403)
        # Fallo de proyección: la fuente conserva un marcador durable y puede reintentarse.
        r2=self.call(company,'/api/cuenta/solicitudes/',{'servicioId':sid,'fecha':slot,'claveOperacion':uuid4().hex});rid2=r2.json()['record']['id']
        self.assertEqual(self.call(pro,'/api/cuenta/responder/',{'id':rid2,'estado':'aceptada'}).status_code,200)
        slot2=(datetime.now(timezone.utc)+timedelta(days=3)).replace(minute=0,second=0,microsecond=0).isoformat()
        profile=pro.get('/api/cuenta/').json();self.call(pro,'/api/cuenta/perfil/',{'version':profile['version'],'record':{'disponibilidad':[slot,slot2]}},'put')
        from core.business import book,reconcile
        user=self.db.usuarios.find_one({'correo':'company@example.com'})
        with patch('core.business.projection',side_effect=RuntimeError('simulated interruption')):
            with self.assertRaises(RuntimeError):book(self.db,user,rid2,slot2,uuid4().hex)
        pending=self.db.agendas.find_one({'solicitudId':rid2});self.assertTrue(pending['_syncPendiente'])
        reconcile(self.db);self.assertIsNotNone(self.db.pagos.find_one({'agendaId':pending['_id']}));self.assertNotIn('_syncPendiente',self.db.agendas.find_one({'_id':pending['_id']}))
        stolen=company.cookies[COOKIE].value;self.call(company,'/api/auth/logout/');replay=self.client();replay.cookies[COOKIE]=stolen;self.assertEqual(replay.get('/api/cuenta/').status_code,401)
    def test_catalog_pagination_beyond_one_hundred(self):
        profiles=[];services=[]
        for i in range(110):
            pid=f'p-{i:03d}';sid=f's-{i:03d}'
            profiles.append(to_document('profesionales',{'id':pid,'nombre':f'Perfil {i:03d}','profesion':'Diseño','estado':'validado','validacionProceso':'test'}))
            services.append(to_document('servicios',{'id':sid,'titulo':f'Servicio {i:03d}','profesionalId':pid,'precio':1000,'disponible':True,'categoria':'Diseño'}))
        self.db.profesionales.insert_many(profiles);self.db.servicios.insert_many(services)
        result=self.client().get('/api/catalogo/?limit=24&offset=96').json()
        self.assertEqual(result['pagination']['totalServicios'],110)
        self.assertIn('s-109',[s['id'] for s in result['servicios']])
        self.assertNotIn('validacionProceso',result['profesionales'][0])
    def test_read_load(self):
        self.db.profesionales.insert_one(to_document('profesionales',{'id':'p','nombre':'Perfil','profesion':'Diseño','estado':'validado','validacionProceso':'test'}))
        self.db.servicios.insert_one(to_document('servicios',{'id':'s','titulo':'Servicio de prueba','profesionalId':'p','precio':1000,'disponible':True}))
        def read(_):
            start=perf_counter();r=self.client().get('/api/catalogo/');return (perf_counter()-start)*1000,r.status_code
        with ThreadPoolExecutor(max_workers=4) as pool:readings=list(pool.map(read,range(100)))
        self.assertTrue(all(code==200 for _,code in readings))
        values=sorted(v for v,_ in readings)
        print(f'\nCarga interna: 100 lecturas/4 trabajadores, 0 errores; p95={values[94]:.2f}ms, p99={values[98]:.2f}ms. No representa carga HTTP de producción.')
