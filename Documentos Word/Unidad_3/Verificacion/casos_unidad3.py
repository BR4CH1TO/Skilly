"""Protocolo HTTP, volumen, estrés acotado y recuperación sobre base temporal."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import os,json,time,math,threading,csv,platform
import requests
from pymongo import MongoClient
R=Path(os.environ['SKILLY_EVIDENCE_ROOT'])/'evidence';info=json.loads((R.parent/'fixture-secret.json').read_text());base=os.environ['SKILLY_HTTP_BASE']
assert info['database'].startswith('skilly_integration_')
cases=[];samples=[];phases=[]
def record(cid,title,status,response,condition=True):
 result={'id':cid,'caso':title,'esperadoHTTP':status,'observadoHTTP':response.status_code,'condicionComprobada':bool(condition),'resultado':'APROBADO' if status==response.status_code and condition else 'FALLIDO'};cases.append(result);return result

def login(email):
 s=requests.Session();token=s.get(base+'/api/auth/sesion/',timeout=8).json()['csrfToken'];r=s.post(base+'/api/auth/login/',json={'correo':email,'password':info['password']},headers={'X-CSRFToken':token},timeout=8);r.raise_for_status();return s
s=requests.Session();r=s.get(base+'/api/catalogo/',timeout=8);record('CN-01','Catálogo sin documentos, credenciales ni notas privadas',200,r,not any(x in r.text for x in ['passwordHash','"documentos"','"entrevista"']))
token=s.get(base+'/api/auth/sesion/',timeout=8).json()['csrfToken'];r=s.post(base+'/api/auth/login/',json={'correo':'inexistente@example.invalid','password':'No-valida-9283-2026!'},headers={'X-CSRFToken':token},timeout=8);record('CN-02','Credenciales inválidas rechazadas',401,r)
r=s.get(base+'/api/estado/',timeout=8);record('CN-03','Visitante sin acceso al estado administrativo',401,r)
company=login(info['company']);pro=login(info['professional']);r=company.get(base+'/api/estado/',timeout=8);record('CN-04','Empresa sin privilegios administrativos',403,r)
r=pro.get(base+'/api/profesionales/ajeno/documentos/00000000-0000-0000-0000-000000000001/',timeout=8);record('CN-05','Documento ajeno no descargable',403,r)
p=pro.get(base+'/api/cuenta/',timeout=8).json();token=pro.get(base+'/api/auth/sesion/',timeout=8).json()['csrfToken'];r=pro.post(base+'/api/profesionales/'+p['profile']['id']+'/documentos/',data={'version':p['version'],'tipo':'cv'},files={'archivo':('falso.pdf',b'%PDF-falso','application/pdf')},headers={'X-CSRFToken':token},timeout=8);record('CN-06','Firma PDF aparente con estructura inválida rechazada',400,r)
r=requests.post(base+'/api/auth/login/',json={'correo':info['company'],'password':info['password']},timeout=8);record('CN-07','POST sin CSRF rechazado',403,r)
for cid,path,expected,field,value in [('CN-08','/api/catalogo/?limit=0',200,'limit',1),('CN-09','/api/catalogo/?limit=999',200,'limit',60),('CN-10','/api/catalogo/?offset=-1',200,'offset',0)]:
 r=s.get(base+path,timeout=8);record(cid,'Límite de paginación '+path.split('?')[1],expected,r,r.json().get('pagination',{}).get(field)==value)
r=s.get(base+'/api/catalogo/?offset=abc',timeout=8);record('CN-11','Offset no numérico produce error controlado',400,r)
r=s.get(base+'/api/catalogo/',params={'q':'.*'},timeout=8);record('CN-12','La búsqueda trata metacaracteres como texto literal',200,r,r.json().get('pagination',{}).get('totalServicios')==0)
(R/'caja_negra.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2));print('Caja negra',sum(x['resultado']=='APROBADO' for x in cases),'/',len(cases),flush=True)

def phase(kind,workers,seconds=8,pause=.025):
 start=time.perf_counter();deadline=start+seconds;lock=threading.Lock();entries=[]
 def work(worker):
  session=requests.Session();local=[];i=0
  while time.perf_counter()<deadline:
   path='/api/auth/sesion/' if i%5==0 else '/api/catalogo/?limit=24&offset=0';before=time.perf_counter();status=0;err=''
   try:status=session.get(base+path,timeout=(1,5)).status_code
   except requests.RequestException as error:err=type(error).__name__
   local.append({'fase':kind,'trabajadores':workers,'worker':worker,'ruta':path,'ms':round((time.perf_counter()-before)*1000,3),'http':status,'error':err});i+=1
   if pause:time.sleep(pause)
  session.close()
  with lock:entries.extend(local)
 with ThreadPoolExecutor(max_workers=workers) as pool:list(pool.map(work,range(workers)))
 elapsed=time.perf_counter()-start;v=sorted(x['ms'] for x in entries);pct=lambda q:v[max(0,math.ceil(len(v)*q)-1)]
 result={'fase':kind,'trabajadores':workers,'segundosObjetivo':seconds,'segundosReales':round(elapsed,3),'peticiones':len(entries),'errores':sum(x['http']!=200 for x in entries),'p95ms':pct(.95),'p99ms':pct(.99),'rps':round(len(entries)/elapsed,3),'pausaMs':int(pause*1000)};result['tasaError']=result['errores']/result['peticiones'];phases.append(result);samples.extend(entries);print(result,flush=True);return result
client=MongoClient('mongodb://127.0.0.1:27017/',serverSelectionTimeoutMS=3000);db=client[info['database']]
try:
 phase('base',1);phase('base',5);phase('base',10)
 db.profesionales.insert_many([{'_id':f'vol-p-{i:04d}','id':f'vol-p-{i:04d}','_version':1,'nombre':f'Perfil sintético {i:04d}','profesion':'Diseño','estado':'validado','validacionProceso':'ensayo-volumen','habilidades':['Diseño','Prototipado']} for i in range(1000)])
 db.servicios.insert_many([{'_id':f'vol-s-{i:04d}','id':f'vol-s-{i:04d}','_version':1,'titulo':f'Oferta sintética {i:04d}','profesionalId':f'vol-p-{i//3:04d}','precio':100000,'disponible':True,'categoria':'Diseño','descripcion':'Datos sintéticos para prueba de volumen.'} for i in range(3000)])
 phase('volumen',1);phase('volumen',5);phase('volumen',10)
 r=s.get(base+'/api/catalogo/?limit=24&offset=2976',timeout=8);volume={'profesionalesInsertados':1000,'serviciosInsertados':3000,'HTTP':r.status_code,'totalServicios':r.json().get('pagination',{}).get('totalServicios'),'registrosUltimaPagina':len(r.json().get('servicios',[]))}
 reason='Límite preventivo de 40 trabajadores alcanzado; no se determina capacidad máxima.'
 for workers in [1,5,10,20,40]:
  result=phase('estres_acotado',workers,pause=0)
  if result['tasaError']>.05 or result['p95ms']>2000:
   reason='Se activó umbral preventivo: error >5% o p95 >2000 ms.';break
 recovery=phase('recuperacion',1)
 explain=db.profesionales.find({'estado':'validado','_revisionPendiente':{'$ne':True},'restriccionComercialActiva':{'$ne':True},'validacionProceso':{'$exists':True}}).sort([('nombre',1),('_id',1)]).limit(24).explain()
 def stages(v):
  if isinstance(v,dict):return ([v['stage']] if 'stage'in v else [])+sum((stages(x) for x in v.values()),[])
  if isinstance(v,list):return sum((stages(x) for x in v),[])
  return []
 st=explain.get('executionStats',{});query={'consulta':'Listado paginado de profesionales validados, orden nombre/_id','etapas':sorted(set(stages(explain.get('queryPlanner',{}).get('winningPlan',{})))),'nReturned':st.get('nReturned'),'totalDocsExamined':st.get('totalDocsExamined'),'totalKeysExamined':st.get('totalKeysExamined'),'executionTimeMillis':st.get('executionTimeMillis'),'alcance':'Consulta de perfiles; no es el explain de la agregación de servicios.'}
 out={'fechaUTC':datetime.now(timezone.utc).isoformat(),'entorno':{'servidor':'Django runserver local; HTTP sin TLS','cliente':platform.platform(),'mezcla':'80% catálogo; 20% consulta de sesión anónima','modelo':'Cerrado; trabajadores concurrentes, no usuarios humanos ni tasa de llegada ilimitada','duracionFaseSegundos':8},'umbralesPrevios':{'errorCargaVolumen':0,'p95CargaVolumenObjetivoMs':500,'paradaEstresError':.05,'paradaEstresP95Ms':2000,'maxTrabajadores':40,'naturaleza':'Criterios propuestos de laboratorio; no SLA ni certificación externa'},'fases':phases,'volumen':volume,'paradaEstres':reason,'recuperacionSatisfactoria':recovery['errores']==0 and recovery['p95ms']<=500,'consultaIndices':query,'limites':'Prueba corta y local. No acredita producción ni punto de ruptura si no fue alcanzado.'}
 (R/'rendimiento.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 with (R/'muestras_http.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(samples[0]));writer.writeheader();writer.writerows(samples)
 if any(x['resultado']!='APROBADO' for x in cases):raise SystemExit('Se detectaron discrepancias de caja negra. Revisar evidencia.')
finally:client.close()
