"""Sesiones opacas revocables y permisos de los espacios privados."""
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


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request):
    if hasattr(request, "skilly_user"):
        return request.skilly_user
    token = request.COOKIES.get(COOKIE, "")
    if not token or len(token) > 128:
        return None
    db = database()
    session = db.sesiones.find_one({"_id": digest(token), "expiresAt": {"$gt": datetime.now(timezone.utc)}})
    if session is None:
        return None
    user = db.usuarios.find_one({"_id": session["usuarioId"], "activo": True})
    request.skilly_user = user
    return user


def access_required(*roles):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = current_user(request)
            if user is None:
                return JsonResponse({"error": "Inicia sesión para continuar."}, status=401)
            if roles and user["rol"] not in roles:
                return JsonResponse({"error": "No tienes permiso para acceder a este recurso."}, status=403)
            request.skilly_user = user
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


def profile_access(view):
    @wraps(view)
    @access_required("admin", "profesional")
    def wrapped(request, identifier, *args, **kwargs):
        user = request.skilly_user
        if user["rol"] != "admin" and user.get("perfilId") != identifier:
            return JsonResponse({"error": "No tienes acceso a este perfil."}, status=403)
        return view(request, identifier, *args, **kwargs)
    return wrapped


def revoke_session(request):
    token = request.COOKIES.get(COOKIE)
    if token:
        database().sesiones.delete_one({"_id": digest(token)})


def start_session(request, response, user):
    revoke_session(request)
    token = secrets.token_urlsafe(32)
    database().sesiones.insert_one({"_id": digest(token), "usuarioId": user["_id"], "expiresAt": datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)})
    response.set_cookie(COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True, secure=not settings.DEBUG, samesite="Lax", path="/")
    rotate_token(request)
    return response


def setup_access(db):
    db.usuarios.create_index("correo", unique=True)
    db.usuarios.create_index("perfilId", unique=True, partialFilterExpression={"perfilId": {"$type": "string"}})
    db.sesiones.create_index("expiresAt", expireAfterSeconds=0)
    db.sesiones.create_index("usuarioId")
    db.intentos.create_index("expiresAt", expireAfterSeconds=0)
