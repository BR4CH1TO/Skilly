// Solo bases de laboratorio; prohíbe ejecutar sobre skilly.
if (!/^skilly_lab_[a-z0-9_]+$/.test(db.getName())) throw new Error("Selecciona una base skilly_lab_... antes de ejecutar.");
db.profesionales.createIndex({"nombre": 1}, {});
db.empresas.createIndex({"nombre": 1}, {});
db.validaciones.createIndex({"profesionalId": 1}, {"unique": true});
db.pagos.createIndex({"agendaId": 1}, {"unique": true});
db.historial.createIndex({"fecha": -1}, {});
db.revisiones.createIndex({"recurso": 1, "registroId": 1, "fecha": -1}, {});
db.contratos.createIndex({"agendaId": 1}, {"unique": true});
db.atencion.createIndex({"usuarioId": 1, "fecha": -1}, {});
db.agendas.createIndex({"solicitudId": 1}, {"unique": true, "partialFilterExpression": {"estado": {"$in": ["propuesto", "confirmado", "realizado", "finalizado"]}}});
db.agendas.createIndex({"profesionalId": 1, "fecha": 1}, {"unique": true, "partialFilterExpression": {"estado": {"$in": ["propuesto", "confirmado", "realizado", "finalizado"]}}});
db.agendas.createIndex({"claveOperacion": 1}, {"unique": true, "partialFilterExpression": {"claveOperacion": {"$type": "string"}}});
db.solicitudes.createIndex({"claveOperacion": 1}, {"unique": true, "partialFilterExpression": {"claveOperacion": {"$type": "string"}}});
db.usuarios.createIndex({"correo": 1}, {"unique": true});
db.usuarios.createIndex({"perfilId": 1}, {"unique": true, "partialFilterExpression": {"perfilId": {"$type": "string"}}});
db.sesiones.createIndex({"expiresAt": 1}, {"expireAfterSeconds": 0});
db.intentos.createIndex({"expiresAt": 1}, {"expireAfterSeconds": 0});

// Filtro por estado y orden determinista del catálogo.
db.profesionales.createIndex({estado: 1, nombre: 1, _id: 1}, {name: "catalogo_profesionales"});
