"""Ensayo de respaldo/restauración exclusivamente sobre datos sintéticos."""
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
import os,sys,tempfile,json,time,hashlib,shutil
from contextlib import ExitStack
from unittest.mock import patch
from bson import BSON,decode_file_iter,json_util
import argparse
from urllib.parse import urlparse
parser=argparse.ArgumentParser(description='Ensayo aislado de respaldo y restauración con datos sintéticos.')
parser.add_argument('--salida',type=Path,required=True)
args=parser.parse_args()
if args.salida.exists():raise SystemExit('El directorio de salida ya existe; usa uno nuevo.')
project=next((p for p in Path(__file__).resolve().parents if (p/'backend/manage.py').is_file()),None)
if project is None:raise SystemExit('Conserva este archivo dentro del proyecto Skilly.')
root=args.salida;root.mkdir(parents=True);(root/'evidence').mkdir()
sys.path.insert(0,str(project/'backend'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');os.environ['SKILLY_INTEGRATION']='1'
import django;django.setup()
from django.conf import settings
if urlparse(settings.DATABASES['default']['HOST']).hostname not in ('localhost','127.0.0.1','::1'):raise SystemExit('Solo se admite MongoDB local para este ensayo.')
from core.test_integration import RealIntegrationTests
from django.test import override_settings
case=RealIntegrationTests();case.setUp();destination='skilly_restore_'+uuid4().hex;restored=case.mongo[destination]
def digest(records):
    canonical=json_util.dumps(sorted(records,key=lambda x:str(x['_id'])),sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
try:
    case.test_complete_flow_permissions_and_recovery();source=case.db
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='skilly-restore-') as scratch:
        scratch=Path(scratch);backup=scratch/'copia.bson';options={};indexes={};counts={};hashes={}
        with os.fdopen(os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb') as f:
            for name in source.list_collection_names():
                options[name]=source[name].options();indexes[name]=list(source[name].list_indexes());records=list(source[name].find());counts[name]=len(records);hashes[name]=digest(records)
                for record in records:f.write(BSON.encode({'coleccion':name,'documento':record}))
        archive_time=time.perf_counter()-started;restore_start=time.perf_counter()
        for name,opts in options.items():restored.create_collection(name,**opts)
        with backup.open('rb') as f:
            for entry in decode_file_iter(f):restored[entry['coleccion']].insert_one(entry['documento'])
        for name,specs in indexes.items():
            for spec in specs:
                if spec['name']=='_id_':continue
                restored[name].create_index(list(spec['key'].items()),**{k:v for k,v in spec.items() if k not in ('v','ns','key')})
        files=scratch/'documentos';shutil.copytree(case.files,files)
        file_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(case.files).glob('*.pdf')}
        assert all(hashlib.sha256((files/name).read_bytes()).hexdigest()==value for name,value in file_hashes.items())
        for name,count in counts.items():
            assert restored[name].count_documents({})==count
            assert digest(list(restored[name].find()))==hashes[name]
            assert {i['name'] for i in restored[name].list_indexes()}=={i['name'] for i in indexes[name]}
        with ExitStack() as stack:
            for module in ['access','auth_views','views','portal_views','workflow_views','business_views','contract_views']:
                stack.enter_context(patch('core.'+module+'.database',return_value=restored))
            stack.enter_context(override_settings(PRIVATE_DOCUMENT_ROOT=files))
            pro=case.client();assert case.call(pro,'/api/auth/login/',{'correo':'pro@example.com','password':case.password}).status_code==200
            account=pro.get('/api/cuenta/').json();doc=account['profile']['documentos'][0]
            response=pro.get(f"/api/profesionales/{account['profile']['id']}/documentos/{doc['id']}/");assert response.status_code==200;response.close()
        result={'fechaUTC':datetime.now(timezone.utc).isoformat(),'tipo':'Ensayo aislado con datos sintéticos','colecciones':len(counts),'documentos':sum(counts.values()),'archivosPDF':len(file_hashes),'respaldoSegundos':round(archive_time,3),'restauracionVerificacionSegundos':round(time.perf_counter()-restore_start,3),'conteosIguales':True,'hashesIguales':True,'indicesRestaurados':True,'PDFIntegridadVerificada':True,'loginYDescargaRestaurados':True,'RPO_RTO_produccion':'No acreditados por este ensayo; requieren política y medición operativa.'}
        (root/'evidence/restauracion.json').write_text(json.dumps(result,indent=2));print(result)
finally:
    assert destination.startswith('skilly_restore_');case.mongo.drop_database(destination);case.cleanup()
