"""API de registro, autenticación y salida con contraseñas verificadas.

Documenta propósito, contratos y límites de las operaciones del prototipo.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest

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

from .access import (
    COOKIE,
    access_required,
    current_user,
    digest,
    revoke_session,
    start_session,
)
from .storage import database
from .views import database_errors, payload
from .workflow import review_profile

# Hash válido para igualar el trabajo cuando la cuenta no existe.
DUMMY_HASH = make_password("non-login-placeholder")


def user_summary(user: dict[str, Any]) -> dict[str, Any]:
    """Proyecta los datos de cuenta necesarios para la interfaz.

    Incluye nombre, correo y rol; excluye passwordHash e identificadores de sesión.

    Args:
        user: Cuenta autenticada con _id, rol y perfilId cuando participa como empresa/profesional.

    Returns:
        Objeto con los campos y significado indicados en la descripción.
    """
    return {"nombre": user["nombre"], "correo": user["correo"], "rol": user["rol"]}


def destination(user: dict[str, Any]) -> str:
    """Selecciona el espacio inicial de la cuenta autenticada.

    Administración usa /panel/; empresa y profesional usan /cuenta/, cuyo contenido depende del rol.

    Args:
        user: Cuenta autenticada con _id, rol y perfilId cuando participa como empresa/profesional.

    Returns:
        Texto normalizado o identificador descrito.
    """
    return "/panel/" if user["rol"] == "admin" else "/cuenta/"


def normalized_email(value: Any) -> str:
    """Valida y normaliza el correo usado como identificador de acceso.

    Recorta espacios y aplica casefold; rechaza entradas no textuales o mayores de 254 caracteres.

    Args:
        value: Valor recibido o calculado que se comprobará según las reglas descritas.

    Returns:
        Texto normalizado o identificador descrito.

    Raises:
        ValueError: Se incumple una de las precondiciones o reglas descritas.

    Examples:
        >>> normalized_email("  CUENTA@example.com  ")
        'cuenta@example.com'
    """
    if not isinstance(value, str) or len(value) > 254:
        raise ValueError("Introduce un correo válido.")
    value = value.strip().casefold()
    try:
        validate_email(value)
    except ValidationError:
        raise ValueError("Introduce un correo válido.") from None
    return value


def valid_password(value: Any) -> None:
    """Valida una contraseña nueva con los controles configurados de Django.

    Exige entre 8 y 128 caracteres, rechaza claves comunes y exclusivamente numéricas. No exige
    una combinación fija de símbolos. La comprobación de confirmación corresponde al formulario
    de registro.

    Args:
        value: Valor recibido o calculado que se comprobará según las reglas descritas.

    Returns:
        No devuelve un valor; consulta/actualiza solo lo indicado en la descripción.

    Raises:
        ValueError: Se incumple una de las precondiciones o reglas descritas.
    """
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError("La contraseña debe tener entre 8 y 128 caracteres.")
    try:
        validate_password(value)
    except ValidationError as error:
        raise ValueError(" ".join(error.messages)) from None


def rate_limit(request: HttpRequest, scope: str, email: str = "") -> bool:
    """Registra y comprueba una ventana de intentos de quince minutos.

    La clave combina ámbito, IP y, cuando procede, correo. Diez intentos se admiten en la
    ventana; el siguiente se bloquea. No es un contador distribuido transaccional ni garantiza
    un límite exacto bajo carreras simultáneas.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.
        scope: Ámbito del contador para separar login por IP, cuenta y registro.
        email: Correo normalizado o cadena vacía cuando el límite es solo por IP.

    Returns:
        True si se cumple la condición descrita; False en caso contrario.
    """
    key = hashlib.sha256(
        (scope + ":" + request.META.get("REMOTE_ADDR", "") + ":" + email).encode()
    ).hexdigest()
    db = database()
    now = datetime.now(timezone.utc)
    db.intentos.delete_one({"_id": key, "expiresAt": {"$lte": now}})
    record = db.intentos.find_one({"_id": key})
    if record and record["count"] >= 10:
        return False
    db.intentos.update_one(
        {"_id": key},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {"expiresAt": now + timedelta(minutes=15)},
        },
        upsert=True,
    )
    return True


@never_cache
@require_http_methods(["GET"])
@database_errors
def session(request: HttpRequest) -> JsonResponse:
    """Expone la sesión actual y un token CSRF para el formulario.

    GET público: user y redirect son nulos si no hay cuenta autenticada. No expone el token
    opaco de sesión.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    user = current_user(request)
    return JsonResponse(
        {
            "user": user_summary(user) if user else None,
            "redirect": destination(user) if user else None,
            "csrfToken": get_token(request),
        }
    )


@never_cache
@require_http_methods(["POST"])
@database_errors
def login(request: HttpRequest) -> JsonResponse:
    """Autentica y crea una sesión sin revelar qué credencial falló.

    POST JSON con correo y password. Responde 200 al autenticar, 401 con error genérico o 429
    por intentos. El hash ficticio mantiene una comprobación de contraseña incluso sin cuenta.
    JSON/correo inválidos producen 400 mediante database_errors.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    data = payload(request)
    email = normalized_email(data.get("correo"))
    if not rate_limit(request, "login-ip") or not rate_limit(request, "login", email):
        return JsonResponse(
            {"error": "Demasiados intentos. Espera 15 minutos e inténtalo otra vez."},
            status=429,
        )
    password = data.get("password")
    if not isinstance(password, str) or len(password) > 128:
        raise ValueError("Correo o contraseña incorrectos.")
    user = database().usuarios.find_one({"correo": email, "activo": True})
    matches = check_password(password, user["passwordHash"] if user else DUMMY_HASH)
    if not user or not matches:
        return JsonResponse({"error": "Correo o contraseña incorrectos."}, status=401)
    for scope, account in (("login-ip", ""), ("login", email)):
        key = hashlib.sha256(
            (scope + ":" + request.META.get("REMOTE_ADDR", "") + ":" + account).encode()
        ).hexdigest()
        database().intentos.delete_one({"_id": key})
    return start_session(
        request,
        JsonResponse({"user": user_summary(user), "redirect": destination(user)}),
        user,
    )


@never_cache
@require_http_methods(["POST"])
@database_errors
def register(request: HttpRequest) -> JsonResponse:
    """Registra una empresa o un profesional con aceptación de condiciones.

    POST JSON: nombre de 3–150 caracteres, correo, password, rol, mayoría de edad, aceptación y
    hash vigente. Crea cuenta/perfil; devuelve 201 y sesión. Clave o datos inválidos: 400;
    correo duplicado: 409; límite de intentos: 429. El rol admin no se admite. Ante fallo al
    crear el perfil intenta retirar la cuenta creada; no declara una transacción entre
    colecciones.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    if not rate_limit(request, "register"):
        return JsonResponse(
            {"error": "Demasiados intentos. Inténtalo más tarde."}, status=429
        )
    data = payload(request)
    email = normalized_email(data.get("correo"))
    valid_password(data.get("password"))
    name, role = data.get("nombre"), data.get("rol")
    if (
        not isinstance(name, str)
        or not 3 <= len(name.strip()) <= 150
        or role not in ("empresa", "profesional")
    ):
        raise ValueError("Indica tu nombre y un tipo de cuenta válido.")
    from .contracts import terms_snapshot

    policy = terms_snapshot()
    if (
        data.get("aceptoTerminos") is not True
        or data.get("mayorEdad") is not True
        or data.get("hashTerminos") != policy["sha256"]
    ):
        raise ValueError(
            "Confirma mayoría de edad y aceptación expresa de los términos vigentes."
        )
    db = database()
    db.politicas.update_one(
        {"_id": policy["sha256"]}, {"$setOnInsert": policy}, upsert=True
    )
    identifier, profile_id = str(uuid4()), str(uuid4())
    user = {
        "_id": identifier,
        "nombre": name.strip(),
        "correo": email,
        "passwordHash": make_password(data["password"]),
        "rol": role,
        "perfilId": profile_id,
        "activo": True,
        "fecha": datetime.now(timezone.utc),
    }
    user["aceptacionTerminos"] = {
        "version": policy["version"],
        "sha256": policy["sha256"],
        "fecha": datetime.now(timezone.utc),
        "mayorEdadDeclarada": True,
    }
    db.usuarios.insert_one(user)
    try:
        if role == "empresa":
            db.empresas.insert_one(
                {
                    "_id": profile_id,
                    "id": profile_id,
                    "_version": 1,
                    "nombre": name.strip(),
                    "correo": email,
                    "estado": "activa",
                    "contacto": name.strip(),
                    "rubro": "Por completar",
                    "descripcion": "",
                    "miembroDesde": datetime.now(timezone.utc).strftime("%m/%Y"),
                }
            )
        else:
            db.profesionales.insert_one(
                {
                    "_id": profile_id,
                    "id": profile_id,
                    "_version": 1,
                    "nombre": name.strip(),
                    "profesion": "Por completar",
                    "estado": "revision",
                    "ubicacion": "",
                    "resumen": "",
                    "habilidades": [],
                    "documentos": [],
                    "iniciales": "".join(part[0] for part in name.split()[:2]),
                    "experienciaLaboral": [],
                    "educacion": [],
                    "cursos": [],
                    "disponibilidad": [],
                    "serviciosRealizados": 0,
                    "empresas": 0,
                    "cumplimiento": "Sin historial",
                    "experiencia": "Por completar",
                }
            )
            review_profile(db, profile_id)
    except Exception:
        db.usuarios.delete_one({"_id": identifier})
        db.empresas.delete_one({"_id": profile_id})
        db.profesionales.delete_one({"_id": profile_id})
        db.validaciones.delete_one({"_id": profile_id})
        raise
    return start_session(
        request,
        JsonResponse({"user": user_summary(user), "redirect": "/cuenta/"}, status=201),
        user,
    )


@never_cache
@require_http_methods(["POST"])
@database_errors
def logout(request: HttpRequest) -> JsonResponse:
    """Revoca la sesión y retira su cookie del navegador.

    POST protegido por CSRF. Devuelve 200 con confirmación; una cookie ausente no crea una
    sesión nueva.

    Args:
        request: Petición Django; JSON, parámetros o multipart según el contrato descrito. Los
            decoradores verifican método, sesión, rol y CSRF cuando corresponde.

    Returns:
        Respuesta JSON de éxito o error según método, permisos y reglas descritos.
        database_errors convierte validación en 400, duplicados en 409 y fallos MongoDB en 503;
        los decoradores pueden responder 401/403/405.
    """
    revoke_session(request)
    response = JsonResponse({"message": "Sesión cerrada."})
    response.delete_cookie(COOKIE, path="/", samesite="Lax")
    return response
