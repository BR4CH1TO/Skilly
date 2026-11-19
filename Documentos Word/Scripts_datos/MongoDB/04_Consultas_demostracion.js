// Solo bases de laboratorio; prohíbe ejecutar sobre skilly.
if (!/^skilly_lab_[a-z0-9_]+$/.test(db.getName())) throw new Error("Selecciona una base skilly_lab_... antes de ejecutar.");
db.profesionales.find({}, {nombre:1,profesion:1,estado:1}).limit(1).forEach(printjson);
db.servicios.find({disponible:true}, {titulo:1,precio:1,profesionalId:1}).limit(5).forEach(printjson);
printjson(db.agendas.getIndexes());
printjson(db.contratos.getIndexes());
