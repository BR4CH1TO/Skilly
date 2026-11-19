// Solo bases de laboratorio; prohíbe ejecutar sobre skilly.
if (!/^skilly_lab_[a-z0-9_]+$/.test(db.getName())) throw new Error("Selecciona una base skilly_lab_... antes de ejecutar.");
for (const n of ["feriados", "configuracion", "atencion", "contratos", "revisiones", "politicas", "intentos", "sesiones", "usuarios", "historial", "pagos", "agendas", "solicitudes", "servicios", "validaciones", "empresas", "profesionales"]) if (db.getCollectionNames().includes(n)) db.getCollection(n).drop();
