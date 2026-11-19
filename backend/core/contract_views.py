"""API de acuerdos, evidencias privadas, atención y configuración.

Documenta propósito, contratos y límites de las operaciones del prototipo.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest
    from pymongo.database import Database

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


def owned(db: Database, user: dict[str, Any], identifier: str) -> dict[str, Any]:
    """Obtiene un acuerdo accesible por administración o participante.

    Un identificador válido no basta para acceder: se comprueba la relación con la cuenta
    autenticada.

    Args:
        db: Base MongoDB configurada; los ensayos deben usar una base temporal.
        user: Cuenta autenticada con _id, rol y perfilId cuando participa como empresa/profesional.
        identifier: Identificador del registro solicitado; no concede acceso por sí solo.

    Returns:
        Objeto con los campos y significado indicados en la descripción.

    Raises:
        ValueError: Se incumple una de las precondiciones o reglas descritas.
    """
    c = db.contratos.find_one({"_id": identifier})
    if not c or not engine.access(user, c):
        raise ValueError("Acuerdo no disponible para esta cuenta.")
    return c


@never_cache
@require_http_methods(["GET"])
@database_errors
def policy(request: HttpRequest) -> JsonResponse:
    """Publica versión y reglas contractuales sin habilitar cobros.

    GET público; excluye el HTML completo de la instantánea e informa
    pagosRealesHabilitados=False y cantidad de feriados configurados.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    p = engine.terms_snapshot()
    p.pop("documento")
    return JsonResponse(
        {
            **p,
            "pagosRealesHabilitados": False,
            "motivos": [
                "No hay proveedor de pagos integrado.",
                "Identificación del operador y revisión jurídica pendientes.",
            ],
            "feriadosCargados": database().feriados.count_documents({}),
            "advertenciaCalendario": "Configurar los feriados legales de cada año antes de operar comercialmente.",
        }
    )


@never_cache
@require_http_methods(["GET", "POST"])
@database_errors
@access_required("admin", "empresa", "profesional")
def agreements(request: HttpRequest) -> JsonResponse:
    """Lista acuerdos autorizados o crea uno desde una reserva.

    GET/POST autenticado; administración ve todos y cada participante solo los propios. GET
    pagina 50 y reconcilia pendientes/avisos; POST delega en create, que exige empresa.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    db = database()
    user = request.skilly_user
    reconcile(db)
    engine.monitor(db)
    from .account_controls import project_restrictions

    project_restrictions(db)
    if request.method == "POST":
        result = engine.create(db, user, payload(request))
        return JsonResponse({"record": engine.summary(result)}, status=201)
    query = (
        {}
        if user["rol"] == "admin"
        else {
            "empresaId" if user["rol"] == "empresa" else "profesionalId": user[
                "perfilId"
            ]
        }
    )
    try:
        offset = max(0, int(request.GET.get("offset", "0")))
    except ValueError:
        raise ValueError("Paginación inválida.") from None
    records = list(
        db.contratos.find(query)
        .sort([("creadoEn", -1), ("_id", 1)])
        .skip(offset)
        .limit(50)
    )
    return JsonResponse(
        {
            "records": [engine.summary(c) for c in records],
            "total": db.contratos.count_documents(query),
            "offset": offset,
            "limit": 50,
            "rol": user["rol"],
            "usuarioId": user["_id"],
        }
    )


@never_cache
@require_http_methods(["GET", "POST"])
@database_errors
@access_required("admin", "empresa", "profesional")
def agreement(request: HttpRequest, identifier: str) -> JsonResponse:
    """Consulta o cambia un acuerdo accesible para la cuenta.

    GET/POST autenticado por identifier; exige pertenencia antes de consultar o ejecutar mutate.
    La salida usa summary, sin comandos internos.

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
    owned(db, request.skilly_user, identifier)
    if request.method == "GET":
        c = owned(db, request.skilly_user, identifier)
    else:
        c = engine.mutate(db, request.skilly_user, identifier, payload(request))
    return JsonResponse({"record": engine.summary(c)})


@never_cache
@require_http_methods(["GET"])
@database_errors
@access_required("admin", "empresa", "profesional")
def accepted_terms(request: HttpRequest, identifier: str) -> HttpResponse:
    """Descarga el HTML de condiciones aceptado en un acuerdo propio.

    GET autenticado; usa la instantánea conservada en el acuerdo, no el texto público
    actualizado. Devuelve adjunto HTML con nosniff.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.
        identifier: Identificador del registro solicitado; no concede acceso por sí solo.

    Returns:
        Respuesta HTTP o adjunto con el contenido descrito.
    """
    c = owned(database(), request.skilly_user, identifier)
    response = HttpResponse(
        c["politica"]["documento"], content_type="text/html; charset=utf-8"
    )
    response["Content-Disposition"] = (
        'attachment; filename="condiciones-' + identifier + '.html"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
@require_http_methods(["POST"])
@database_errors
@access_required("admin", "empresa", "profesional")
def upload(request: HttpRequest, identifier: str) -> JsonResponse:
    """Adjunta evidencia PDF privada al expediente contractual.

    POST multipart: archivo, version, claveOperacion e hitoId opcional. Máximo 50
    archivos/acuerdo y 5 MiB/PDF; conserva hash y permisos 0600. Retira el archivo nuevo ante
    rechazo o reintento idempotente sin adjunto nuevo.

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
    c = owned(db, request.skilly_user, identifier)
    if len(c.get("archivos", [])) >= 50:
        raise ValueError("Máximo de 50 archivos por acuerdo.")
    f = request.FILES.get("archivo")
    if not f or f.size > 5 * 1024 * 1024:
        raise ValueError("Adjunta un PDF de hasta 5 MiB.")
    from .pdf_validation import inspect_pdf

    content = f.read()
    inspect_pdf(content)
    root = Path(settings.PRIVATE_DOCUMENT_ROOT) / "contratos"
    root.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid4())
    path = root / (file_id + ".pdf")
    path.write_bytes(content)
    path.chmod(0o600)
    meta = {
        "id": file_id,
        "nombre": Path(f.name).name[:150],
        "sha256": hashlib.sha256(content).hexdigest(),
        "fecha": engine.stamp(),
        "autorId": request.skilly_user["_id"],
    }
    try:
        data = {
            "accion": "adjuntar",
            "archivoSha256": meta["sha256"],
            "version": int(request.POST.get("version", "0")),
            "claveOperacion": request.POST.get("claveOperacion", ""),
            "hitoId": request.POST.get("hitoId"),
        }
        result = engine.mutate(
            db, request.skilly_user, identifier, data, file_meta=meta
        )
        if not any(a["id"] == file_id for a in result.get("archivos", [])):
            path.unlink(missing_ok=True)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return JsonResponse({"record": engine.summary(result)}, status=201)


@never_cache
@require_http_methods(["GET"])
@database_errors
@access_required("admin", "empresa", "profesional")
def evidence(request: HttpRequest, identifier: str, file_id: str) -> FileResponse:
    """Descarga evidencia contractual tras comprobar acceso e integridad.

    GET autenticado por identifier/file_id. Verifica participación, metadatos, existencia y
    SHA-256 antes de transmitir el PDF.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.
        identifier: Identificador del registro solicitado; no concede acceso por sí solo.
        file_id: Identificador del PDF previamente asociado al expediente.

    Returns:
        Flujo del archivo PDF autorizado como adjunto.
    """
    c = owned(database(), request.skilly_user, identifier)
    f = next((x for x in c.get("archivos", []) if x["id"] == str(file_id)), None)
    if not f:
        raise ValueError("Archivo no encontrado.")
    p = Path(settings.PRIVATE_DOCUMENT_ROOT) / "contratos" / (f["id"] + ".pdf")
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
        raise ValueError("Archivo no disponible o integridad incorrecta.")
    return FileResponse(
        p.open("rb"),
        as_attachment=True,
        filename=f["nombre"],
        content_type="application/pdf",
    )


def reconcile(db: Database) -> None:
    """Recupera acuerdos y proyecciones pendientes de una interrupción.

    Completa desde _contratoPendiente y _syncPendiente, respetando el agregado fuente. No
    fabrica nuevas aceptaciones.

    Args:
        db: Base MongoDB configurada; los ensayos deben usar una base temporal.

    Returns:
        No devuelve un valor; consulta/actualiza solo lo indicado en la descripción.
    """
    for c in db.contratos.find({"_syncPendiente": True}):
        engine.project(db, c)
    for agenda in db.agendas.find({"_contratoPendiente": {"$exists": True}}):
        c = agenda["_contratoPendiente"]
        db.contratos.update_one({"_id": c["_id"]}, {"$setOnInsert": c}, upsert=True)
        engine.project(db, c)
        db.agendas.update_one(
            {"_id": agenda["_id"], "_contratoId": c["_id"]},
            {"$unset": {"_contratoPendiente": ""}},
        )


@never_cache
@require_http_methods(["GET", "POST"])
@database_errors
@access_required("admin")
def holidays(request: HttpRequest) -> JsonResponse:
    """Consulta o mantiene el calendario configurado de días inhábiles.

    GET/POST admin; JSON fecha ISO, nombre o eliminar=True. Valida la fecha antes de escribir;
    devuelve calendario ordenado. No importa automáticamente feriados externos.

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
        from datetime import date

        d = payload(request)
        day = engine.text(d, "fecha", 10, 10)
        try:
            date.fromisoformat(day)
        except ValueError:
            raise ValueError("Fecha de feriado inválida.") from None
        if d.get("eliminar") is True:
            db.feriados.delete_one({"_id": day})
        else:
            db.feriados.update_one(
                {"_id": day},
                {"$set": {"nombre": engine.text(d, "nombre", 3, 150)}},
                upsert=True,
            )
    return JsonResponse(
        {
            "records": [
                {"fecha": x["_id"], "nombre": x["nombre"]}
                for x in db.feriados.find().sort("_id", 1)
            ]
        }
    )


@never_cache
@require_http_methods(["GET", "POST"])
@database_errors
@access_required("admin", "empresa", "profesional")
def attention(request: HttpRequest) -> JsonResponse:
    """Gestiona peticiones privadas de datos y atención de cuentas.

    GET/POST autenticado; titular consulta/crea/reabre, administración responde. Verifica
    propietario, tipo y versión; conserva historial y devuelve hasta 100 registros autorizados.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    db = database()
    u = request.skilly_user
    if request.method == "POST":
        d = payload(request)
        if d.get("id"):
            r = (
                db.atencion.find_one({"_id": d["id"]})
                if isinstance(d["id"], str)
                else None
            )
            if not r or (u["rol"] != "admin" and r["usuarioId"] != u["_id"]):
                raise ValueError("Solicitud no disponible.")
            if type(d.get("version")) is not int or d["version"] != r["_version"]:
                raise ValueError("La solicitud cambió. Recarga.")
            action = d.get("accion")
            if action == "responder" and u["rol"] == "admin":
                changes = {
                    "estado": "respondida",
                    "respuesta": engine.text(d, "detalle", 10),
                    "respondidoEn": engine.stamp(),
                    "responsableId": u["_id"],
                }
            elif (
                action == "reabrir"
                and u["rol"] != "admin"
                and r["estado"] == "respondida"
            ):
                changes = {
                    "estado": "abierta",
                    "motivoRevision": engine.text(d, "detalle", 10),
                }
            else:
                raise ValueError("Acción no permitida.")
            if not db.atencion.update_one(
                {"_id": r["_id"], "_version": r["_version"]},
                {
                    "$set": changes,
                    "$inc": {"_version": 1},
                    "$push": {
                        "historial": {
                            "actorId": u["_id"],
                            "fecha": engine.stamp(),
                            "accion": action,
                            "detalle": engine.text(d, "detalle", 10),
                        }
                    },
                },
            ).matched_count:
                raise ValueError("La solicitud cambió.")
        else:
            kind = d.get("tipo")
            if kind not in (
                "acceso",
                "rectificacion",
                "supresion",
                "portabilidad",
                "seguridad",
                "cuenta",
                "consulta",
            ):
                raise ValueError("Tipo de solicitud inválido.")
            t = engine.stamp()
            db.atencion.insert_one(
                {
                    "_id": str(uuid4()),
                    "_version": 1,
                    "usuarioId": u["_id"],
                    "nombre": u["nombre"],
                    "tipo": kind,
                    "detalle": engine.text(d, "detalle", 10),
                    "fecha": t,
                    "estado": "abierta",
                    "recepcionRegistradaEn": t,
                    "historial": [],
                }
            )
    query = {} if u["rol"] == "admin" else {"usuarioId": u["_id"]}
    return JsonResponse(
        {
            "records": [
                {
                    **{k: v for k, v in r.items() if not k.startswith("_")},
                    "id": r["_id"],
                    "version": r["_version"],
                }
                for r in db.atencion.find(query).sort("fecha", -1).limit(100)
            ]
        }
    )


@never_cache
@require_http_methods(["GET", "POST"])
@database_errors
@access_required("admin")
def operator(request: HttpRequest) -> JsonResponse:
    """Conserva antecedentes declarados del operador comercial.

    GET/POST admin; JSON razonSocial/rut/domicilio/correo. Valida correo; no verifica legalmente
    el RUT. Siempre devuelve pagosRealesHabilitados=False.

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
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError

        d = payload(request)
        record = {
            k: engine.text(d, k, 3, 250)
            for k in ("razonSocial", "rut", "domicilio", "correo")
        }
        try:
            validate_email(record["correo"])
        except ValidationError:
            raise ValueError("Correo oficial inválido.") from None
        # El RUT se conserva como antecedente; no se presenta como identidad verificada.
        record.update(
            actualizadoEn=engine.stamp(),
            actorId=request.skilly_user["_id"],
            verificado=False,
        )
        db.configuracion.update_one({"_id": "operador"}, {"$set": record}, upsert=True)
    result = db.configuracion.find_one({"_id": "operador"}) or {}
    result.pop("_id", None)
    return JsonResponse({"record": result, "pagosRealesHabilitados": False})


@never_cache
@require_http_methods(["GET", "POST"])
@database_errors
@access_required("admin")
def controls(request: HttpRequest) -> JsonResponse:
    """Registra o levanta restricciones comerciales motivadas.

    GET/POST admin; exige cuenta no administrativa y controlVersion vigente. Conserva motivo y
    aviso en atención; mantiene acceso a acuerdos y reclamaciones. Proyecta la restricción al
    perfil.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    db = database()
    actor = request.skilly_user
    if request.method == "POST":
        d = payload(request)
        u = (
            db.usuarios.find_one({"_id": d.get("usuarioId")})
            if isinstance(d.get("usuarioId"), str)
            else None
        )
        if not u or u["rol"] == "admin":
            raise ValueError("Selecciona una cuenta de empresa o profesional.")
        version = u.get("controlVersion", 0)
        if type(d.get("version")) is not int or d["version"] != version:
            raise ValueError("La cuenta cambió. Recarga antes de continuar.")
        detail = engine.text(d, "detalle", 20)
        restriction = (
            None
            if d.get("levantar") is True
            else {
                "motivo": detail,
                "fecha": engine.stamp(),
                "desde": engine.stamp()
                if d.get("urgente") is True
                else engine.business_due(db, engine.stamp(), 3),
                "urgente": d.get("urgente") is True,
                "actorId": actor["_id"],
            }
        )
        q = (
            {"_id": u["_id"], "controlVersion": version}
            if "controlVersion" in u
            else {"_id": u["_id"], "controlVersion": {"$exists": False}}
        )
        if not db.usuarios.update_one(
            q,
            {
                "$set": {"restriccionComercial": restriction},
                "$inc": {"controlVersion": 1},
            },
        ).matched_count:
            raise ValueError("Otro administrador modificó la cuenta.")
        db.atencion.insert_one(
            {
                "_id": str(uuid4()),
                "_version": 1,
                "usuarioId": u["_id"],
                "nombre": u["nombre"],
                "tipo": "cuenta",
                "detalle": (
                    "Restricción levantada. "
                    if restriction is None
                    else "Restricción comercial notificada. "
                )
                + detail,
                "fecha": engine.stamp(),
                "estado": "respondida",
                "respuesta": "Puedes solicitar revisión y aportar antecedentes. Tus acuerdos, pagos e información permanecen accesibles.",
                "responsableId": actor["_id"],
                "historial": [
                    {
                        "accion": "control_cuenta",
                        "actorId": actor["_id"],
                        "fecha": engine.stamp(),
                        "detalle": detail,
                    }
                ],
            }
        )
    from .account_controls import project_restrictions

    project_restrictions(db)
    return JsonResponse(
        {
            "records": [
                {
                    "id": u["_id"],
                    "nombre": u["nombre"],
                    "rol": u["rol"],
                    "version": u.get("controlVersion", 0),
                    "restriccion": u.get("restriccionComercial"),
                }
                for u in db.usuarios.find(
                    {"rol": {"$in": ["empresa", "profesional"]}}
                ).limit(500)
            ]
        }
    )
