"""Adaptador HTTP para reservas y operaciones de seguimiento.

Documenta propósito, contratos y límites de las operaciones del prototipo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .views import database_errors, payload
from .access import access_required
from .storage import database, serialize
from .business import book, transition


@never_cache
@require_http_methods(["POST"])
@database_errors
@access_required("admin", "empresa", "profesional")
def operations(request: HttpRequest) -> JsonResponse:
    """Enruta reservas y operaciones de seguimiento al dominio.

    POST autenticado; accion=agendar exige solicitudId/fecha/claveOperacion, otras acciones
    agendaId/version. book y transition verifican titularidad, estado y permisos adicionales.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    data, db = payload(request), database()
    if data.get("accion") == "agendar":
        if not isinstance(data.get("solicitudId"), str):
            raise ValueError("Indica la solicitud.")
        agenda = book(
            db,
            request.skilly_user,
            data["solicitudId"],
            data.get("fecha"),
            data.get("claveOperacion"),
        )
    else:
        if not isinstance(data.get("agendaId"), str):
            raise ValueError("Indica el agendamiento.")
        agenda = transition(
            db,
            request.skilly_user,
            data["agendaId"],
            data.get("version"),
            data.get("accion"),
            data.get("evaluacion"),
        )
    return JsonResponse({"record": serialize(agenda), "version": agenda["_version"]})
