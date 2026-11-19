// Solo bases de laboratorio; prohíbe ejecutar sobre skilly.
if (!/^skilly_lab_[a-z0-9_]+$/.test(db.getName())) throw new Error("Selecciona una base skilly_lab_... antes de ejecutar.");
for (const n of ["profesionales", "empresas", "validaciones", "servicios", "solicitudes", "agendas", "pagos", "historial", "usuarios", "sesiones", "intentos", "politicas", "revisiones", "contratos", "atencion", "configuracion", "feriados"]) if (db.getCollectionNames().includes(n)) db.getCollection(n).dropIndexes();
