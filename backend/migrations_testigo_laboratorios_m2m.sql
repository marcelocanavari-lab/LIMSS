-- ============================================================
-- MIGRACIÓN: testigo <-> laboratorio, relación muchos a muchos
-- ------------------------------------------------------------
-- Un testigo puede estar asignado a varios laboratorios (antes
-- solo se permitía uno, vía lims_testigos.id_laboratorio). Se
-- agrega la tabla de relación lims_testigo_laboratorios y se
-- migran los datos existentes.
--
-- lims_testigos.id_laboratorio queda deprecado -- NO se elimina,
-- por compatibilidad con datos/consultas antiguas.
--
-- Idempotente: si la tabla ya existe, no hace nada.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF OBJECT_ID('lims_testigo_laboratorios', 'U') IS NULL
BEGIN
    CREATE TABLE lims_testigo_laboratorios (
        id             INT IDENTITY(1,1) PRIMARY KEY,
        id_testigo     INT NOT NULL REFERENCES lims_testigos(id_testigo),
        id_laboratorio INT NOT NULL REFERENCES lims_laboratorios(id_laboratorio),
        CONSTRAINT uq_testigo_lab UNIQUE (id_testigo, id_laboratorio)
    );
    PRINT 'Tabla lims_testigo_laboratorios creada';

    IF COL_LENGTH('lims_testigos', 'id_laboratorio') IS NOT NULL
    BEGIN
        INSERT INTO lims_testigo_laboratorios (id_testigo, id_laboratorio)
        SELECT id_testigo, id_laboratorio
        FROM lims_testigos
        WHERE id_laboratorio IS NOT NULL;
        PRINT 'Datos existentes de id_laboratorio migrados a lims_testigo_laboratorios';
    END
END
GO
