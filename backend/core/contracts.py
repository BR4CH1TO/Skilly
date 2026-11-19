"""Acuerdos versionados. Cada agregado se actualiza mediante CAS de MongoDB."""
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from uuid import uuid4
from zoneinfo import ZoneInfo
from pymongo import ReturnDocument

POLICY_VERSION = '1.0'
ZONE = ZoneInfo('America/Santiago')
RULES = {'comisionPorcentaje':10,'toleranciaHoras':24,'penalizacionPorcentajeDiario':1,'penalizacionTopePorcentaje':10,'revisionDiasHabiles':5,'respuestaDiasHabiles':3,'liquidacionDiasHabiles':3,'devolucionDiasHabiles':5}
TERMINAL = {'liquidado','reembolsado','cancelado'}


def now(): return datetime.now(timezone.utc)
def stamp(value=None): return (value or now()).isoformat().replace('+00:00','Z')
def date(value):
    if not isinstance(value,str): raise ValueError('Indica una fecha con zona horaria.')
    try: result=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError: raise ValueError('Fecha inválida.') from None
    if result.tzinfo is None: raise ValueError('La fecha debe incluir zona horaria.')
    return result.astimezone(timezone.utc)
def text(data,key,minimum=3,maximum=4000):
    value=data.get(key)
    if not isinstance(value,str) or not minimum<=len(value.strip())<=maximum: raise ValueError(f'{key}: introduce entre {minimum} y {maximum} caracteres.')
    return value.strip()
def money(value):
    if type(value) is not int or not 0<=value<=1_000_000_000: raise ValueError('Los importes deben ser pesos enteros, entre 0 y 1.000.000.000.')
    return value
def percent(value,rate): return int((Decimal(value)*Decimal(rate)/100).quantize(Decimal('1'),rounding=ROUND_DOWN))


def holiday_days(db): return set(x['_id'] for x in db.feriados.find({}, {'_id':1}))
def business_due(db,start,days):
    d=date(start).astimezone(ZONE);holidays=holiday_days(db)
    for _ in range(days):
        d+=timedelta(days=1)
        while d.weekday()>4 or d.date().isoformat() in holidays: d+=timedelta(days=1)
    return stamp(d.replace(hour=18,minute=0,second=0,microsecond=0).astimezone(timezone.utc))


def terms_snapshot():
    from django.conf import settings
    path=settings.PROJECT_DIR/'pages'/'terms.html'
    content=path.read_text()
    return {'version':POLICY_VERSION,'sha256':hashlib.sha256(content.encode()).hexdigest(),'documento':content,'reglas':RULES,'modo':'prueba'}


def access(user,contract):
    return user['rol']=='admin' or (user['rol']=='empresa' and contract['empresaId']==user.get('perfilId')) or (user['rol']=='profesional' and contract['profesionalId']==user.get('perfilId'))
def party(user,contract):
    if not access(user,contract): raise ValueError('No tienes acceso a este acuerdo.')
    return user['rol']
def require_role(role,*allowed):
    if role not in allowed: raise ValueError('Tu rol no puede ejecutar esta operación.')
def item_for(contract,key,value):
    item=next((x for x in contract[key] if x['id']==value),None)
    if not item: raise ValueError('Registro no encontrado en este acuerdo.')
    return item
def open_cases(c,hid): return [i for i in c['incidencias'] if i['hitoId']==hid and i['estado']!='resuelta']


def penalty(h,at=None):
    end=date(h['entregadaEn']) if h.get('entregadaEn') and h.get('estado')!='correcciones' else at or now()
    excluded=0
    for p in h.get('suspensiones',[]):
        left=max(date(h['vence']),date(p['desde']));right=min(end,date(p['hasta']))
        excluded+=max(0,(right-left).total_seconds())
    hours=max(0,int((end-date(h['vence'])).total_seconds()-excluded)//3600)
    periods=max(0,hours-24)//24
    amount=min(percent(h['neto'],10),percent(h['neto'],1)*periods)
    # Se multiplica antes del redondeo para conservar importes pequeños.
    amount=min(percent(h['neto'],10),percent(h['neto'],periods))
    return {'horasAtribuibles':hours,'periodos':periods,'estimada':amount,'tope':percent(h['neto'],10),'aplicada':h.get('compensacion',0),'automatica':False}


def finances(h):
    base=h['neto']-h.get('devolucionServicio',0)
    if h['estado'] in ('cancelado','reembolsado'): base=0
    commission=percent(base,10)
    refund=h.get('devolucionServicio',0)+h.get('compensacion',0)
    held=h.get('financiado',0)-h.get('reembolsado',0)-h.get('liquidado',0)-h.get('comisionCobrada',0)
    return {'netoEjecutado':base,'comision':commission,'compensacion':h.get('compensacion',0),'devolucionTotal':refund,'devolucionPendiente':max(0,refund-h.get('reembolsado',0)),'netoProfesional':max(0,base-commission-h.get('compensacion',0)),'retenido':held,'simulado':True,'impuestos':'No liquidados: prueba sin documentos tributarios reales.'}


def summary(c,db=None):
    c=copy.deepcopy(c)
    for h in c['hitos']:
        h['penalizacion']=penalty(h);h['finanzas']=finances(h)
        h['pasoSiguiente']={'por_financiar':'La empresa debe financiar la etapa en modo de prueba.','financiado':'La empresa confirma los insumos y el profesional inicia.','en_ejecucion':'El profesional debe registrar su entrega.','en_revision':'La empresa revisa y acepta u observa la entrega.','correcciones':'El profesional responde y acuerda las correcciones.','aceptado':'Administración procesa devolución pendiente y liquidación de prueba.','liquidado':'Etapa liquidada.','cancelado':'Procesar devolución de prueba si existe saldo.','reembolsado':'Devolución completada.'}[h['estado']]
        if open_cases(c,h['id']): h['pasoSiguiente']='Incidencia abierta: resolver antes de liquidar.'
    c['id']=c.pop('_id');c['version']=c.pop('_version')
    c.pop('_syncPendiente',None)
    c['resumen']={'retenido':sum(h['finanzas']['retenido'] for h in c['hitos']),'liquidado':sum(h.get('liquidado',0) for h in c['hitos']),'devuelto':sum(h.get('reembolsado',0) for h in c['hitos']),'comisionCobrada':sum(h.get('comisionCobrada',0) for h in c['hitos']),'aceptadoPorAmbasPartes':all(r in c['aceptaciones'] for r in ('empresa','profesional')),'simulado':True}
    c.pop('comandos',None)
    # El documento completo permanece en MongoDB y se descarga por un endpoint propio.
    c['politica'].pop('documento',None)
    return c


def create(db,user,data):
    from .account_controls import require_commercial
    require_commercial(user)
    require_role(user['rol'],'empresa')
    if not isinstance(data.get('agendaId'),str): raise ValueError('Indica el agendamiento.')
    agenda=db.agendas.find_one({'_id':data['agendaId'],'empresaId':user['perfilId']})
    if not agenda or agenda['estado'] not in ('propuesto','confirmado'): raise ValueError('Solo pueden formalizarse servicios propios aún no ejecutados.')
    if agenda.get('pagoEstado','espera')!='espera': raise ValueError('El servicio ya tiene un seguimiento de pago incompatible.')
    policy=terms_snapshot()
    if data.get('acepto') is not True or data.get('versionTerminos')!=policy['version'] or data.get('hashTerminos')!=policy['sha256']: raise ValueError('Debes leer y aceptar la versión vigente de los términos de prueba.')
    raw=data.get('hitos')
    if not isinstance(raw,list) or not 1<=len(raw)<=12: raise ValueError('Define entre una y doce etapas.')
    stages=[];last=now()
    for h in raw:
        if not isinstance(h,dict): raise ValueError('Etapa inválida.')
        deadline=date(h.get('vence'));net=money(h.get('neto'))
        if not net or not last<deadline<=now()+timedelta(days=365): raise ValueError('Las etapas deben tener importe positivo y fechas futuras crecientes, dentro de un año.')
        stages.append({'id':str(uuid4()),'nombre':text(h,'nombre',3,150),'criterios':text(h,'criterios',10),'neto':net,'vence':stamp(deadline),'estado':'por_financiar','suspensiones':[],'entregas':[]});last=deadline
    if sum(h['neto'] for h in stages)!=agenda['precioAcordado']: raise ValueError('La suma de etapas debe coincidir con el importe acordado del agendamiento.')
    service=db.servicios.find_one({'_id':agenda['servicioId']})
    c={'_id':str(uuid4()),'_version':1,'agendaId':agenda['_id'],**{k:agenda[k] for k in ('empresaId','profesionalId','servicioId')},'titulo':service['titulo'],'estado':'propuesto','creadoEn':stamp(),'alcance':text(data,'alcance',10),'entregables':text(data,'entregables',10),'exclusiones':text(data,'exclusiones'),'insumos':text(data,'insumos'),'propiedad':text(data,'propiedad',10),'politica':policy,'hitos':stages,'aceptaciones':{'empresa':{'usuarioId':user['_id'],'fecha':stamp(),'hash':policy['sha256']}},'cambios':[],'incidencias':[],'movimientos':[],'eventos':[{'fecha':stamp(),'actorId':user['_id'],'actor':user['nombre'],'accion':'crear','detalle':'Propuesta y aceptación de la empresa registradas.'}],'comandos':{}}
    claimed=db.agendas.update_one({'_id':agenda['_id'],'_version':agenda['_version'],'_contratoId':{'$exists':False}}, {'$set':{'_contratoId':c['_id'],'_contratoPendiente':c},'$inc':{'_version':1}})
    if not claimed.matched_count: raise ValueError('El servicio cambió o ya tiene un acuerdo. Recarga para continuar.')
    c['_syncPendiente']=True
    db.contratos.insert_one(c)
    project(db,c)
    db.agendas.update_one({'_id':agenda['_id'],'_contratoId':c['_id']},{'$unset':{'_contratoPendiente':''}})
    return c


def mutate(db,user,identifier,data,file_meta=None):
    old=db.contratos.find_one({'_id':identifier})
    if not old: raise ValueError('Acuerdo no encontrado.')
    role=party(user,old)
    key=text(data,'claveOperacion',8,100)
    fingerprint=hashlib.sha256(json.dumps({k:v for k,v in data.items() if k not in ('version','claveOperacion')},sort_keys=True).encode()).hexdigest()
    command=hashlib.sha256((user['_id']+':'+key).encode()).hexdigest()
    if command in old.get('comandos',{}):
        if old['comandos'][command]!=fingerprint: raise ValueError('La clave de operación ya se utilizó con otros datos.')
        return old
    if type(data.get('version')) is not int or old['_version']!=data['version']: raise ValueError('El acuerdo cambió. Recarga antes de continuar.')
    if len(old['eventos'])>=500: raise ValueError('Se alcanzó el límite de eventos. Contacta con administración para continuar el expediente.')
    c=copy.deepcopy(old);action=data.get('accion');time=stamp();detail=''
    h=item_for(c,'hitos',data.get('hitoId')) if data.get('hitoId') else None
    def stage():
        if h is None: raise ValueError('Selecciona una etapa.')
        return h
    def clear():
        if open_cases(c,stage()['id']): raise ValueError('Existe una incidencia abierta sobre esta etapa.')
    if action=='aceptar':
        require_role(role,'profesional')
        if c['estado']!='propuesto' or 'profesional' in c['aceptaciones']: raise ValueError('La propuesta ya no admite esta aceptación.')
        if data.get('acepto') is not True or data.get('hashTerminos')!=c['politica']['sha256']: raise ValueError('Debes aceptar expresamente las condiciones y este acuerdo.')
        c['aceptaciones']['profesional']={'usuarioId':user['_id'],'fecha':time,'hash':c['politica']['sha256']};c['estado']='vigente'
    elif action=='rechazar_acuerdo':
        require_role(role,'profesional')
        if c['estado']!='propuesto': raise ValueError('Solo se rechaza una propuesta pendiente.')
        detail=text(data,'detalle',10)
        for h in c['hitos']: h['estado']='cancelado'
    elif action=='financiar':
        require_role(role,'empresa');stage();clear()
        if c['estado']!='vigente' or h['estado']!='por_financiar': raise ValueError('Ambas partes deben aceptar antes de financiar la etapa.')
        h.update(estado='financiado',financiado=h['neto'],financiadoEn=time)
        c['movimientos'].append({'id':str(uuid4()),'hitoId':h['id'],'tipo':'ingreso','monto':h['neto'],'fecha':time,'simulado':True})
    elif action=='insumos':
        require_role(role,'empresa');stage()
        if c['estado']!='vigente' or h['estado'] not in ('por_financiar','financiado'): raise ValueError('Los insumos deben confirmarse antes del inicio.')
        h['insumosConfirmados']={'fecha':time,'detalle':text(data,'detalle',10)}
    elif action=='iniciar':
        require_role(role,'profesional');stage();clear()
        if h['estado']!='financiado' or not h.get('insumosConfirmados'): raise ValueError('Se necesita financiación e insumos confirmados para iniciar.')
        if now()>=date(h['vence']): raise ValueError('Acuerda una nueva fecha antes de iniciar una etapa vencida.')
        h.update(estado='en_ejecucion',iniciadaEn=time)
    elif action in ('avance','respuesta_correccion'):
        require_role(role,'profesional');stage()
        if h['estado'] not in ('en_ejecucion','correcciones'): raise ValueError('La etapa no está en ejecución o correcciones.')
        detail=text(data,'detalle',10)
        if action=='respuesta_correccion': h['respuestaCorreccion']={'detalle':detail,'fecha':time}
    elif action=='entregar':
        require_role(role,'profesional');stage()
        if h['estado'] not in ('en_ejecucion','correcciones'): raise ValueError('La etapa no admite una entrega.')
        delivery={'fecha':time,'detalle':text(data,'detalle',10),'autorId':user['_id']}
        h['entregas'].append(delivery)
        # Cada entrega conserva su evidencia. Una entrega observada no detiene el retraso.
        h['entregadaEn']=time
        h.update(estado='en_revision',ultimaEntregaEn=time,revisionVence=business_due(db,time,5))
    elif action=='observar':
        require_role(role,'empresa');stage();clear()
        if h['estado']!='en_revision': raise ValueError('Solo se observa una entrega pendiente de revisión.')
        h.update(estado='correcciones',observacion={'fecha':time,'detalle':text(data,'detalle',10)},respuestaCorreccionVence=business_due(db,time,2))
    elif action=='aceptar_entrega':
        require_role(role,'empresa');stage();clear()
        if h['estado']!='en_revision': raise ValueError('No hay una entrega para aceptar.')
        h.update(estado='aceptado',aceptadaEn=time,liquidacionVence=business_due(db,time,3))
    elif action=='cancelar':
        require_role(role,'empresa');stage();clear()
        if h['estado'] not in ('por_financiar','financiado'): raise ValueError('Después del inicio, solicita la cancelación mediante una incidencia.')
        detail=text(data,'detalle',10)
        h.update(estado='cancelado',devolucionServicio=h['neto'] if h.get('financiado') else 0,devolucionVence=business_due(db,time,5))
    elif action=='proponer_cambio':
        require_role(role,'empresa','profesional');stage();clear()
        if c['estado']!='vigente' or h['estado'] in TERMINAL or h['estado']=='aceptado': raise ValueError('Esta etapa no admite cambios.')
        if any(x['estado']=='pendiente' and x['hitoId']==h['id'] for x in c['cambios']): raise ValueError('Resuelve la propuesta de cambio pendiente.')
        new_date=date(data.get('vence'))
        if not now()<new_date<=now()+timedelta(days=365): raise ValueError('La nueva fecha debe ser futura y estar dentro de un año.')
        change={'id':str(uuid4()),'hitoId':h['id'],'estado':'pendiente','rol':role,'actorId':user['_id'],'fecha':time,'motivo':text(data,'detalle',10),'vence':stamp(new_date),'anterior':h['vence']}
        if data.get('desde') or data.get('hasta'):
            a=date(data.get('desde'));b=date(data.get('hasta'))
            if not a<b<=now(): raise ValueError('La exclusión debe ser un intervalo pasado y válido.')
            if any(a<date(p['hasta']) and b>date(p['desde']) for p in h['suspensiones']): raise ValueError('La exclusión se superpone con un período ya acordado.')
            change['suspension']={'desde':stamp(a),'hasta':stamp(b)}
        c['cambios'].append(change)
    elif action in ('aceptar_cambio','rechazar_cambio'):
        require_role(role,'empresa','profesional');change=item_for(c,'cambios',data.get('cambioId'));h=item_for(c,'hitos',change['hitoId']);clear()
        if change['estado']!='pendiente' or change['rol']==role: raise ValueError('La contraparte debe responder al cambio pendiente.')
        if h['estado'] in TERMINAL or h['estado']=='aceptado': raise ValueError('La etapa ya se cerró.')
        if action=='aceptar_cambio':
            if date(change['vence'])<=now(): raise ValueError('La fecha propuesta ya venció.')
            h['vence']=change['vence']
            if change.get('suspension'): h['suspensiones'].append(change['suspension'])
        change.update(estado='aceptado' if action=='aceptar_cambio' else 'rechazado',respondidoEn=time,respondidoPor=user['_id'])
    elif action=='reclamar':
        require_role(role,'empresa','profesional');stage()
        if open_cases(c,h['id']): raise ValueError('Responde a la incidencia abierta antes de crear otra.')
        category=data.get('categoria')
        if category not in ('retraso','abandono','entrega','cancelacion','pago','otro'): raise ValueError('Categoría no válida.')
        c['incidencias'].append({'id':str(uuid4()),'hitoId':h['id'],'categoria':category,'detalle':text(data,'detalle',10),'estado':'abierta','rol':role,'actorId':user['_id'],'creadaEn':time,'respuestaVence':business_due(db,time,3),'resolucionVence':business_due(db,business_due(db,time,3),10),'respuestas':[]})
    elif action=='responder':
        require_role(role,'empresa','profesional');case=item_for(c,'incidencias',data.get('incidenciaId'))
        if case['estado'] not in ('abierta','reconsideracion'): raise ValueError('La incidencia no admite respuestas.')
        case['respuestas'].append({'actorId':user['_id'],'rol':role,'fecha':time,'detalle':text(data,'detalle',10)})
    elif action=='prorrogar_resolucion':
        require_role(role,'admin');case=item_for(c,'incidencias',data.get('incidenciaId'))
        if case.get('prorroga') or case['estado'] not in ('abierta','reconsideracion') or now()>date(case['resolucionVence']): raise ValueError('La prórroga no está disponible.')
        case['prorroga']={'motivo':text(data,'detalle',10),'fecha':time};case['resolucionVence']=business_due(db,case['resolucionVence'],5)
    elif action=='proponer_resolucion':
        require_role(role,'admin');case=item_for(c,'incidencias',data.get('incidenciaId'));h=item_for(c,'hitos',case['hitoId'])
        if case['estado'] not in ('abierta','reconsideracion'): raise ValueError('La incidencia ya tiene propuesta.')
        if case['estado']=='reconsideracion' and case.get('revisorAnterior')==user['_id']: raise ValueError('La reconsideración requiere una persona revisora distinta.')
        if not ({'empresa','profesional'} <= {r['rol'] for r in case['respuestas']} if case['rol']=='sistema' else any(r['rol']!=case['rol'] for r in case['respuestas'])) and now()<date(case['respuestaVence']): raise ValueError('Espera la respuesta de la contraparte o el vencimiento del plazo.')
        refund=money(data.get('devolucion',0));comp=money(data.get('compensacion',0))
        f=finances(h)
        if (h.get('resolucionEconomicaId') or h.get('reembolsado') or h.get('liquidado')) and (refund or comp): raise ValueError('Esta etapa ya tiene una resolución económica o salidas procesadas. No pueden reemplazarse sus saldos; registra una revisión no económica.')
        if refund+comp>f['retenido'] or comp>penalty(h)['estimada'] or comp>h['neto']-refund-percent(h['neto']-refund,10): raise ValueError('La solución supera el saldo, la compensación estimada o el importe ejecutado disponible.')
        case.update(estado='propuesta',revisorId=user['_id'],propuesta={'detalle':text(data,'detalle',20),'devolucion':refund,'compensacion':comp,'fecha':time,'calculo':penalty(h)},consentimientos={},reconsiderarVence=business_due(db,time,5))
    elif action=='reconsiderar':
        require_role(role,'empresa','profesional');case=item_for(c,'incidencias',data.get('incidenciaId'))
        if case['estado']!='propuesta' or now()>date(case['reconsiderarVence']): raise ValueError('No hay propuesta dentro del plazo de reconsideración. Conservas tus vías legales.')
        case.setdefault('propuestasAnteriores',[]).append(copy.deepcopy(case['propuesta']));case.update(estado='reconsideracion',revisorAnterior=case['revisorId'],motivoReconsideracion=text(data,'detalle',10),consentimientos={},respuestaVence=business_due(db,time,3),resolucionVence=business_due(db,time,5));case.pop('prorroga',None)
    elif action=='aceptar_resolucion':
        require_role(role,'empresa','profesional');case=item_for(c,'incidencias',data.get('incidenciaId'));h=item_for(c,'hitos',case['hitoId'])
        if case['estado']!='propuesta' or data.get('acepto') is not True: raise ValueError('Debes aceptar expresamente la propuesta de solución.')
        case['consentimientos'][role]={'fecha':time,'usuarioId':user['_id']}
        if len(case['consentimientos'])==2:
            result=case['propuesta'];case.update(estado='resuelta',resueltaEn=time)
            if h['estado'] not in TERMINAL and not h.get('resolucionEconomicaId') and not h.get('reembolsado') and not h.get('liquidado'):
                h['resolucionEconomicaId']=case['id']
                h.update(devolucionServicio=result['devolucion'],compensacion=result['compensacion'],estado='aceptado' if h.get('financiado') and result['devolucion']<h['neto'] else 'cancelado',liquidacionVence=business_due(db,time,3),devolucionVence=business_due(db,time,5))
    elif action=='devolver':
        require_role(role,'admin');stage();clear();f=finances(h)
        if not f['devolucionPendiente'] or h['estado'] not in ('aceptado','cancelado'): raise ValueError('No hay una devolución autorizada pendiente.')
        h['reembolsado']=h.get('reembolsado',0)+f['devolucionPendiente'];h['reembolsadoEn']=time
        if h['estado']=='cancelado': h['estado']='reembolsado'
        c['movimientos'].append({'id':str(uuid4()),'hitoId':h['id'],'tipo':'devolucion','monto':f['devolucionPendiente'],'fecha':time,'simulado':True})
    elif action=='liquidar':
        require_role(role,'admin');stage();clear();f=finances(h)
        if h['estado']!='aceptado' or f['devolucionPendiente'] or f['retenido']!=f['comision']+f['netoProfesional']: raise ValueError('Se necesita aceptación y saldo conciliado, sin devolución pendiente.')
        h.update(estado='liquidado',liquidado=f['netoProfesional'],comisionCobrada=f['comision'],liquidadoEn=time)
        c['movimientos'].extend([{'id':str(uuid4()),'hitoId':h['id'],'tipo':kind,'monto':amount,'fecha':time,'simulado':True} for kind,amount in [('liquidacion',f['netoProfesional']),('comision',f['comision'])]])
    elif action=='evaluar':
        require_role(role,'empresa')
        if c['estado']!='cerrado' or c.get('evaluacion') or not any(x['estado']=='liquidado' for x in c['hitos']): raise ValueError('Solo se evalúa una vez un acuerdo con trabajo liquidado.')
        note=data.get('nota')
        if type(note) is not int or not 1<=note<=5: raise ValueError('La nota debe estar entre 1 y 5.')
        c['evaluacion']={'nota':note,'comentario':text(data,'detalle',3,1000),'fecha':time,'autorId':user['_id']}
    elif action=='adjuntar' and file_meta:

        detail=file_meta['nombre'];c.setdefault('archivos',[]).append(file_meta)
    else: raise ValueError('Acción no permitida.')
    if all(h['estado'] in TERMINAL for h in c['hitos']): c['estado']='cerrado'
    c['eventos'].append({'fecha':time,'actorId':user['_id'],'actor':user['nombre'],'accion':action,'detalle':detail,'hitoId':h['id'] if h else None})
    c['comandos'][command]=fingerprint;c['_version']+=1;c['actualizadoEn']=time;c['_syncPendiente']=True
    updated=db.contratos.find_one_and_replace({'_id':identifier,'_version':old['_version']},c,return_document=ReturnDocument.AFTER)
    if not updated: raise ValueError('Otro usuario actualizó el acuerdo. Recarga para continuar.')
    project(db,updated)
    return updated


def monitor(db):
    """Recordatorios internos persistentes; nunca acepta entregas ni ejecuta descuentos."""
    count=0
    for old in db.contratos.find({'estado':{'$ne':'cerrado'}}):
        c=copy.deepcopy(old);alerts=c.setdefault('avisos',[]);known={a['clave'] for a in alerts};added=False
        for h in c['hitos']:
            flags=[]
            if h['estado']=='en_revision' and now()>date(h['revisionVence']):
                flags.append(('revision','empresa','Venció la revisión de la entrega. Responde para continuar.'))
                extra=business_due(db,h['revisionVence'],2)
                if now()>date(extra) and not open_cases(c,h['id']):
                    t=stamp();c['incidencias'].append({'id':str(uuid4()),'hitoId':h['id'],'categoria':'entrega','detalle':'Sin respuesta del cliente después del recordatorio. Revisión iniciada sin aceptar la entrega por silencio.','estado':'abierta','rol':'sistema','actorId':'sistema','creadaEn':t,'respuestaVence':business_due(db,t,3),'resolucionVence':business_due(db,business_due(db,t,3),10),'respuestas':[]});added=True
            if h['estado'] in ('en_ejecucion','correcciones') and now()>date(h['vence']): flags.append(('retraso','profesional','La fecha de entrega venció. Registra el avance o informa un impedimento; no se aplicó una multa.'))
            if h['estado']=='aceptado' and now()>date(h['liquidacionVence']): flags.append(('liquidacion','admin','Liquidación de prueba fuera de plazo. Revisa incidencias, devoluciones y saldo.'))
            if finances(h)['devolucionPendiente'] and now()>date(h['devolucionVence']): flags.append(('devolucion','admin','Devolución de prueba pendiente fuera del plazo previsto.'))
            if h['estado']=='correcciones' and now()>date(h['respuestaCorreccionVence']) and not h.get('respuestaCorreccion'): flags.append(('correccion','profesional','Responde las observaciones de la empresa.'))
            for kind,role,message in flags:
                key=kind+':'+h['id']+':'+h.get('ultimaEntregaEn',h['vence'])
                if key not in known: alerts.append({'clave':key,'rol':role,'hitoId':h['id'],'mensaje':message,'fecha':stamp()});known.add(key);added=True
        if added and len(c['eventos'])<500:
            c['eventos'].append({'fecha':stamp(),'actorId':'sistema','actor':'Skilly','accion':'seguimiento','detalle':'Recordatorios internos y vencimientos revisados.'});c['_version']+=1
            if db.contratos.replace_one({'_id':old['_id'],'_version':old['_version']},c).matched_count: count+=1
    return count


def project(db,c):
    """Proyecciones recuperables. El acuerdo es la fuente del saldo de prueba."""
    from .business import projection
    summary_data=summary(c)['resumen']
    finished=c['estado']=='cerrado'
    state='finalizado' if finished and summary_data['liquidado'] else 'cancelado' if finished else 'realizado' if any(h['entregas'] for h in c['hitos']) else 'confirmado' if c['estado']=='vigente' else 'propuesto'
    pay='finalizado' if finished else 'pendiente' if any(h.get('financiado') for h in c['hitos']) else 'espera'
    agenda=db.agendas.find_one_and_update({'_id':c['agendaId'],'$or':[{'contratoVersion':{'$lt':c['_version']}},{'contratoVersion':{'$exists':False}}]}, {'$set':{'estado':state,'pagoEstado':pay,'contratoId':c['_id'],'contratoVersion':c['_version'],'resumenContrato':summary_data,'_syncPendiente':True},'$inc':{'_version':1}},return_document=ReturnDocument.AFTER)
    if agenda: projection(db,agenda)
    for i,event in enumerate(c['eventos']):
        identifier=f"contrato-{c['_id']}-{i}"
        db.historial.update_one({'_id':identifier},{'$setOnInsert':{'_id':identifier,'id':identifier,'_version':1,'tipo':'Servicio','titulo':'Acuerdo: '+event['accion'].replace('_',' '),'descripcion':event.get('detalle') or c['titulo'],'fecha':date(event['fecha']),'actorId':event['actorId'],'actor':event['actor'],'contratoId':c['_id']}},upsert=True)
    db.contratos.update_one({'_id':c['_id'],'_version':c['_version']},{'$unset':{'_syncPendiente':''}})
