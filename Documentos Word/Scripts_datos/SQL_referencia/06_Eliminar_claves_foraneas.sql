-- Laboratorio aislado: no corresponde al almacenamiento operativo de Skilly.
USE skilly_rubrica_ref;
ALTER TABLE hitos DROP FOREIGN KEY fk_hitos_contrato_id;
ALTER TABLE contratos DROP FOREIGN KEY fk_contratos_agenda_id;
ALTER TABLE agendas DROP FOREIGN KEY fk_agendas_solicitud_id;
ALTER TABLE solicitudes DROP FOREIGN KEY fk_solicitudes_servicio_id;
ALTER TABLE solicitudes DROP FOREIGN KEY fk_solicitudes_profesional_id;
ALTER TABLE solicitudes DROP FOREIGN KEY fk_solicitudes_empresa_id;
ALTER TABLE servicios DROP FOREIGN KEY fk_servicios_profesional_id;
ALTER TABLE empresas DROP FOREIGN KEY fk_empresas_usuario_id;
ALTER TABLE profesionales DROP FOREIGN KEY fk_profesionales_usuario_id;
