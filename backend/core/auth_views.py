import hashlib
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .access import COOKIE, access_required, current_user, digest, revoke_session, start_session
from .storage import database
from .views import database_errors, payload
from .workflow import review_profile

# Hash válido para igualar el trabajo cuando la cuenta no existe.
DUMMY_HASH = make_password("non-login-placeholder")


def user_summary(user):
    return {"nombre": user["nombre"], "correo": user["correo"], "rol": user["rol"]}


def destination(user):
    return "/panel/" if user["rol"] == "admin" else "/cuenta/"


def normalized_email(value):
    if not isinstance(value, str) or len(value) > 254:
        raise ValueError("Introduce un correo válido.")
    value = value.strip().casefold()
    try:
        validate_email(value)
    except ValidationError:
        raise ValueError("Introduce un correo válido.") from None
    return value


def valid_password(value):
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError("La contraseña debe tener entre 8 y 128 caracteres.")
    try:
        validate_password(value)
    except ValidationError as error:
        raise ValueError(" ".join(error.messages)) from None


def rate_limit(request, scope, email=""):
    key = hashlib.sha256((scope + ":" + request.META.get("REMOTE_ADDR", "") + ":" + email).encode()).hexdigest()
    db = database()
    now = datetime.now(timezone.utc)
    db.intentos.delete_one({"_id": key, "expiresAt": {"$lte": now}})
    record = db.intentos.find_one({"_id": key})
    if record and record["count"] >= 10:
        return False
    db.intentos.update_one({"_id": key}, {"$inc": {"count": 1}, "$setOnInsert": {"expiresAt": now + timedelta(minutes=15)}}, upsert=True)
    return True


@never_cache
@require_http_methods(["GET"])
@database_errors
def session(request):
    user = current_user(request)
    return JsonResponse({"user": user_summary(user) if user else None, "redirect": destination(user) if user else None, "csrfToken": get_token(request)})


@never_cache
@require_http_methods(["POST"])
@database_errors
def login(request):
    data = payload(request)
    email = normalized_email(data.get("correo"))
    if not rate_limit(request, "login-ip") or not rate_limit(request, "login", email):
        return JsonResponse({"error": "Demasiados intentos. Espera 15 minutos e inténtalo otra vez."}, status=429)
    password = data.get("password")
    if not isinstance(password, str) or len(password) > 128:
        raise ValueError("Correo o contraseña incorrectos.")
    user = database().usuarios.find_one({"correo": email, "activo": True})
    matches = check_password(password, user["passwordHash"] if user else DUMMY_HASH)
    if not user or not matches:
        return JsonResponse({"error": "Correo o contraseña incorrectos."}, status=401)
    for scope, account in (("login-ip",""),("login",email)):
        key = hashlib.sha256((scope+":"+request.META.get("REMOTE_ADDR", "")+":"+account).encode()).hexdigest()
        database().intentos.delete_one({"_id":key})
    return start_session(request, JsonResponse({"user": user_summary(user), "redirect": destination(user)}), user)


@never_cache
@require_http_methods(["POST"])
@database_errors
def register(request):
    if not rate_limit(request, "register"):
        return JsonResponse({"error": "Demasiados intentos. Inténtalo más tarde."}, status=429)
    data = payload(request)
    email = normalized_email(data.get("correo"))
    valid_password(data.get("password"))
    name, role = data.get("nombre"), data.get("rol")
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 150 or role not in ("empresa", "profesional"):
        raise ValueError("Indica tu nombre y un tipo de cuenta válido.")
    from .contracts import terms_snapshot
    policy=terms_snapshot()
    if data.get('aceptoTerminos') is not True or data.get('mayorEdad') is not True or data.get('hashTerminos')!=policy['sha256']:
        raise ValueError('Confirma mayoría de edad y aceptación expresa de los términos vigentes.')
    db = database()
    db.politicas.update_one({'_id':policy['sha256']},{'$setOnInsert':policy},upsert=True)
    identifier, profile_id = str(uuid4()), str(uuid4())
    user = {"_id": identifier, "nombre": name.strip(), "correo": email, "passwordHash": make_password(data["password"]), "rol": role, "perfilId": profile_id, "activo": True, "fecha": datetime.now(timezone.utc)}
    user['aceptacionTerminos']={'version':policy['version'],'sha256':policy['sha256'],'fecha':datetime.now(timezone.utc),'mayorEdadDeclarada':True}
    db.usuarios.insert_one(user)
    try:
        if role == "empresa":
            db.empresas.insert_one({"_id": profile_id, "id": profile_id, "_version": 1, "nombre": name.strip(), "correo": email, "estado": "activa", "contacto": name.strip(),"rubro":"Por completar","descripcion":"","miembroDesde":datetime.now(timezone.utc).strftime("%m/%Y")})
        else:
            db.profesionales.insert_one({"_id": profile_id, "id": profile_id, "_version": 1, "nombre": name.strip(), "profesion": "Por completar", "estado": "revision", "ubicacion": "", "resumen": "", "habilidades": [], "documentos": [], "iniciales": "".join(part[0] for part in name.split()[:2]), "experienciaLaboral": [], "educacion": [], "cursos": [], "disponibilidad": [],"serviciosRealizados":0,"empresas":0,"cumplimiento":"Sin historial","experiencia":"Por completar"})
            review_profile(db, profile_id)
    except Exception:
        db.usuarios.delete_one({"_id": identifier})
        db.empresas.delete_one({"_id": profile_id})
        db.profesionales.delete_one({"_id": profile_id})
        db.validaciones.delete_one({"_id": profile_id})
        raise
    return start_session(request, JsonResponse({"user": user_summary(user), "redirect": "/cuenta/"}, status=201), user)


@never_cache
@require_http_methods(["POST"])
@database_errors
def logout(request):
    revoke_session(request)
    response = JsonResponse({"message": "Sesión cerrada."})
    response.delete_cookie(COOKIE, path="/", samesite="Lax")
    return response
