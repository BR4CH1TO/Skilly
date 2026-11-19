-- Laboratorio aislado: no corresponde al almacenamiento operativo de Skilly.
USE skilly_rubrica_ref;
ALTER TABLE usuarios ADD PRIMARY KEY(id);
ALTER TABLE profesionales ADD PRIMARY KEY(id);
ALTER TABLE empresas ADD PRIMARY KEY(id);
ALTER TABLE servicios ADD PRIMARY KEY(id);
ALTER TABLE solicitudes ADD PRIMARY KEY(id);
ALTER TABLE agendas ADD PRIMARY KEY(id);
ALTER TABLE contratos ADD PRIMARY KEY(id);
ALTER TABLE hitos ADD PRIMARY KEY(id);
