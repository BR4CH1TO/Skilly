import hashlib
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .access import access_required
from .storage import database
from .views import database_errors, payload
from . import contracts as engine


def owned(db,user,identifier):
    c=db.contratos.find_one({'_id':identifier})
    if not c or not engine.access(user,c): raise ValueError('Acuerdo no disponible para esta cuenta.')
    return c


@never_cache
@require_http_methods(['GET'])
@database_errors
def policy(request):
    p=engine.terms_snapshot();p.pop('documento')
    return JsonResponse({**p,'pagosRealesHabilitados':False,'motivos':['No hay proveedor de pagos integrado.','Identificación del operador y revisión jurídica pendientes.'],'feriadosCargados':database().feriados.count_documents({}), 'advertenciaCalendario':'Configurar los feriados legales de cada año antes de operar comercialmente.'})


@never_cache
@require_http_methods(['GET','POST'])
@database_errors
@access_required('admin','empresa','profesional')
def agreements(request):
    db=database();user=request.skilly_user
    reconcile(db)
    engine.monitor(db)
    from .account_controls import project_restrictions
    project_restrictions(db)
    if request.method=='POST':
        result=engine.create(db,user,payload(request));return JsonResponse({'record':engine.summary(result)},status=201)
    query={} if user['rol']=='admin' else {'empresaId' if user['rol']=='empresa' else 'profesionalId':user['perfilId']}
    try: offset=max(0,int(request.GET.get('offset','0')))
    except ValueError: raise ValueError('Paginación inválida.') from None
    records=list(db.contratos.find(query).sort([('creadoEn',-1),('_id',1)]).skip(offset).limit(50))
    return JsonResponse({'records':[engine.summary(c) for c in records],'total':db.contratos.count_documents(query),'offset':offset,'limit':50,'rol':user['rol'],'usuarioId':user['_id']})


@never_cache
@require_http_methods(['GET','POST'])
@database_errors
@access_required('admin','empresa','profesional')
def agreement(request,identifier):
    db=database();owned(db,request.skilly_user,identifier)
    if request.method=='GET': c=owned(db,request.skilly_user,identifier)
    else: c=engine.mutate(db,request.skilly_user,identifier,payload(request))
    return JsonResponse({'record':engine.summary(c)})


@never_cache
@require_http_methods(['GET'])
@database_errors
@access_required('admin','empresa','profesional')
def accepted_terms(request,identifier):
    c=owned(database(),request.skilly_user,identifier)
    response=HttpResponse(c['politica']['documento'],content_type='text/html; charset=utf-8')
    response['Content-Disposition']='attachment; filename="condiciones-'+identifier+'.html"'
    response['X-Content-Type-Options']='nosniff'
    return response


@never_cache
@require_http_methods(['POST'])
@database_errors
@access_required('admin','empresa','profesional')
def upload(request,identifier):
    db=database();c=owned(db,request.skilly_user,identifier)
    if len(c.get('archivos',[]))>=50: raise ValueError('Máximo de 50 archivos por acuerdo.')
    f=request.FILES.get('archivo')
    if not f or f.size>5*1024*1024: raise ValueError('Adjunta un PDF de hasta 5 MiB.')
    from .pdf_validation import inspect_pdf
    content=f.read();inspect_pdf(content)
    root=Path(settings.PRIVATE_DOCUMENT_ROOT)/'contratos';root.mkdir(parents=True,exist_ok=True)
    file_id=str(uuid4());path=root/(file_id+'.pdf');path.write_bytes(content);path.chmod(0o600)
    meta={'id':file_id,'nombre':Path(f.name).name[:150],'sha256':hashlib.sha256(content).hexdigest(),'fecha':engine.stamp(),'autorId':request.skilly_user['_id']}
    try:
        data={'accion':'adjuntar','archivoSha256':meta['sha256'],'version':int(request.POST.get('version','0')),'claveOperacion':request.POST.get('claveOperacion',''),'hitoId':request.POST.get('hitoId')}
        result=engine.mutate(db,request.skilly_user,identifier,data,file_meta=meta)
        if not any(a['id']==file_id for a in result.get('archivos',[])): path.unlink(missing_ok=True)
    except BaseException:
        path.unlink(missing_ok=True);raise
    return JsonResponse({'record':engine.summary(result)},status=201)


@never_cache
@require_http_methods(['GET'])
@database_errors
@access_required('admin','empresa','profesional')
def evidence(request,identifier,file_id):
    c=owned(database(),request.skilly_user,identifier)
    f=next((x for x in c.get('archivos',[]) if x['id']==str(file_id)),None)
    if not f: raise ValueError('Archivo no encontrado.')
    p=Path(settings.PRIVATE_DOCUMENT_ROOT)/'contratos'/(f['id']+'.pdf')
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']: raise ValueError('Archivo no disponible o integridad incorrecta.')
    return FileResponse(p.open('rb'),as_attachment=True,filename=f['nombre'],content_type='application/pdf')


def reconcile(db):
    for c in db.contratos.find({'_syncPendiente':True}): engine.project(db,c)
    for agenda in db.agendas.find({'_contratoPendiente':{'$exists':True}}):
        c=agenda['_contratoPendiente'];db.contratos.update_one({'_id':c['_id']},{'$setOnInsert':c},upsert=True)
        engine.project(db,c)
        db.agendas.update_one({'_id':agenda['_id'],'_contratoId':c['_id']},{'$unset':{'_contratoPendiente':''}})


@never_cache
@require_http_methods(['GET','POST'])
@database_errors
@access_required('admin')
def holidays(request):
    db=database()
    if request.method=='POST':
        from datetime import date
        d=payload(request);day=engine.text(d,'fecha',10,10)
        try: date.fromisoformat(day)
        except ValueError: raise ValueError('Fecha de feriado inválida.') from None
        if d.get('eliminar') is True: db.feriados.delete_one({'_id':day})
        else: db.feriados.update_one({'_id':day},{'$set':{'nombre':engine.text(d,'nombre',3,150)}},upsert=True)
    return JsonResponse({'records':[{'fecha':x['_id'],'nombre':x['nombre']} for x in db.feriados.find().sort('_id',1)]})


@never_cache
@require_http_methods(['GET','POST'])
@database_errors
@access_required('admin','empresa','profesional')
def attention(request):
    db=database();u=request.skilly_user
    if request.method=='POST':
        d=payload(request)
        if d.get('id'):
            r=db.atencion.find_one({'_id':d['id']}) if isinstance(d['id'],str) else None
            if not r or (u['rol']!='admin' and r['usuarioId']!=u['_id']): raise ValueError('Solicitud no disponible.')
            if type(d.get('version')) is not int or d['version']!=r['_version']: raise ValueError('La solicitud cambió. Recarga.')
            action=d.get('accion')
            if action=='responder' and u['rol']=='admin':
                changes={'estado':'respondida','respuesta':engine.text(d,'detalle',10),'respondidoEn':engine.stamp(),'responsableId':u['_id']}
            elif action=='reabrir' and u['rol']!='admin' and r['estado']=='respondida':
                changes={'estado':'abierta','motivoRevision':engine.text(d,'detalle',10)}
            else: raise ValueError('Acción no permitida.')
            if not db.atencion.update_one({'_id':r['_id'],'_version':r['_version']},{'$set':changes,'$inc':{'_version':1},'$push':{'historial':{'actorId':u['_id'],'fecha':engine.stamp(),'accion':action,'detalle':engine.text(d,'detalle',10)}}}).matched_count: raise ValueError('La solicitud cambió.')
        else:
            kind=d.get('tipo')
            if kind not in ('acceso','rectificacion','supresion','portabilidad','seguridad','cuenta','consulta'): raise ValueError('Tipo de solicitud inválido.')
            t=engine.stamp();db.atencion.insert_one({'_id':str(uuid4()),'_version':1,'usuarioId':u['_id'],'nombre':u['nombre'],'tipo':kind,'detalle':engine.text(d,'detalle',10),'fecha':t,'estado':'abierta','recepcionRegistradaEn':t,'historial':[]})
    query={} if u['rol']=='admin' else {'usuarioId':u['_id']}
    return JsonResponse({'records':[{**{k:v for k,v in r.items() if not k.startswith('_')},'id':r['_id'],'version':r['_version']} for r in db.atencion.find(query).sort('fecha',-1).limit(100)]})


@never_cache
@require_http_methods(['GET','POST'])
@database_errors
@access_required('admin')
def operator(request):
    db=database()
    if request.method=='POST':
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        d=payload(request);record={k:engine.text(d,k,3,250) for k in ('razonSocial','rut','domicilio','correo')}
        try: validate_email(record['correo'])
        except ValidationError: raise ValueError('Correo oficial inválido.') from None
        # El RUT se conserva como antecedente; no se presenta como identidad verificada.
        record.update(actualizadoEn=engine.stamp(),actorId=request.skilly_user['_id'],verificado=False)
        db.configuracion.update_one({'_id':'operador'},{'$set':record},upsert=True)
    result=db.configuracion.find_one({'_id':'operador'}) or {}
    result.pop('_id',None)
    return JsonResponse({'record':result,'pagosRealesHabilitados':False})


@never_cache
@require_http_methods(['GET','POST'])
@database_errors
@access_required('admin')
def controls(request):
    db=database();actor=request.skilly_user
    if request.method=='POST':
        d=payload(request);u=db.usuarios.find_one({'_id':d.get('usuarioId')}) if isinstance(d.get('usuarioId'),str) else None
        if not u or u['rol']=='admin': raise ValueError('Selecciona una cuenta de empresa o profesional.')
        version=u.get('controlVersion',0)
        if type(d.get('version')) is not int or d['version']!=version: raise ValueError('La cuenta cambió. Recarga antes de continuar.')
        detail=engine.text(d,'detalle',20)
        restriction=None if d.get('levantar') is True else {'motivo':detail,'fecha':engine.stamp(),'desde':engine.stamp() if d.get('urgente') is True else engine.business_due(db,engine.stamp(),3),'urgente':d.get('urgente') is True,'actorId':actor['_id']}
        q={'_id':u['_id'],'controlVersion':version} if 'controlVersion' in u else {'_id':u['_id'],'controlVersion':{'$exists':False}}
        if not db.usuarios.update_one(q,{'$set':{'restriccionComercial':restriction},'$inc':{'controlVersion':1}}).matched_count: raise ValueError('Otro administrador modificó la cuenta.')
        db.atencion.insert_one({'_id':str(uuid4()),'_version':1,'usuarioId':u['_id'],'nombre':u['nombre'],'tipo':'cuenta','detalle':('Restricción levantada. ' if restriction is None else 'Restricción comercial notificada. ')+detail,'fecha':engine.stamp(),'estado':'respondida','respuesta':'Puedes solicitar revisión y aportar antecedentes. Tus acuerdos, pagos e información permanecen accesibles.','responsableId':actor['_id'],'historial':[{'accion':'control_cuenta','actorId':actor['_id'],'fecha':engine.stamp(),'detalle':detail}]})
    from .account_controls import project_restrictions
    project_restrictions(db)
    return JsonResponse({'records':[{'id':u['_id'],'nombre':u['nombre'],'rol':u['rol'],'version':u.get('controlVersion',0),'restriccion':u.get('restriccionComercial')} for u in db.usuarios.find({'rol':{'$in':['empresa','profesional']}}).limit(500)]})
