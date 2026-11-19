from datetime import datetime, timezone

from django.db import connections
from pymongo import ASCENDING, DESCENDING

# Las claves del frontend se mantienen para no cambiar la interfaz.
COLLECTIONS = {
    "profesionales": "profesionales", "empresas": "empresas",
    "validaciones": "validaciones", "servicios": "servicios",
    "solicitudes": "solicitudes", "agendamientos": "agendas",
    "pagos": "pagos", "trazabilidad": "historial",
}
REFERENCES = {
    "validaciones": {"profesionalId": "profesionales"},
    "servicios": {"profesionalId": "profesionales"},
    "solicitudes": {"empresaId": "empresas", "profesionalId": "profesionales", "servicioId": "servicios"},
    "agendas": {"solicitudId": "solicitudes", "empresaId": "empresas", "profesionalId": "profesionales", "servicioId": "servicios"},
    "pagos": {"agendaId": "agendas", "solicitudId": "solicitudes", "empresaId": "empresas", "profesionalId": "profesionales", "servicioId": "servicios"},
}
REQUIRED = {
    "profesionales": {"nombre": str, "profesion": str, "estado": str},
    "empresas": {"nombre": str, "correo": str, "estado": str},
    "validaciones": {"profesionalId": str, "estado": str},
    "servicios": {"titulo": str, "profesionalId": str, "precio": int, "disponible": bool},
    "solicitudes": {"empresaId": str, "profesionalId": str, "servicioId": str, "fecha": str, "expiracion": str, "estado": str},
    "agendas": {"solicitudId": str, "empresaId": str, "profesionalId": str, "servicioId": str, "fecha": str, "estado": str},
    "pagos": {"agendaId": str, "solicitudId": str, "empresaId": str, "profesionalId": str, "servicioId": str, "monto": int, "fecha": str, "estado": str},
    "historial": {"tipo": str, "titulo": str, "descripcion": str, "fecha": str},
}
STATES = {
    "profesionales": {"validado", "revision", "segunda", "rechazado"},
    "validaciones": {"validado", "revision", "segunda", "rechazado"},
    "empresas": {"activa", "inactiva"},
    "solicitudes": {"pendiente", "aceptada", "rechazada", "expirada"},
    "agendas": {"propuesto", "confirmado", "realizado", "finalizado", "cancelado"},
    "pagos": {"espera", "pendiente", "pagado", "finalizado"},
}
DATE_FIELDS = {"solicitudes": ("fecha", "expiracion"), "agendas": ("fecha",), "pagos": ("fecha",), "historial": ("fecha",)}


def database():
    return connections["default"].database


def record_id(record):
    return record.get("id", record.get("profesionalId"))


def valid_identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 128 and all(c.isalnum() or c in "-_" for c in value)


def safe_fields(value):
    if isinstance(value, dict):
        return all(isinstance(k, str) and not k.startswith(("$", "_")) and "." not in k and safe_fields(v) for k, v in value.items())
    if isinstance(value, list):
        return len(value) <= 10000 and all(safe_fields(v) for v in value)
    return value is None or type(value) in (str, int, float, bool)


def validate_record(resource, record, db):
    if not isinstance(record, dict) or not safe_fields(record) or not valid_identifier(record_id(record)):
        raise ValueError("El registro o su identificador no son válidos.")
    if resource != "validaciones" and not valid_identifier(record.get("id")):
        raise ValueError("El campo id es obligatorio.")
    for field, field_type in REQUIRED[resource].items():
        if type(record.get(field)) is not field_type or (field_type is str and not record[field].strip()):
            raise ValueError(f"El campo {field} es obligatorio y debe tener el tipo correcto.")
    if resource in STATES and record["estado"] not in STATES[resource]:
        raise ValueError("El estado no es válido.")
    for field in ("monto", "precio"):
        if field in record and (type(record[field]) is not int or record[field] < 0):
            raise ValueError(f"El campo {field} debe ser un entero no negativo en pesos chilenos.")
    for field, target in REFERENCES.get(resource, {}).items():
        if not valid_identifier(record.get(field)) or db[target].find_one({"_id": record[field]}, {"_id": 1}) is None:
            raise ValueError(f"El campo {field} no corresponde a un registro existente.")
    if resource == "validaciones" and record_id(record) != record["profesionalId"]:
        raise ValueError("La validación debe usar el identificador del profesional.")
    limits = {"nombre":150,"profesion":150,"ubicacion":150,"resumen":4000,"descripcion":4000,"entregables":4000,"titulo":200,"categoria":100,"duracion":100,"experiencia":150}
    for field, limit in limits.items():
        if field in record and (not isinstance(record[field], str) or len(record[field]) > limit):
            raise ValueError(f"El campo {field} debe ser texto de hasta {limit} caracteres.")
    for field in ("habilidades", "cursos", "disponibilidad"):
        if field in record and (not isinstance(record[field], list) or len(record[field]) > 100 or any(not isinstance(v,str) or not v.strip() or len(v)>200 for v in record[field])):
            raise ValueError(f"El campo {field} debe ser una lista de textos válidos (máximo 100).")
    for field in ("experienciaLaboral", "educacion", "documentos"):
        if field in record and (not isinstance(record[field], list) or len(record[field])>100 or any(not isinstance(v,dict) for v in record[field])):
            raise ValueError(f"El campo {field} debe ser una lista de registros.")
    if "disponibilidad" in record:
        from .business import instant
        for value in record["disponibilidad"]:
            instant(value)
    # Rechaza fechas inválidas antes de cualquier escritura.
    to_document(resource, record)


def to_document(resource, record, version=1):
    document = {**record, "_id": record_id(record), "_version": version}
    for field in DATE_FIELDS.get(resource, ()):
        try:
            date = datetime.fromisoformat(record[field].replace("Z", "+00:00"))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ValueError(f"El campo {field} debe ser una fecha ISO válida.") from None
        # Las fechas antiguas sin zona pertenecen a la zona configurada en Skilly.
        if date.tzinfo is None:
            from zoneinfo import ZoneInfo
            from django.conf import settings
            date = date.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
        document[field] = date.astimezone(timezone.utc)
    return document


def serialize(document):
    record = {k: v for k, v in document.items() if not k.startswith("_")}
    for key, value in record.items():
        if isinstance(value, datetime):
            record[key] = value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return record


def ensure_indexes(db):
    existing = set(db.list_collection_names())
    for resource in COLLECTIONS.values():
        bson_types = {str: "string", int: ["int", "long"], bool: "bool"}
        properties = {"_id": {"bsonType": "string"}, "_version": {"bsonType": ["int", "long"], "minimum": 1}}
        for field, field_type in REQUIRED[resource].items():
            properties[field] = {"bsonType": "date" if field in DATE_FIELDS.get(resource, ()) else bson_types[field_type]}
        for field in ("monto", "precio"):
            if field in properties:
                properties[field]["minimum"] = 0
        if resource in STATES:
            properties["estado"]["enum"] = sorted(STATES[resource])
        validator = {"$jsonSchema": {
            "bsonType": "object",
            "required": ["_id", "_version", *REQUIRED[resource]],
            "properties": properties,
        }}
        if resource in existing:
            db.command("collMod", resource, validator=validator, validationLevel="strict")
        else:
            db.create_collection(resource, validator=validator)
        # _id ya es único e indexado. Las relaciones se consultan por identificador.
        for field in REFERENCES.get(resource, {}):
            if (resource, field) in {("validaciones", "profesionalId"), ("pagos", "agendaId"), ("agendas", "solicitudId")}:
                continue
            db[resource].create_index([(field, ASCENDING)])
        if resource in STATES:
            db[resource].create_index([("estado", ASCENDING)])
    db.profesionales.create_index([("nombre", ASCENDING)])
    catalog_indexes(db)
    db.empresas.create_index([("nombre", ASCENDING)])
    db.validaciones.create_index("profesionalId", unique=True)
    db.pagos.create_index("agendaId", unique=True)
    db.agendas.create_index("solicitudId", unique=True, partialFilterExpression={"estado": {"$in": ["propuesto", "confirmado", "realizado", "finalizado"]}})
    db.agendas.create_index([("profesionalId", ASCENDING), ("fecha", ASCENDING)], unique=True, partialFilterExpression={"estado": {"$in": ["propuesto", "confirmado", "realizado", "finalizado"]}})
    db.agendas.create_index("claveOperacion", unique=True, partialFilterExpression={"claveOperacion":{"$type":"string"}})
    db.solicitudes.create_index("claveOperacion", unique=True, partialFilterExpression={"claveOperacion":{"$type":"string"}})
    contract_indexes(db)
    db.historial.create_index([("fecha", DESCENDING)])
    db.revisiones.create_index([("recurso", ASCENDING), ("registroId", ASCENDING), ("fecha", DESCENDING)])



def catalog_indexes(db):
    """Cubre estado y orden estable del catálogo, sin retirar índices existentes."""
    return db.profesionales.create_index(
        [("estado", ASCENDING), ("nombre", ASCENDING), ("_id", ASCENDING)],
        name="catalogo_profesionales",
    )


def contract_indexes(db):
    db.atencion.create_index([('usuarioId',1),('fecha',-1)])
    db.contratos.create_index('agendaId',unique=True)
    db.contratos.create_index([('empresaId',1),('creadoEn',-1)])
    db.contratos.create_index([('profesionalId',1),('creadoEn',-1)])
