from datetime import datetime, timezone, timedelta
from uuid import uuid4

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .access import access_required
from .storage import database, serialize, to_document, validate_record
from .views import database_errors, payload
from .workflow import review_profile, review_service

PROFILE_FIELDS = ("id", "nombre", "profesion", "especialidad", "ubicacion", "resumen", "habilidades", "experiencia")
SERVICE_FIELDS = ("id", "titulo", "descripcion", "categoria", "duracion", "precio", "entregables", "profesionalId")


def visible_catalog(db, limit=24, offset=0, query="", category="Todos"):
    import re
    base = [{"$match":{"disponible":True,"_revisionPendiente":{"$ne":True}}}, {"$lookup":{"from":"profesionales","localField":"profesionalId","foreignField":"_id","as":"professional"}}, {"$unwind":"$professional"}, {"$match":{"professional.estado":"validado","professional.validacionProceso":{"$exists":True},"professional._revisionPendiente":{"$ne":True},"professional.restriccionComercialActiva":{"$ne":True}}}]
    filters = {}
    if query:
        pattern = {"$regex":re.escape(query), "$options":"i"}
        filters["$or"] = [{k:pattern} for k in ("titulo","descripcion","categoria","professional.nombre")]
    if category != "Todos": filters["categoria"] = category
    matched = [{"$match":filters}] if filters else []
    data = next(iter(db.servicios.aggregate(base + [{"$facet":{
        "items":matched + [{"$sort":{"titulo":1,"_id":1}},{"$skip":offset},{"$limit":limit}],
        "total":matched + [{"$count":"value"}],
        "categories":[{"$group":{"_id":"$categoria"}},{"$sort":{"_id":1}}]
    }}])), {"items":[],"total":[],"categories":[]})
    profile_filter = {"restriccionComercialActiva":{"$ne":True},"estado":"validado","validacionProceso":{"$exists":True},"_revisionPendiente":{"$ne":True}}
    if query:
        profile_filter["$or"] = [{k:{"$regex":re.escape(query),"$options":"i"}} for k in ("nombre","profesion","resumen")]
    profiles = list(db.profesionales.find(profile_filter).sort([("nombre",1),("_id",1)]).skip(offset).limit(limit))
    services = [{**{k:item.get(k) for k in SERVICE_FIELDS}, "profesionalNombre":item["professional"]["nombre"],"demostracion":item["professional"].get("demostracion") is True} for item in data["items"]]
    return {"profesionales":[{**{k:p.get(k) for k in PROFILE_FIELDS},"demostracion":p.get("demostracion") is True} for p in profiles],"servicios":services,
        "categorias":[x["_id"] for x in data["categories"] if isinstance(x["_id"],str)],
        "pagination":{"limit":limit,"offset":offset,"totalServicios":data["total"][0]["value"] if data["total"] else 0,"totalProfesionales":db.profesionales.count_documents(profile_filter)}}


@never_cache
@require_http_methods(["GET"])
@database_errors
def catalog(request):
    try:
        limit = max(1,min(60,int(request.GET.get("limit",24))))
        offset = max(0,int(request.GET.get("offset",0)))
    except ValueError:
        raise ValueError("La página solicitada no es válida.") from None
    return JsonResponse(visible_catalog(database(),limit,offset,request.GET.get("q", "")[:150],request.GET.get("categoria", "Todos")[:100]))


@never_cache
@require_http_methods(["GET"])
@database_errors
@access_required("empresa", "profesional")
def account(request):
    db, user = database(), request.skilly_user
    from .account_controls import project_restrictions
    project_restrictions(db)
    from .business import reconcile, expire_requests, available_slots
    reconcile(db)
    from .workflow import reconcile_reviews
    reconcile_reviews(db)
    expire_requests(db)
    kind = "empresas" if user["rol"] == "empresa" else "profesionales"
    profile = db[kind].find_one({"_id": user["perfilId"]})
    if profile is None:
        return JsonResponse({"error": "Perfil no disponible."}, status=404)
    field = "empresaId" if user["rol"] == "empresa" else "profesionalId"
    requests = [serialize(s) for s in db.solicitudes.find({field: user["perfilId"]}).sort("fecha", -1).limit(100)]
    for item in requests:
        service = db.servicios.find_one({"_id": item["servicioId"]}, {"titulo": 1})
        item["servicioTitulo"] = service["titulo"] if service else "Servicio no disponible"
        item["horariosDisponibles"] = available_slots(db,item["profesionalId"]) if user["rol"]=="empresa" and item["estado"]=="aceptada" else []
    result = {"rol": user["rol"], "profile": serialize(profile), "version": profile["_version"], "solicitudes": requests}
    result["agendas"] = [{"record":serialize(a),"version":a["_version"]} for a in db.agendas.find({field:user["perfilId"]}).sort("fecha",-1).limit(200)]
    result["pagos"] = [serialize(p) for p in db.pagos.find({field:user["perfilId"]}).limit(200)]
    if user["rol"] == "profesional":
        validation = db.validaciones.find_one({"_id": user["perfilId"]})
        result["validacion"] = serialize(validation) if validation else None
        result["servicios"] = [{"record": serialize(s), "version": s["_version"]} for s in db.servicios.find({"profesionalId": user["perfilId"]})]
    return JsonResponse(result)


@never_cache
@require_http_methods(["POST"])
@database_errors
@access_required("empresa")
def create_request(request):
    from .account_controls import require_commercial
    require_commercial(request.skilly_user)
    data, db, user = payload(request), database(), request.skilly_user
    key = data.get("claveOperacion")
    if not isinstance(key,str) or not 8 <= len(key) <= 100:
        raise ValueError("Falta el identificador de la solicitud.")
    key = user["_id"] + ":" + key
    old = db.solicitudes.find_one({"claveOperacion":key})
    if old:
        from .business import iso
        if old["servicioId"] != data.get("servicioId") or iso(old["fecha"]) != iso(data.get("fecha")):
            raise ValueError("Esta operación ya corresponde a otro servicio.")
        return JsonResponse({"record":serialize(old)}, status=200)
    service = db.servicios.find_one({"_id": data.get("servicioId"), "disponible": True,"_revisionPendiente":{"$ne":True}}) if isinstance(data.get("servicioId"), str) else None
    if service is None:
        raise ValueError("El servicio ya no está disponible.")
    profile = db.profesionales.find_one({"_id": service["profesionalId"], "estado": "validado", "validacionProceso": {"$exists": True},"_revisionPendiente":{"$ne":True}})
    if profile is None or profile.get("restriccionComercialActiva"):
        raise ValueError("El profesional no está habilitado para recibir solicitudes.")
    try:
        date = datetime.fromisoformat(data.get("fecha", "").replace("Z", "+00:00"))
        if date.tzinfo is None or date <= datetime.now(timezone.utc):
            raise ValueError()
    except (ValueError, AttributeError):
        raise ValueError("Selecciona una fecha futura para el servicio.") from None
    identifier = str(uuid4())
    record = {"claveOperacion":key,"id": identifier, "empresaId": user["perfilId"], "servicioId": service["_id"], "profesionalId": service["profesionalId"], "fecha": date.isoformat(), "expiracion": (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat(), "estado": "pendiente"}
    db.solicitudes.insert_one(to_document("solicitudes", record))
    return JsonResponse({"record": record}, status=201)


@never_cache
@require_http_methods(["POST"])
@database_errors
@access_required("profesional")
def answer_request(request):
    data, db, user = payload(request), database(), request.skilly_user
    if not isinstance(data.get("id"), str) or data.get("estado") not in ("aceptada", "rechazada"):
        raise ValueError("Respuesta de solicitud inválida.")
    profile = db.profesionales.find_one({"_id": user["perfilId"], "estado": "validado"})
    if profile is None:
        raise ValueError("Completa tu validación antes de responder solicitudes.")
    result = db.solicitudes.update_one({"_id": data["id"], "profesionalId": user["perfilId"], "estado": "pendiente", "expiracion": {"$gt": datetime.now(timezone.utc)}}, {"$set": {"estado": data["estado"]}, "$inc": {"_version": 1}})
    if result.matched_count != 1:
        return JsonResponse({"error": "La solicitud no está disponible, expiró o ya fue respondida."}, status=409)
    return JsonResponse({"message": "Respuesta guardada."})


@never_cache
@require_http_methods(["PUT"])
@database_errors
@access_required("profesional")
def save_profile(request):
    db, data, user = database(), payload(request), request.skilly_user
    profile = db.profesionales.find_one({"_id": user["perfilId"]})
    if profile is None:
        raise ValueError("Perfil no disponible.")
    if type(data.get("version")) is not int or data["version"] != profile["_version"]:
        return JsonResponse({"error": "Tu perfil cambió. Recarga antes de guardar."}, status=409)
    record = serialize(profile)
    allowed = {"profesion", "ubicacion", "resumen", "habilidades", "experiencia", "disponibilidad"}
    changes = data.get("record")
    if not isinstance(changes, dict) or set(changes) - allowed:
        raise ValueError("Los campos enviados no se pueden modificar desde esta cuenta.")
    if "disponibilidad" in changes:
        from .business import instant, iso
        slots = changes["disponibilidad"]
        if not isinstance(slots,list) or len(slots)>100:
            raise ValueError("Introduce un máximo de 100 horarios.")
        dates = [instant(slot) for slot in slots]
        now = datetime.now(timezone.utc)
        if any(not now < date <= now+timedelta(days=180) for date in dates):
            raise ValueError("La disponibilidad debe estar dentro de los próximos 180 días.")
        changes["disponibilidad"] = sorted({iso(d) for d in dates})
    record.update(changes)
    validate_record("profesionales", record, db)
    result = db.profesionales.replace_one({"_id": user["perfilId"], "_version": data["version"]}, {**to_document("profesionales", record, data["version"] + 1),"estado":"revision","_revisionPendiente":True})
    if result.matched_count != 1:
        return JsonResponse({"error": "El perfil cambió durante el guardado."}, status=409)
    review_profile(db, user["perfilId"])
    return JsonResponse({"message": "Perfil guardado y revisado."})


@never_cache
@require_http_methods(["POST", "PUT"])
@database_errors
@access_required("profesional")
def save_service(request):
    from .account_controls import require_commercial
    require_commercial(request.skilly_user)
    db, data, user = database(), payload(request), request.skilly_user
    changes = data.get("record")
    allowed = set(SERVICE_FIELDS) - {"id", "profesionalId"}
    if not isinstance(changes, dict) or set(changes) - allowed:
        raise ValueError("Los campos del servicio no son válidos.")
    old = None
    if request.method == "PUT":
        identifier = data.get("id")
        old = db.servicios.find_one({"_id": identifier, "profesionalId": user["perfilId"]}) if isinstance(identifier, str) else None
        if old is None:
            return JsonResponse({"error": "Servicio no encontrado."}, status=404)
        if type(data.get("version")) is not int or data["version"] != old["_version"]:
            return JsonResponse({"error": "El servicio cambió. Recarga antes de guardar."}, status=409)
    identifier = old["_id"] if old else str(uuid4())
    record = {**(serialize(old) if old else {}), **changes, "id": identifier, "profesionalId": user["perfilId"], "disponible": False}
    validate_record("servicios", record, db)
    if old:
        result = db.servicios.replace_one({"_id": identifier, "_version": old["_version"]}, {**to_document("servicios", record, old["_version"] + 1),"_revisionPendiente":True})
        if result.matched_count != 1:
            return JsonResponse({"error": "El servicio cambió durante el guardado."}, status=409)
    else:
        db.servicios.insert_one({**to_document("servicios", record),"_revisionPendiente":True})
    result = review_service(db, identifier)
    return JsonResponse({"record": serialize(result), "version": result["_version"]}, status=200 if old else 201)

@never_cache
@require_http_methods(["GET"])
@database_errors
def public_service(request, identifier):
    db = database()
    s = db.servicios.find_one({"_id":identifier,"disponible":True,"_revisionPendiente":{"$ne":True}})
    p = db.profesionales.find_one({"_id":s["profesionalId"],"estado":"validado","validacionProceso":{"$exists":True},"_revisionPendiente":{"$ne":True}}) if s else None
    if not p:
        return JsonResponse({"error":"El servicio no está disponible."},status=404)
    return JsonResponse({"record":{**{k:s.get(k) for k in SERVICE_FIELDS},"profesionalNombre":p["nombre"],"demostracion":p.get("demostracion") is True}})
