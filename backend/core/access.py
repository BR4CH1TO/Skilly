"""Sesiones opacas, autorización por rol y propiedad de perfiles.

Los contratos de interfaz describen reglas observables; el tipado no sustituye
la validación del servidor. Las operaciones económicas permanecen en prueba.
"""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse
    from pymongo.database import Database

import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import rotate_token

from .storage import database

COOKIE = "skilly_session"
SESSION_HOURS = 8


def digest(token: str) -> str:
    """Calcula la huella SHA-256 de un token de sesión.

    La base conserva la huella; la cookie contiene el token aleatorio original.

    Args:
        token: Token opaco recibido desde la cookie de sesión.

    Returns:
        Texto normalizado o identificador descrito.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: HttpRequest) -> dict[str, Any] | None:
    """Obtiene la cuenta activa de una sesión vigente.

    Comprueba vencimiento y cuenta activa; aprovecha la caché de la petición. No crea sesiones.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Resultado descrito.
    """
    if hasattr(request, "skilly_user"):
        return request.skilly_user
    token = request.COOKIES.get(COOKIE, "")
    if not token or len(token) > 128:
        return None
    db = database()
    session = db.sesiones.find_one(
        {"_id": digest(token), "expiresAt": {"$gt": datetime.now(timezone.utc)}}
    )
    if session is None:
        return None
    user = db.usuarios.find_one({"_id": session["usuarioId"], "activo": True})
    request.skilly_user = user
    return user


def access_required(*roles) -> Callable:
    """Construye un decorador de autorización por sesión y rol.

    Devuelve 401 sin sesión y 403 para un rol excluido. Sin roles admite cualquier cuenta
    autenticada.

    Args:
        *roles: Roles admitidos; una lista vacía exige solamente sesión.

    Returns:
        Decorador o vista envuelta que conserva los metadatos de la función original.
    """

    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = current_user(request)
            if user is None:
                return JsonResponse(
                    {"error": "Inicia sesión para continuar."}, status=401
                )
            if roles and user["rol"] not in roles:
                return JsonResponse(
                    {"error": "No tienes permiso para acceder a este recurso."},
                    status=403,
                )
            request.skilly_user = user
            return view(request, *args, **kwargs)

        return wrapped

    return decorate


def profile_access(view: Callable) -> Callable:
    """Restringe una vista al administrador o al titular del perfil.

    Verifica sesión y rol antes de comparar perfilId con el identificador solicitado.

    Args:
        view: Función de vista que será envuelta conservando metadatos con wraps.

    Returns:
        Decorador o vista envuelta que conserva los metadatos de la función original.
    """

    @wraps(view)
    @access_required("admin", "profesional")
    def wrapped(request, identifier, *args, **kwargs):
        user = request.skilly_user
        if user["rol"] != "admin" and user.get("perfilId") != identifier:
            return JsonResponse(
                {"error": "No tienes acceso a este perfil."}, status=403
            )
        return view(request, identifier, *args, **kwargs)

    return wrapped


def revoke_session(request: HttpRequest) -> None:
    """Elimina la sesión asociada a la cookie recibida.

    Borra solo la huella de esa cookie; no cierra otras sesiones de la cuenta.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        No devuelve un valor; consulta/actualiza solo lo indicado en la descripción.
    """
    token = request.COOKIES.get(COOKIE)
    if token:
        database().sesiones.delete_one({"_id": digest(token)})


def start_session(
    request: HttpRequest, response: HttpResponse, user: dict[str, Any]
) -> HttpResponse:
    """Emite una sesión opaca y rota el token CSRF.

    Revoca la sesión anterior de esta petición y guarda vencimiento de ocho horas. Usa HttpOnly
    y SameSite=Lax; Secure depende de DEBUG.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.
        response: Respuesta sobre la que se configura la cookie de sesión.
        user: Cuenta autenticada con _id, rol y perfilId cuando participa como empresa/profesional.

    Returns:
        Respuesta HTTP o adjunto con el contenido descrito.
    """
    revoke_session(request)
    token = secrets.token_urlsafe(32)
    database().sesiones.insert_one(
        {
            "_id": digest(token),
            "usuarioId": user["_id"],
            "expiresAt": datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS),
        }
    )
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        path="/",
    )
    rotate_token(request)
    return response


def setup_access(db: Database) -> None:
    """Crea índices únicos y de expiración para el acceso.

    La eliminación TTL de MongoDB es asíncrona; current_user verifica también el vencimiento en
    cada acceso.

    Args:
        db: Base MongoDB configurada; los ensayos deben usar una base temporal.

    Returns:
        No devuelve un valor; consulta/actualiza solo lo indicado en la descripción.
    """
    db.usuarios.create_index("correo", unique=True)
    db.usuarios.create_index(
        "perfilId",
        unique=True,
        partialFilterExpression={"perfilId": {"$type": "string"}},
    )
    db.sesiones.create_index("expiresAt", expireAfterSeconds=0)
    db.sesiones.create_index("usuarioId")
    db.intentos.create_index("expiresAt", expireAfterSeconds=0)
