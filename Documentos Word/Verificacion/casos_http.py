import json,time,requests,uuid,csv,threading,platform,math,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from pymongo import MongoClient
root=Path(os.environ['SKILLY_EVIDENCE_ROOT']);fixture=json.loads((root/'fixture-secret.json').read_text());base=os.environ['SKILLY_HTTP_BASE'];cases=[]
def login(email):
 s=requests.Session();token=s.get(base+'/api/auth/sesion/',timeout=10).json()['csrfToken'];r=s.post(base+'/api/auth/login/',json={'correo':email,'password':fixture['password']},headers={'X-CSRFToken':token},timeout=10);r.raise_for_status();return s
def call(s,path,data):
 token=s.get(base+'/api/auth/sesion/',timeout=10).json()['csrfToken'];return s.post(base+path,json=data,headers={'X-CSRFToken':token},timeout=10)
def record(key,title,expected,response,condition=True):
 cases.append({'id':key,'caso':title,'esperadoHTTP':expected,'observadoHTTP':response.status_code,'resultado':'APROBADO' if response.status_code==expected and condition else 'FALLIDO'})
s=requests.Session();r=s.get(base+'/api/catalogo/',timeout=10);record('CN-01','Catálogo público sin campos privados',200,r,'passwordHash' not in r.text and 'documentos' not in r.text)
r=call(s,'/api/auth/login/',{'correo':'inexistente@example.com','password':'No-es-una-clave-valida-2026!'});record('CN-02','Credenciales inválidas no crean sesión',401,r)
r=s.get(base+'/api/estado/',timeout=10);record('CN-03','Visitante no accede al panel de datos',401,r)
company=login(fixture['company']);pro=login(fixture['professional'])
r=company.get(base+'/api/estado/',timeout=10);record('CN-04','Empresa no accede a administración',403,r)
r=pro.get(base+'/api/profesionales/otro-perfil/documentos/00000000-0000-0000-0000-000000000001/',timeout=10);record('CN-05','Profesional no descarga documentos ajenos',403,r)
p=pro.get(base+'/api/cuenta/',timeout=10).json();token=pro.get(base+'/api/auth/sesion/',timeout=10).json()['csrfToken']
r=pro.post(base+'/api/profesionales/'+p['profile']['id']+'/documentos/',data={'version':p['version'],'tipo':'cv'},files={'archivo':('falso.pdf',b'%PDF-fake content','application/pdf')},headers={'X-CSRFToken':token},timeout=10);record('CN-06','Archivo con firma PDF falsa se rechaza',400,r)
r=requests.post(base+'/api/auth/login/',json={'correo':fixture['company'],'password':fixture['password']},timeout=10);record('CN-07','Escritura sin token CSRF se rechaza',403,r)
(root/'evidence/http_blackbox.json').write_text(json.dumps(cases,indent=2));print('Caja negra HTTP:',sum(x['resultado']=='APROBADO' for x in cases),'/',len(cases),flush=True)
results=[];samples=[]
def run_phase(label,users,seconds=30):
 stop=time.perf_counter()+seconds;started=time.perf_counter();lock=threading.Lock();entries=[]
 def worker(uid):
  session=requests.Session();local=[];i=0
  while time.perf_counter()<stop:
   path='/api/catalogo/?limit=24&offset=0' if i%5 else '/api/auth/sesion/';t=time.perf_counter();code=0;size=0;error=''
   try:
    r=session.get(base+path,timeout=(3,10));code=r.status_code;size=len(r.content)
   except requests.RequestException as e:error=type(e).__name__
   local.append({'escenario':label,'usuarios':users,'worker':uid,'ruta':path,'ms':round((time.perf_counter()-t)*1000,3),'http':code,'bytes':size,'error':error});i+=1;time.sleep(.05)
  with lock:entries.extend(local)
 with ThreadPoolExecutor(max_workers=users) as pool:list(pool.map(worker,range(users)))
 elapsed=time.perf_counter()-started;values=sorted(x['ms'] for x in entries);percent=lambda q:values[max(0,math.ceil(len(values)*q)-1)]
 result={'escenario':label,'usuarios':users,'duracionObjetivoSeg':seconds,'duracionRealSeg':round(elapsed,2),'peticiones':len(entries),'errores':sum(x['http']!=200 for x in entries),'rps':round(len(entries)/elapsed,2),'p50ms':percent(.5),'p95ms':percent(.95),'p99ms':percent(.99),'pausaPorUsuarioMs':50}
 results.append(result);samples.extend(entries);print(result,flush=True)
for users in [1,5,10]:run_phase('datos_base',users)
client=MongoClient('mongodb://127.0.0.1:27017/');db=client[fixture['database']]
profiles=[{'_id':f'vol-p-{i:04d}','id':f'vol-p-{i:04d}','_version':1,'nombre':f'Profesional sintético volumen {i:04d}','profesion':'Diseño digital','estado':'validado','validacionProceso':'prueba-volumen','ubicacion':'Santiago','resumen':'Datos sintéticos exclusivos de evaluación.','habilidades':['Diseño','Prototipado']} for i in range(1000)]
services=[{'_id':f'vol-s-{i:04d}','id':f'vol-s-{i:04d}','_version':1,'titulo':f'Servicio sintético volumen {i:04d}','profesionalId':f'vol-p-{i//3:04d}','precio':100000,'disponible':True,'categoria':['Diseño','Tecnología','Marketing'][i%3],'descripcion':'Servicio sintético para medición controlada de consultas HTTP.'} for i in range(3000)]
db.profesionales.insert_many(profiles);db.servicios.insert_many(services)
for users in [1,5,10]:run_phase('1000_perfiles_3000_servicios',users)
# Verificar que el volumen continúa siendo consultable más allá de la primera página.
r=requests.get(base+'/api/catalogo/?limit=24&offset=2976',timeout=10);data=r.json();volume={'perfilesInsertados':1000,'serviciosInsertados':3000,'totalServicios':data.get('pagination',{}).get('totalServicios'),'ultimaPaginaHTTP':r.status_code,'registrosEnPagina':len(data.get('servicios',[]))}
with (root/'evidence/http_samples.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=list(samples[0]));writer.writeheader();writer.writerows(samples)
(root/'evidence/http_load.json').write_text(json.dumps({'entorno':{'server':'Django runserver local; HTTP real; sin TLS ni proxy','cliente':platform.platform(),'base':'temporal sintética','mezcla':'80% catálogo, 20% sesión anónima','concurrencia':'modelo cerrado con pausa de 50 ms por trabajador'},'fases':results,'volumen':volume},indent=2))
client.close();print('HTTP y volumen completados.',flush=True)
