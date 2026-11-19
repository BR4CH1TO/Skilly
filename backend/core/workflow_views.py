"""API privada de respaldos, entrevista humana y disponibilidad.

Documenta propósito, contratos y límites de las operaciones del prototipo.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest
    from pymongo.database import Database

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from pymongo import ReturnDocument

from .storage import database, serialize
from .access import access_required, profile_access
from .views import database_errors, payload
from .workflow import (
    DOCUMENT_TYPES,
    audit,
    now,
    profile_checks,
    review_profile,
    review_service,
)


def existing_profile(db: Database, identifier: str) -> dict[str, Any]:
    """Busca un profesional existente para una operación de validación.

    No acredita titularidad por sí sola; el decorador de la vista debe autorizar antes de invocarla.

    Args:
        db: Base MongoDB configurada; los ensayos deben usar una base temporal.
        identifier: Identificador del registro solicitado; no concede acceso por sí solo.

    Returns:
        Objeto con los campos y significado indicados en la descripción.

    Raises:
        ValueError: Se incumple una de las precondiciones o reglas descritas.
    """
    profile = db.profesionales.find_one({"_id": identifier})
    if profile is None:
        raise ValueError("Profesional no encontrado.")
    return profile


def require_version(value: Any, expected: int) -> None:
    """Exige que la versión recibida coincida exactamente con la vigente.

    Rechaza bool, valores no enteros y versiones diferentes antes de realizar una escritura.

    Args:
        value: Valor recibido o calculado que se comprobará según las reglas descritas.
        expected: Versión vigente que debe igualar el valor recibido.

    Returns:
        No devuelve un valor; consulta/actualiza solo lo indicado en la descripción.

    Raises:
        ValueError: Se incumple una de las precondiciones o reglas descritas.
    """
    if type(value) is not int or value != expected:
        raise ValueError("El registro cambió. Recarga los datos antes de continuar.")


@never_cache
@require_http_methods(["GET", "POST"])
@database_errors
@access_required("admin")
def reviews(request: HttpRequest) -> JsonResponse:
    """Consulta auditoría o reintenta revisiones pendientes.

    GET/POST admin; GET exige recurso profesionales/servicios e id, y devuelve hasta 50
    revisiones. POST recupera pendientes sin registrar una entrevista no realizada.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    db = database()
    if request.method == "POST":
        for profile in db.profesionales.find({"_revisionPendiente": True}, {"_id": 1}):
            review_profile(db, profile["_id"])
        for service in db.servicios.find({"_revisionPendiente": True}, {"_id": 1}):
            review_service(db, service["_id"])
        return JsonResponse({"message": "Revisiones actualizadas."})
    resource, identifier = request.GET.get("recurso"), request.GET.get("id")
    if resource not in ("profesionales", "servicios") or not identifier:
        raise ValueError("Indica el recurso y su identificador.")
    docs = (
        db.revisiones.find({"recurso": resource, "registroId": identifier})
        .sort("fecha", -1)
        .limit(50)
    )
    return JsonResponse(
        {"results": [{k: v for k, v in doc.items() if k != "_id"} for doc in docs]}
    )


@never_cache
@require_http_methods(["POST"])
@database_errors
@access_required("admin")
def review(request: HttpRequest, resource: str, identifier: str) -> JsonResponse:
    """Repite explícitamente la revisión de un perfil o servicio.

    POST admin; resource debe ser profesionales o servicios. Fuerza el recálculo de reglas y
    devuelve el documento resultante.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.
        resource: Nombre lógico del recurso permitido para esta operación.
        identifier: Identificador del registro solicitado; no concede acceso por sí solo.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    if resource not in ("profesionales", "servicios"):
        raise ValueError("Recurso de revisión no válido.")
    db = database()
    result = (
        review_profile(db, identifier, force=True)
        if resource == "profesionales"
        else review_service(db, identifier, force=True)
    )
    return JsonResponse({"record": serialize(result)})


@never_cache
@require_http_methods(["POST"])
@database_errors
@profile_access
def documents(request: HttpRequest, identifier: str) -> JsonResponse:
    """Recibe un respaldo PDF privado y revisa el perfil.

    POST multipart de titular/admin: version, tipo cv/formacion y archivo de hasta 5 MiB.
    Verifica estructura, crea archivo con permisos 0600 y guarda hash. Si falla el guardado
    retira el archivo recién creado; 201 al completar.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.
        identifier: Identificador del registro solicitado; no concede acceso por sí solo.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    import hashlib

    db = database()
    profile = existing_profile(db, identifier)
    try:
        version = int(request.POST.get("version", ""))
    except ValueError:
        raise ValueError("Falta la versión del profesional.") from None
    require_version(version, profile["_version"])
    kind, uploaded = request.POST.get("tipo"), request.FILES.get("archivo")
    if kind not in DOCUMENT_TYPES or uploaded is None:
        raise ValueError("Selecciona el tipo y el archivo PDF.")
    if uploaded.size > 5 * 1024 * 1024:
        raise ValueError("El tamaño máximo es 5 MiB.")
    content = uploaded.read()
    from .pdf_validation import inspect_pdf

    inspection = inspect_pdf(content)
    identifier_file = str(uuid4())
    root = Path(settings.PRIVATE_DOCUMENT_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (identifier_file + ".pdf")
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as output:
        output.write(content)
    metadata = {
        "id": identifier_file,
        "tipo": kind,
        "nombre": Path(uploaded.name).name[:150],
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "fecha": now(),
        "formatoComprobado": True,
        "autenticidad": "no_verificada",
        **inspection,
    }
    attachments = [d for d in profile.get("documentos", []) if d["tipo"] != kind] + [
        metadata
    ]
    try:
        updated = db.profesionales.find_one_and_update(
            {"_id": identifier, "_version": version},
            {"$set": {"documentos": attachments}, "$inc": {"_version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            path.unlink(missing_ok=True)
            raise ValueError(
                "El perfil cambió durante la carga. Recarga e inténtalo nuevamente."
            )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    db.profesionales.update_one(
        {"_id": identifier}, {"$set": {"_revisionPendiente": True}}
    )
    review_profile(db, identifier)
    return JsonResponse({"document": metadata}, status=201)


@never_cache
@require_http_methods(["GET"])
@database_errors
@profile_access
def download(request: HttpRequest, identifier: str, file_id: str) -> FileResponse:
    """Descarga un respaldo profesional autorizado y con hash correcto.

    GET titular/admin; documento o archivo ausente: 404; hash diferente: 409; cuenta ajena: 403.
    Devuelve PDF como adjunto con nosniff.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.
        identifier: Identificador del registro solicitado; no concede acceso por sí solo.
        file_id: Identificador del PDF previamente asociado al expediente.

    Returns:
        Flujo del archivo PDF autorizado como adjunto.
    """
    profile = existing_profile(database(), identifier)
    document = next(
        (d for d in profile.get("documentos", []) if d["id"] == str(file_id)), None
    )
    if document is None:
        return JsonResponse({"error": "Documento no encontrado."}, status=404)
    path = Path(settings.PRIVATE_DOCUMENT_ROOT) / (document["id"] + ".pdf")
    if not path.is_file():
        return JsonResponse({"error": "Archivo no disponible."}, status=404)
    import hashlib

    if hashlib.sha256(path.read_bytes()).hexdigest() != document.get("sha256"):
        return JsonResponse(
            {
                "error": "El archivo no coincide con el documento registrado. Vuelve a cargarlo."
            },
            status=409,
        )
    response = FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=document["nombre"],
        content_type="application/pdf",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
@require_http_methods(["POST"])
@database_errors
@access_required("admin")
def interview(request: HttpRequest, identifier: str) -> JsonResponse:
    """Registra una entrevista humana con responsable y observaciones.

    POST admin; JSON version, resultado, responsable, observaciones, enlace HTTPS y fecha con
    zona. Exige requisitos automáticos completos. Fecha futura solo para agendada; un resultado
    exige entrevista ya ocurrida. Conflicto concurrente: 409.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.
        identifier: Identificador del registro solicitado; no concede acceso por sí solo.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    db = database()
    profile = existing_profile(db, identifier)
    data = payload(request)
    validation = db.validaciones.find_one({"_id": identifier})
    if validation is None:
        raise ValueError(
            "Ejecuta la revisión automática antes de agendar la entrevista."
        )
    require_version(data.get("version"), validation["_version"])
    if not all(c["resultado"] == "aprobado" for c in profile_checks(profile)):
        raise ValueError("Primero deben completarse todos los requisitos automáticos.")
    outcome = data.get("resultado")
    if outcome not in ("agendada", "aprobada", "segunda", "rechazada"):
        raise ValueError("Resultado de entrevista no válido.")
    responsible, comments = data.get("responsable", ""), data.get("observaciones", "")
    if (
        not isinstance(responsible, str)
        or len(responsible.strip()) < 3
        or not isinstance(comments, str)
        or len(comments.strip()) < 10
    ):
        raise ValueError(
            "Indica responsable y observaciones de al menos 10 caracteres."
        )
    url = data.get("enlace", "")
    if (
        not isinstance(url, str)
        or urlparse(url).scheme != "https"
        or not urlparse(url).hostname
    ):
        raise ValueError("Indica un enlace HTTPS para la entrevista online.")
    try:
        date = datetime.fromisoformat(data.get("fecha", "").replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError()
    except (ValueError, AttributeError):
        raise ValueError("Indica la fecha de entrevista con su zona horaria.") from None
    if outcome == "agendada" and date <= datetime.now(timezone.utc):
        raise ValueError("Una entrevista agendada debe tener fecha futura.")
    if outcome != "agendada" and date > datetime.now(timezone.utc):
        raise ValueError(
            "No se puede registrar resultado de una entrevista que aún no ocurrió."
        )
    entry = {
        "resultado": outcome,
        "responsable": responsible.strip(),
        "observaciones": comments.strip(),
        "enlace": url,
        "fecha": date.isoformat(),
        "registradaEn": now(),
        "registradoPor": request.skilly_user["_id"],
    }
    updated = db.validaciones.find_one_and_update(
        {"_id": identifier, "_version": data["version"]},
        {"$set": {"entrevista": entry}, "$inc": {"_version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        return JsonResponse(
            {"error": "La entrevista cambió. Recarga los datos."}, status=409
        )
    audit(
        db,
        "profesionales",
        identifier,
        {"tipo": "entrevista", **entry},
        actor=request.skilly_user["nombre"],
    )
    db.profesionales.update_one(
        {"_id": identifier}, {"$set": {"_revisionPendiente": True}}
    )
    review_profile(db, identifier)
    return JsonResponse({"message": "Entrevista registrada y proceso recalculado."})


@never_cache
@require_http_methods(["PUT"])
@database_errors
@profile_access
def availability(request: HttpRequest, identifier: str) -> JsonResponse:
    """Guarda horarios futuros propios y los registra en auditoría.

    PUT titular/admin; JSON version y horarios. Admite hasta 100 dentro de 180 días,
    normaliza/deduplica y controla versión. Conflicto durante escritura: 409; datos inválidos:
    400.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.
        identifier: Identificador del registro solicitado; no concede acceso por sí solo.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    from datetime import timedelta
    from .business import instant, iso

    db = database()
    profile = existing_profile(db, identifier)
    data = payload(request)
    require_version(data.get("version"), profile["_version"])
    slots = data.get("horarios")
    if not isinstance(slots, list) or len(slots) > 100:
        raise ValueError("Introduce hasta 100 horarios futuros.")
    dates = [instant(s) for s in slots]
    today = datetime.now(timezone.utc)
    if any(not today < d <= today + timedelta(days=180) for d in dates):
        raise ValueError("Los horarios deben estar dentro de los próximos 180 días.")
    normalized = sorted({iso(d) for d in dates})
    updated = db.profesionales.find_one_and_update(
        {"_id": identifier, "_version": profile["_version"]},
        {
            "$set": {"disponibilidad": normalized, "_revisionPendiente": True},
            "$inc": {"_version": 1},
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        return JsonResponse(
            {"error": "El perfil cambió. Recarga para continuar."}, status=409
        )
    review_profile(db, identifier)
    audit(
        db,
        "profesionales",
        identifier,
        {
            "tipo": "disponibilidad",
            "resultado": "actualizada",
            "observaciones": f"{len(normalized)} horarios futuros publicados.",
            "fecha": now(),
        },
        actor=request.skilly_user["nombre"],
    )
    return JsonResponse(
        {"message": "Disponibilidad guardada en MongoDB.", "horarios": normalized}
    )
