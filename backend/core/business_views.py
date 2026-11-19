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
def operations(request):
    data, db = payload(request), database()
    if data.get("accion") == "agendar":
        if not isinstance(data.get("solicitudId"), str):
            raise ValueError("Indica la solicitud.")
        agenda = book(db, request.skilly_user, data["solicitudId"], data.get("fecha"), data.get("claveOperacion"))
    else:
        if not isinstance(data.get("agendaId"), str):
            raise ValueError("Indica el agendamiento.")
        agenda = transition(db, request.skilly_user, data["agendaId"], data.get("version"), data.get("accion"), data.get("evaluacion"))
    return JsonResponse({"record": serialize(agenda), "version": agenda["_version"]})
