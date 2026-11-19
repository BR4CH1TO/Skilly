-- Laboratorio aislado: no corresponde al almacenamiento operativo de Skilly.
USE skilly_rubrica_ref;
ALTER TABLE hitos DROP PRIMARY KEY;
ALTER TABLE contratos DROP PRIMARY KEY;
ALTER TABLE agendas DROP PRIMARY KEY;
ALTER TABLE solicitudes DROP PRIMARY KEY;
ALTER TABLE servicios DROP PRIMARY KEY;
ALTER TABLE empresas DROP PRIMARY KEY;
ALTER TABLE profesionales DROP PRIMARY KEY;
ALTER TABLE usuarios DROP PRIMARY KEY;
