-- Laboratorio aislado: no corresponde al almacenamiento operativo de Skilly.
USE skilly_rubrica_ref;
START TRANSACTION;
INSERT INTO usuarios VALUES ('lab-up','Profesional de demostración','profesional@example.invalid','profesional',TRUE),('lab-ue','Empresa de demostración','empresa@example.invalid','empresa',TRUE);
INSERT INTO profesionales VALUES ('lab-p','lab-up','Profesional de demostración','Diseño','validado');
INSERT INTO empresas VALUES ('lab-e','lab-ue','Empresa de demostración','empresa@example.invalid');
INSERT INTO servicios VALUES ('lab-s','lab-p','Servicio de demostración de laboratorio',100000,TRUE);
INSERT INTO solicitudes VALUES ('lab-r','lab-e','lab-p','lab-s','2026-12-01 12:00:00','aceptada');
INSERT INTO agendas VALUES ('lab-a','lab-r','2026-12-02 12:00:00','confirmado',100000);
INSERT INTO contratos VALUES ('lab-c','lab-a',1,'vigente','Contrato de demostración para verificar PK y FK.');
INSERT INTO hitos VALUES ('lab-h','lab-c','Entrega de demostración',100000,'2026-12-10 18:00:00','por_financiar');
COMMIT;
SELECT c.id AS contrato, e.nombre AS empresa, p.nombre AS profesional, s.titulo AS servicio, h.neto AS importe
FROM contratos c JOIN agendas a ON a.id=c.agenda_id JOIN solicitudes r ON r.id=a.solicitud_id JOIN empresas e ON e.id=r.empresa_id JOIN profesionales p ON p.id=r.profesional_id JOIN servicios s ON s.id=r.servicio_id JOIN hitos h ON h.contrato_id=c.id;
SELECT COUNT(*) AS claves_foraneas FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA='skilly_rubrica_ref';
