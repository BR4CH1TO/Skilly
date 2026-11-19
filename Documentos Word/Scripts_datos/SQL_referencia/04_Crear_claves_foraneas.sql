-- Laboratorio aislado: no corresponde al almacenamiento operativo de Skilly.
USE skilly_rubrica_ref;
ALTER TABLE profesionales ADD CONSTRAINT fk_profesionales_usuario_id FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
ALTER TABLE empresas ADD CONSTRAINT fk_empresas_usuario_id FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
ALTER TABLE servicios ADD CONSTRAINT fk_servicios_profesional_id FOREIGN KEY(profesional_id) REFERENCES profesionales(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
ALTER TABLE solicitudes ADD CONSTRAINT fk_solicitudes_empresa_id FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
ALTER TABLE solicitudes ADD CONSTRAINT fk_solicitudes_profesional_id FOREIGN KEY(profesional_id) REFERENCES profesionales(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
ALTER TABLE solicitudes ADD CONSTRAINT fk_solicitudes_servicio_id FOREIGN KEY(servicio_id) REFERENCES servicios(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
ALTER TABLE agendas ADD CONSTRAINT fk_agendas_solicitud_id FOREIGN KEY(solicitud_id) REFERENCES solicitudes(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
ALTER TABLE contratos ADD CONSTRAINT fk_contratos_agenda_id FOREIGN KEY(agenda_id) REFERENCES agendas(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
ALTER TABLE hitos ADD CONSTRAINT fk_hitos_contrato_id FOREIGN KEY(contrato_id) REFERENCES contratos(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
