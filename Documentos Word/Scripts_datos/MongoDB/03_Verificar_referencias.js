// Solo bases de laboratorio; prohíbe ejecutar sobre skilly.
if (!/^skilly_lab_[a-z0-9_]+$/.test(db.getName())) throw new Error("Selecciona una base skilly_lab_... antes de ejecutar.");
// Auditoría de referencias: MongoDB no implementa FK nativas.
for (const [origin,field,target] of [["servicios","profesionalId","profesionales"],["solicitudes","empresaId","empresas"],["solicitudes","servicioId","servicios"],["agendas","solicitudId","solicitudes"],["pagos","agendaId","agendas"],["contratos","agendaId","agendas"]]) {
 const broken=db.getCollection(origin).aggregate([{$lookup:{from:target,localField:field,foreignField:"_id",as:"ref"}},{$match:{ref:{$size:0}}},{$count:"total"}]).toArray();
 printjson({coleccion:origin,campo:field,referenciasInexistentes:broken.length?broken[0].total:0});
}
