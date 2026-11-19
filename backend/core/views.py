"""API administrativa y traducción uniforme de errores esperados.

Documenta propósito, contratos y límites de las operaciones del prototipo.
"""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest
    from pymongo.database import Database

import json
import logging
from functools import wraps

from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from pymongo.errors import DuplicateKeyError, PyMongoError

from .storage import (
    COLLECTIONS,
    database,
    record_id,
    serialize,
    to_document,
    validate_record,
    valid_identifier,
)
from .workflow import review_profile, review_service
from .access import access_required

logger = logging.getLogger(__name__)


def apply_review(
    db: Database, resource: str, document: dict[str, Any]
) -> dict[str, Any]:
    """Ejecuta la revisión aplicable después de guardar un registro.

    Perfiles y servicios delegan en workflow; otros recursos devuelven el documento sin revisión
    adicional.

    Args:
        db: Base MongoDB configurada; los ensayos deben usar una base temporal.
        resource: Nombre lógico del recurso permitido para esta operación.
        document: Documento almacenado, con _id y _version internos cuando corresponde.

    Returns:
        Objeto con los campos y significado indicados en la descripción.

    Raises:
        ValueError: Se incumple una de las precondiciones o reglas descritas.
    """
    if resource == "profesionales":
        return review_profile(db, document["_id"])
    if resource == "servicios":
        return review_service(db, document["_id"])
    return document


def database_errors(view: Callable) -> Callable:
    """Convierte errores esperados en respuestas HTTP controladas.

    DuplicateKeyError produce 409; ValueError produce 400; PyMongoError produce 503 y registro
    interno del incidente. No envía trazas al cliente ni captura todos los errores de
    programación.

    Args:
        view: Función de vista que será envuelta conservando metadatos con wraps.

    Returns:
        Decorador o vista envuelta que conserva los metadatos de la función original.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except DuplicateKeyError:
            return JsonResponse(
                {"error": "El registro ya existe o duplica una relación u horario."},
                status=409,
            )
        except ValueError as error:
            return JsonResponse({"error": str(error)}, status=400)
        except PyMongoError:
            logger.exception("Error de acceso a MongoDB")
            return JsonResponse(
                {"error": "No se pudo acceder a MongoDB. Comprueba la conexión."},
                status=503,
            )

    return wrapped


def payload(request: HttpRequest) -> dict[str, Any]:
    """Extrae un objeto JSON de la petición.

    Requiere application/json, JSON bien formado y objeto como raíz; rechaza listas y escalares.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Objeto con los campos y significado indicados en la descripción.

    Raises:
        ValueError: Se incumple una de las precondiciones o reglas descritas.
    """
    if request.content_type != "application/json":
        raise ValueError("Se requiere contenido JSON.")
    try:
        value = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("JSON inválido.") from None
    if not isinstance(value, dict):
        raise ValueError("Se requiere un objeto JSON.")
    return value


@never_cache
@require_http_methods(["GET"])
@database_errors
@access_required("admin")
def state(request: HttpRequest) -> JsonResponse:
    """Entrega el estado agrupado para la administración.

    GET restringido a admin; reconcilia proyecciones y revisiones y expira solicitudes. La
    agrupación es una respuesta de lectura, no un documento monolítico persistido.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    # Esta respuesta agrupa lecturas para la interfaz; no se guarda como documento.
    db = database()
    from .business import reconcile, expire_requests

    reconcile(db)
    from .workflow import reconcile_reviews

    reconcile_reviews(db)
    expire_requests(db)
    result, versions = {}, {}
    for key, collection in COLLECTIONS.items():
        documents = list(db[collection].find().sort("_id", 1))
        if collection == "historial":
            documents.sort(key=lambda d: d["fecha"], reverse=True)
        result[key] = [serialize(doc) for doc in documents]
        versions[key] = {doc["_id"]: doc["_version"] for doc in documents}
    return JsonResponse(
        {"state": result, "versions": versions, "csrfToken": get_token(request)}
    )


@never_cache
@require_http_methods(["GET", "POST", "PUT"])
@database_errors
@access_required("admin")
def records(
    request: HttpRequest, resource: str, identifier: str = None
) -> JsonResponse:
    """Consulta o guarda registros administrativos con control de versión.

    GET paginado 1–100; POST crea; PUT exige identidad y versión conservadas. No permite editar
    directamente validaciones, agendas, pagos ni resultados automáticos. Devuelve 404 para
    registro/recurso ausente, 409 por concurrencia y 403 para recursos gestionados por
    operaciones de negocio.

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
    if resource not in COLLECTIONS.values() or (
        identifier is not None and not valid_identifier(identifier)
    ):
        return JsonResponse({"error": "Recurso no encontrado."}, status=404)
    db = database()
    collection = db[resource]
    if request.method == "GET":
        if identifier is not None:
            document = collection.find_one({"_id": identifier})
            if document is None:
                return JsonResponse({"error": "Registro no encontrado."}, status=404)
            return JsonResponse(
                {"record": serialize(document), "version": document["_version"]}
            )
        try:
            limit = min(max(int(request.GET.get("limit", 25)), 1), 100)
            offset = max(int(request.GET.get("offset", 0)), 0)
        except ValueError:
            raise ValueError("limit y offset deben ser números enteros.") from None
        documents = collection.find().sort("_id", 1).skip(offset).limit(limit)
        return JsonResponse(
            {
                "results": [serialize(doc) for doc in documents],
                "limit": limit,
                "offset": offset,
            }
        )
    if (request.method == "POST" and identifier is not None) or (
        request.method == "PUT" and identifier is None
    ):
        return JsonResponse({"error": "Método no permitido en esta ruta."}, status=405)
    if resource in ("validaciones", "agendas", "pagos"):
        return JsonResponse(
            {
                "error": "Este registro se gestiona mediante su operación de negocio, no mediante edición directa."
            },
            status=403,
        )
    data = payload(request)
    record = data.get("record")
    if isinstance(record, dict):
        existing = collection.find_one({"_id": identifier}) if identifier else None
        protected = (
            ("documentos", "validacionProceso", "estadoAnteriorProceso", "estadoTexto")
            if resource == "profesionales"
            else ("revision",)
            if resource == "servicios"
            else ()
        )
        for field in protected:
            if field in record and (
                existing is None or record[field] != existing.get(field)
            ):
                raise ValueError(
                    f"El campo {field} solo puede cambiarse mediante su proceso automático."
                )
            if existing and field in existing:
                record[field] = existing[field]
        if resource == "profesionales":
            if record.get("estado") != (
                existing.get("estado") if existing else "revision"
            ):
                raise ValueError("El estado del profesional lo calcula el sistema.")
        if resource == "servicios":
            record["disponible"] = False
    validate_record(resource, record, db)
    if request.method == "POST":
        if resource == "solicitudes":
            service = db.servicios.find_one({"_id": record["servicioId"]})
            if (
                not service
                or not service.get("disponible")
                or service["profesionalId"] != record["profesionalId"]
            ):
                raise ValueError(
                    "El servicio debe estar publicado y corresponder al profesional indicado."
                )
        document = to_document(resource, record)
        if resource in ("profesionales", "servicios"):
            document["_revisionPendiente"] = True
        collection.insert_one(document)
        document = apply_review(db, resource, document)
        return JsonResponse(
            {"record": serialize(document), "version": document["_version"]}, status=201
        )
    if record_id(record) != identifier:
        raise ValueError("No se puede cambiar el identificador de un registro.")
    version = data.get("version")
    if type(version) is not int or version < 1:
        raise ValueError("Se requiere una versión válida del registro.")
    document = to_document(resource, record, version + 1)
    if resource in ("profesionales", "servicios"):
        document["_revisionPendiente"] = True
    result = collection.replace_one({"_id": identifier, "_version": version}, document)
    if not result.matched_count:
        return JsonResponse(
            {
                "error": "Este registro cambió en otra pestaña. Recarga los datos antes de continuar."
            },
            status=409,
        )
    document = apply_review(db, resource, document)
    return JsonResponse(
        {"record": serialize(document), "version": document["_version"]}
    )
