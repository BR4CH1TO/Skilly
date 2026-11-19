"""Reglas deterministas y trazabilidad del proceso de validación."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from pymongo import ReturnDocument

RULESET = "2026.10.29"
DOCUMENT_TYPES = {"cv": "Currículum", "formacion": "Respaldo de formación o experiencia"}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def check(code, label, passed, detail):
    return {"codigo": code, "nombre": label, "resultado": "aprobado" if passed else "pendiente", "detalle": detail}


def text(value, minimum=1):
    return isinstance(value, str) and len(value.strip()) >= minimum


def profile_checks(profile):
    checks = [
        check("PER-01", "Identificación del perfil", text(profile.get("nombre"), 3), "Nombre de al menos 3 caracteres."),
        check("PER-02", "Profesión y ubicación", text(profile.get("profesion"), 3) and text(profile.get("ubicacion"), 3), "Completar profesión y ubicación."),
        check("PER-03", "Presentación profesional", text(profile.get("resumen"), 40), "Resumen de al menos 40 caracteres."),
        check("PER-04", "Habilidades", isinstance(profile.get("habilidades"), list) and len([s for s in profile["habilidades"] if text(s, 2)]) >= 2, "Informar al menos dos habilidades."),
    ]
    documents = profile.get("documentos", [])
    for kind, label in DOCUMENT_TYPES.items():
        matching = [d for d in documents if d.get("tipo") == kind]
        valid = bool(matching and matching[-1].get("formatoComprobado") is True)
        checks.append(check("DOC-" + kind.upper(), label, valid,
            "Estructura PDF y tamaño comprobados. Autenticidad no verificada externamente." if valid else "Subir PDF, máximo 5 MiB. La recepción no acredita autenticidad."))
    return checks


def profile_result(profile, interview):
    checks = profile_checks(profile)
    ready = all(c["resultado"] == "aprobado" for c in checks)
    outcome = interview.get("resultado", "pendiente")
    checks.append(check("ENT-01", "Entrevista online", outcome == "aprobada",
        {"aprobada": "Entrevista aprobada por el equipo de validación.", "rechazada": "Entrevista rechazada: " + interview.get("observaciones", ""), "segunda": "Se requiere segunda entrevista.", "agendada": "Entrevista agendada; falta registrar su resultado."}.get(outcome, "El equipo de validación debe realizar la entrevista online.")))
    if outcome == "rechazada":
        checks[-1]["resultado"] = "rechazado"
    if not ready:
        stage, status, owner, next_step = "Completar antecedentes", "revision", "Profesional", "Corregir los requisitos pendientes y volver a revisar."
    elif outcome == "rechazada":
        stage, status, owner, next_step = "Entrevista rechazada", "rechazado", "Profesional", "Consultar las observaciones de la entrevista."
    elif outcome == "segunda":
        stage, status, owner, next_step = "Segunda entrevista", "segunda", "Equipo de validación", "Agendar y realizar una segunda entrevista online."
    elif outcome == "aprobada":
        stage, status, owner, next_step = "Profesional validado", "validado", "Profesional", "Publicar servicios para su revisión automática."
    else:
        stage = "Entrevista agendada" if outcome == "agendada" else "Pendiente de entrevista"
        status, owner, next_step = "revision", "Equipo de validación", "Realizar la entrevista online y registrar su resultado."
    if status == "validado":
        justification = "El sistema habilitó el perfil porque cumple todos los requisitos de información y documentación, y tiene registrada una entrevista aprobada por el equipo de validación."
    elif status == "rechazado":
        justification = "El sistema no habilitó el perfil porque la entrevista fue rechazada por el equipo de validación. Motivo registrado: " + interview.get("observaciones", "Sin observaciones.")
    else:
        missing = [c["nombre"] for c in checks if c["resultado"] != "aprobado"]
        justification = "El perfil aún no cumple todos los requisitos. Falta completar: " + ", ".join(missing) + "."
    return {"reglasVersion": RULESET, "comprobaciones": checks, "etapa": stage, "estado": status, "responsable": owner, "siguientePaso": next_step,
        "justificacion": justification, "demostracion": profile.get("demostracion") is True,
        "alcance": "Revisión automática de requisitos y formato; no certifica identidad, autenticidad ni competencias."}


def service_result(service, profile):
    checks = [
        check("SER-01", "Profesional validado", profile.get("estado") == "validado" and bool(profile.get("validacionProceso")), "Requiere requisitos automáticos completos y entrevista aprobada."),
        check("SER-02", "Título claro", text(service.get("titulo"), 8), "Título de al menos 8 caracteres."),
        check("SER-03", "Descripción", text(service.get("descripcion"), 40), "Descripción de al menos 40 caracteres."),
        check("SER-04", "Precio", type(service.get("precio")) is int and service["precio"] > 0, "Precio entero mayor que cero en CLP."),
        check("SER-05", "Categoría y duración", text(service.get("categoria"), 3) and text(service.get("duracion"), 3), "Informar categoría y duración estimada."),
        check("SER-06", "Entregables", text(service.get("entregables"), 15), "Describir qué recibe la empresa, al menos 15 caracteres."),
    ]
    passed = all(c["resultado"] == "aprobado" for c in checks)
    return {"reglasVersion": RULESET, "comprobaciones": checks, "estado": "publicado" if passed else "correccion", "responsable": "Profesional",
        "siguientePaso": "Servicio disponible para solicitudes." if passed else "Corregir los puntos pendientes y volver a enviar.",
        "alcance": "Revisión de requisitos de publicación; no garantiza calidad, legalidad ni prestación efectiva."}


def audit(db, resource, identifier, result, actor="Sistema"):
    key = resource + ":" + identifier + ":" + result["huella"] if result.get("huella") else str(uuid4())
    db.revisiones.update_one({"_id": key}, {"$setOnInsert": {"_id": key, "recurso": resource, "registroId": identifier, "actor": actor, "fecha": now(), "resultado": result}}, upsert=True)


def review_service(db, identifier, force=False):
    for _ in range(3):
        service = db.servicios.find_one({"_id": identifier})
        if service is None:
            raise ValueError("Servicio no encontrado.")
        profile = db.profesionales.find_one({"_id": service["profesionalId"]}) or {}
        result = service_result(service, profile)
        fingerprint = hashlib.sha256(json.dumps({"service": {k:v for k,v in service.items() if not k.startswith("_") and k not in ("revision", "disponible")}, "profile": profile.get("validacionProceso"), "status": profile.get("estado"), "rules": RULESET}, default=str, sort_keys=True).encode()).hexdigest()
        if not force and not service.get("_revisionPendiente") and service.get("revision", {}).get("huella") == fingerprint:
            return service
        result.update(fecha=now(), huella=fingerprint)
        updated = db.servicios.find_one_and_update({"_id": identifier, "_version": service["_version"]}, {"$set": {"revision": result, "disponible": result["estado"] == "publicado"}, "$inc": {"_version": 1}}, return_document=ReturnDocument.AFTER)
        if updated is not None:
            audit(db, "servicios", identifier, result)
            db.servicios.update_one({"_id":identifier,"_version":updated["_version"]},{"$unset":{"_revisionPendiente":""}})
            return updated
    raise ValueError("El servicio cambió durante la revisión. Vuelve a intentarlo.")


def document_evidence(profile):
    from pathlib import Path
    from django.conf import settings
    from .pdf_validation import inspect_pdf
    documents = []
    for original in profile.get("documentos", []):
        document = dict(original)
        try:
            path = Path(settings.PRIVATE_DOCUMENT_ROOT) / (document["id"] + ".pdf")
            if not path.is_file() or path.stat().st_size > 5*1024*1024:
                raise ValueError("Archivo ausente o tamaño inválido.")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != document.get("sha256"):
                raise ValueError("El archivo no coincide con el recibido.")
            document.update(inspect_pdf(content), formatoComprobado=True)
        except (OSError, ValueError, KeyError):
            document["formatoComprobado"] = False
        documents.append(document)
    return documents


def review_profile(db, identifier, force=False):
    for _ in range(3):
        profile = db.profesionales.find_one({"_id": identifier})
        if profile is None:
            raise ValueError("Profesional no encontrado.")
        profile["documentos"] = document_evidence(profile)
        validation = db.validaciones.find_one({"_id": identifier}) or {}
        interview = validation.get("entrevista", {})
        result = profile_result(profile, interview)
        inputs = {"profile": {k:profile.get(k) for k in ("nombre", "profesion", "ubicacion", "resumen", "habilidades", "documentos")}, "interview": interview, "rules": RULESET}
        fingerprint = hashlib.sha256(json.dumps(inputs, default=str, sort_keys=True).encode()).hexdigest()
        if not force and not profile.get("_revisionPendiente") and profile.get("estado") == result["estado"] and validation.get("revision", {}).get("huella") == fingerprint:
            return profile
        result.update(fecha=now(), huella=fingerprint)
        changes = {"estado": result["estado"], "estadoTexto": result["etapa"], "validacionProceso": fingerprint,"_revisionPendiente":True,"documentos":profile["documentos"]}
        if "estadoAnteriorProceso" not in profile:
            changes["estadoAnteriorProceso"] = profile["estado"]
        updated = db.profesionales.find_one_and_update({"_id": identifier, "_version": profile["_version"]}, {"$set": changes, "$inc": {"_version": 1}}, return_document=ReturnDocument.AFTER)
        if updated is None:
            continue
        query = {"_id":identifier}
        if validation:
            query["_version"] = validation["_version"]
        try:
            saved = db.validaciones.update_one(query, {"$set":{"profesionalId":identifier,"estado":result["estado"],"etapa":result["etapa"],"revision":result},"$inc":{"_version":1}},upsert=not bool(validation))
        except Exception:
            raise
        if validation and not saved.matched_count:
            continue
        audit(db, "profesionales", identifier, result)
        for service in db.servicios.find({"profesionalId": identifier}, {"_id": 1}):
            review_service(db, service["_id"])
        db.profesionales.update_one({"_id":identifier,"_version":updated["_version"]},{"$unset":{"_revisionPendiente":""}})
        return updated
    raise ValueError("El profesional cambió durante la revisión. Vuelve a intentarlo.")


def reconcile_reviews(db):
    for profile in db.profesionales.find({"_revisionPendiente":True},{"_id":1}):
        review_profile(db,profile["_id"])
    for service in db.servicios.find({"_revisionPendiente":True},{"_id":1}):
        review_service(db,service["_id"])
