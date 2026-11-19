"""Restricciones comerciales sin privar del acceso a acuerdos y atención.

Documenta propósito, contratos y límites de las operaciones del prototipo.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pymongo.database import Database

from datetime import datetime, timezone


def restricted(user: dict[str, Any]) -> bool:
    """Comprueba si la restricción comercial ya está vigente.

    Compara desde con el instante actual; una restricción futura todavía no bloquea nuevas
    operaciones.

    Args:
        user: Cuenta autenticada con _id, rol y perfilId cuando participa como empresa/profesional.

    Returns:
        True si se cumple la condición descrita; False en caso contrario.
    """
    r = user.get("restriccionComercial")
    if not r:
        return False
    return datetime.fromisoformat(r["desde"].replace("Z", "+00:00")) <= datetime.now(
        timezone.utc
    )


def require_commercial(user: dict[str, Any]) -> None:
    """Impide nuevas operaciones comerciales de una cuenta restringida.

    La restricción no elimina la cuenta ni impide consultar acuerdos o solicitar revisión.

    Args:
        user: Cuenta autenticada con _id, rol y perfilId cuando participa como empresa/profesional.

    Returns:
        No devuelve un valor; consulta/actualiza solo lo indicado en la descripción.

    Raises:
        ValueError: Se incumple una de las precondiciones o reglas descritas.
    """
    if restricted(user):
        raise ValueError(
            "Tu cuenta tiene una restricción comercial. Puedes consultar tus acuerdos y pedir revisión desde Privacidad y atención."
        )


def project_restrictions(db: Database) -> None:
    """Actualiza la marca comercial en los perfiles correspondientes.

    Proyecta restricciones de cuentas empresa/profesional; no cambia su sesión ni los acuerdos
    existentes.

    Args:
        db: Base MongoDB configurada; los ensayos deben usar una base temporal.

    Returns:
        No devuelve un valor; consulta/actualiza solo lo indicado en la descripción.
    """
    for user in db.usuarios.find({"rol": {"$in": ["empresa", "profesional"]}}):
        target = "profesionales" if user["rol"] == "profesional" else "empresas"
        db[target].update_one(
            {"_id": user["perfilId"]},
            {"$set": {"restriccionComercialActiva": restricted(user)}},
        )
