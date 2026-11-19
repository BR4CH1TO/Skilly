"""Operaciones del servicio. La agenda es la fuente de verdad del seguimiento."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from .storage import to_document

ACTIVE = ("propuesto", "confirmado", "realizado", "finalizado")


def instant(value):
    if isinstance(value, datetime):
        result = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("La fecha indicada no es válida.") from None
    else:
        raise ValueError("Se requiere una fecha válida.")
    if result.tzinfo is None:
        from zoneinfo import ZoneInfo
        from django.conf import settings
        result = result.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
    return result.astimezone(timezone.utc).replace(microsecond=0)


def iso(value):
    return instant(value).isoformat().replace("+00:00", "Z")


def expire_requests(db):
    db.solicitudes.update_many({"estado": "pendiente", "expiracion": {"$lte": datetime.now(timezone.utc)}}, {"$set": {"estado": "expirada"}, "$inc": {"_version": 1}})


def available_slots(db, professional_id):
    p = db.profesionales.find_one({"_id": professional_id})
    if not p or p.get("estado") != "validado" or p.get("_revisionPendiente") or p.get("restriccionComercialActiva"):
        return []
    now = datetime.now(timezone.utc)
    occupied = {iso(a["fecha"]) for a in db.agendas.find({"profesionalId": professional_id, "estado": {"$in": list(ACTIVE)}}, {"fecha": 1})}
    result = set()
    for slot in p.get("disponibilidad", []):
        try:
            date = instant(slot)
            if now < date <= now + timedelta(days=180) and iso(date) not in occupied:
                result.add(iso(date))
        except ValueError:
            continue
    return sorted(result)


def projection(db, agenda):
    """Proyección reintentable: nunca declara ACID entre colecciones en standalone."""
    if "precioAcordado" not in agenda:
        return
    for _ in range(3):
        old = db.pagos.find_one({"agendaId": agenda["_id"]})
        if old and old.get("origenVersion", 0) >= agenda["_version"]:
            break
        record = {"id": old["_id"] if old else "pago-" + agenda["_id"], "agendaId": agenda["_id"],
            **{k: agenda[k] for k in ("solicitudId", "empresaId", "profesionalId", "servicioId")},
            "monto": agenda["precioAcordado"], "fecha": iso(agenda["fecha"]), "estado": agenda.get("pagoEstado", "espera"),
            "origenVersion": agenda["_version"], "simulado": True}
        if agenda.get("contratoId"):
            record["contratoId"]=agenda["contratoId"];record["resumenContrato"]=agenda.get("resumenContrato",{})
        if agenda.get("documento"):
            record["documento"] = agenda["documento"]
        if agenda.get("evaluacion"):
            record["evaluacion"] = agenda["evaluacion"]
        doc = to_document("pagos", record, old["_version"] + 1 if old else 1)
        if old:
            if db.pagos.replace_one({"_id": old["_id"], "_version": old["_version"]}, doc).matched_count:
                break
        else:
            try:
                db.pagos.insert_one(doc)
                break
            except DuplicateKeyError:
                continue
    else:
        raise ValueError("El seguimiento se está sincronizando. Recarga para continuar.")
    for event in agenda.get("_eventosPendientes", []):
        db.historial.update_one({"_id": event["_id"]}, {"$setOnInsert": event}, upsert=True)
    db.agendas.update_one({"_id": agenda["_id"], "_version": agenda["_version"]}, {"$unset": {"_syncPendiente": "", "_eventosPendientes": ""}})


def reconcile(db):
    for agenda in db.agendas.find({"_syncPendiente": True}):
        projection(db, agenda)


def event(agenda_id, version, title, user):
    return {"_id": f"agenda-{agenda_id}-{version}", "id": f"agenda-{agenda_id}-{version}", "_version": 1,
        "tipo": "Servicio", "titulo": title, "descripcion": "Operación registrada en el seguimiento del servicio.",
        "agendaId": agenda_id, "actorId": user["_id"], "actor": user["nombre"], "fecha": datetime.now(timezone.utc)}


def owns(user, agenda):
    return user["rol"] == "admin" or (user["rol"] == "empresa" and agenda["empresaId"] == user["perfilId"]) or (user["rol"] == "profesional" and agenda["profesionalId"] == user["perfilId"])


def book(db, user, request_id, slot, operation_key):
    from .account_controls import require_commercial
    require_commercial(user)
    if user["rol"] not in ("admin", "empresa"):
        raise ValueError("Solo la empresa solicitante puede proponer el horario.")
    if not isinstance(operation_key, str) or not 8 <= len(operation_key) <= 100:
        raise ValueError("Falta el identificador de la operación.")
    existing = db.agendas.find_one({"claveOperacion": user["_id"] + ":" + operation_key})
    if existing:
        if existing["solicitudId"] != request_id or iso(existing["fecha"]) != iso(slot):
            raise ValueError("Ese identificador ya corresponde a otra operación.")
        projection(db, existing)
        return existing
    request = db.solicitudes.find_one({"_id": request_id, "estado": "aceptada"})
    if not request or (user["rol"] != "admin" and request["empresaId"] != user["perfilId"]):
        raise ValueError("La solicitud aceptada no está disponible para esta cuenta.")
    service = db.servicios.find_one({"_id": request["servicioId"], "profesionalId": request["profesionalId"], "disponible": True,"_revisionPendiente":{"$ne":True}})
    if not service or iso(slot) not in available_slots(db, request["profesionalId"]):
        raise ValueError("El servicio u horario ya no está disponible.")
    identifier = str(uuid4())
    record = {"id": identifier, **{k:request[k] for k in ("empresaId", "profesionalId", "servicioId")},
        "solicitudId": request_id, "fecha": iso(slot), "estado": "propuesto", "precioAcordado": service["precio"],
        "pagoEstado": "espera", "contratoRequerido": True, "claveOperacion": user["_id"] + ":" + operation_key, "simulado": True}
    doc = to_document("agendas", record)
    doc.update(_syncPendiente=True, _eventosPendientes=[event(identifier, 1, "Horario propuesto", user)])
    db.agendas.insert_one(doc)
    projection(db, doc)
    return doc


def transition(db, user, identifier, version, action, evaluation=None):
    agenda = db.agendas.find_one({"_id": identifier})
    if not agenda or not owns(user, agenda):
        raise ValueError("No tienes acceso a este agendamiento.")
    if type(version) is not int or agenda["_version"] != version:
        raise ValueError("El seguimiento cambió. Recarga antes de continuar.")
    if agenda.get('_contratoId') or agenda.get('contratoRequerido'):
        raise ValueError('Este servicio se gestiona desde su acuerdo contractual; usa Contratos y entregas.')
    role, state, pay = user["rol"], agenda["estado"], agenda.get("pagoEstado", "espera")
    changes = {}
    if action == "confirmar" and role in ("admin", "profesional") and state == "propuesto":
        changes = {"estado": "confirmado"}
    elif action == "realizar" and role in ("admin", "profesional") and state == "confirmado":
        changes = {"estado": "realizado", "pagoEstado": "pendiente"}
    elif action == "pagar" and role in ("admin", "empresa") and state == "realizado" and pay == "pendiente":
        changes = {"pagoEstado": "pagado", "pagoSimuladoEn": datetime.now(timezone.utc)}
    elif action == "finalizar" and role in ("admin", "empresa") and state == "realizado" and pay == "pagado":
        changes = {"estado": "finalizado", "pagoEstado": "finalizado"}
    elif action == "cancelar" and state in ("propuesto", "confirmado"):
        changes = {"estado": "cancelado"}
    elif action == "referencia" and role in ("admin","empresa"):
        reference = evaluation.get("referencia") if isinstance(evaluation,dict) else None
        if not isinstance(reference,str) or len(reference)>160:
            raise ValueError("La referencia debe tener hasta 160 caracteres.")
        changes = {"documento":reference.strip()}
    elif action == "evaluar" and role in ("admin", "empresa") and state == "finalizado" and not agenda.get("evaluacion"):
        if not isinstance(evaluation, dict) or type(evaluation.get("nota")) is not int or not 1 <= evaluation["nota"] <= 5 or not isinstance(evaluation.get("comentario"), str) or not 3 <= len(evaluation["comentario"].strip()) <= 1000:
            raise ValueError("Indica una nota de 1 a 5 y un comentario de 3 a 1000 caracteres.")
        changes = {"evaluacion": {"nota":evaluation["nota"], "comentario":evaluation["comentario"].strip(), "fecha":iso(datetime.now(timezone.utc))}}
    else:
        raise ValueError("Esta acción no corresponde al estado del servicio o al rol de tu cuenta.")
    version += 1
    changes["_syncPendiente"] = True
    updated = db.agendas.find_one_and_update({"_id": identifier, "_version": version - 1, "_contratoId": {"$exists": False}}, {"$set": changes, "$inc": {"_version": 1}, "$push": {"_eventosPendientes": event(identifier, version, action.capitalize(), user)}}, return_document=ReturnDocument.AFTER)
    if updated is None:
        raise ValueError("Otro usuario actualizó el servicio. Recarga para continuar.")
    projection(db, updated)
    return updated
