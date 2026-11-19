-- Laboratorio aislado: no corresponde al almacenamiento operativo de Skilly.
USE skilly_rubrica_ref;
CREATE TABLE usuarios (id VARCHAR(128) NOT NULL, nombre VARCHAR(150) NOT NULL, correo VARCHAR(254) NOT NULL, rol VARCHAR(20) NOT NULL, activo BOOLEAN NOT NULL DEFAULT TRUE, UNIQUE KEY uq_correo(correo), CHECK (rol IN ('empresa','profesional','admin'))) ENGINE=InnoDB;
CREATE TABLE profesionales (id VARCHAR(128) NOT NULL, usuario_id VARCHAR(128) NOT NULL, nombre VARCHAR(150) NOT NULL, profesion VARCHAR(150) NOT NULL, estado VARCHAR(20) NOT NULL, UNIQUE KEY uq_prof_usuario(usuario_id)) ENGINE=InnoDB;
CREATE TABLE empresas (id VARCHAR(128) NOT NULL, usuario_id VARCHAR(128) NOT NULL, nombre VARCHAR(150) NOT NULL, correo VARCHAR(254) NOT NULL, UNIQUE KEY uq_emp_usuario(usuario_id)) ENGINE=InnoDB;
CREATE TABLE servicios (id VARCHAR(128) NOT NULL, profesional_id VARCHAR(128) NOT NULL, titulo VARCHAR(200) NOT NULL, precio BIGINT UNSIGNED NOT NULL, disponible BOOLEAN NOT NULL DEFAULT FALSE) ENGINE=InnoDB;
CREATE TABLE solicitudes (id VARCHAR(128) NOT NULL, empresa_id VARCHAR(128) NOT NULL, profesional_id VARCHAR(128) NOT NULL, servicio_id VARCHAR(128) NOT NULL, fecha DATETIME NOT NULL, estado VARCHAR(20) NOT NULL) ENGINE=InnoDB;
CREATE TABLE agendas (id VARCHAR(128) NOT NULL, solicitud_id VARCHAR(128) NOT NULL, fecha DATETIME NOT NULL, estado VARCHAR(20) NOT NULL, precio_acordado BIGINT UNSIGNED NOT NULL) ENGINE=InnoDB;
CREATE TABLE contratos (id VARCHAR(128) NOT NULL, agenda_id VARCHAR(128) NOT NULL, version INT UNSIGNED NOT NULL DEFAULT 1, estado VARCHAR(20) NOT NULL, alcance TEXT NOT NULL, UNIQUE KEY uq_contrato_agenda(agenda_id)) ENGINE=InnoDB;
CREATE TABLE hitos (id VARCHAR(128) NOT NULL, contrato_id VARCHAR(128) NOT NULL, nombre VARCHAR(150) NOT NULL, neto BIGINT UNSIGNED NOT NULL, vence DATETIME NOT NULL, estado VARCHAR(25) NOT NULL) ENGINE=InnoDB;
