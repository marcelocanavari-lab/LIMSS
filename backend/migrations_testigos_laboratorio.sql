-- ============================================================
-- MIGRACIÓN: laboratorio asignado a un testigo/estándar
-- ------------------------------------------------------------
-- lims_testigos no tiene columna para indicar a qué laboratorio
-- está asignado el testigo (funcionalidad que existía antes y se
-- perdió en un cambio posterior). Se agrega id_laboratorio NULL
-- (un testigo puede no tener laboratorio asignado todavía) con FK
-- a lims_laboratorios.
--
-- Idempotente: si la columna ya existe, no hace nada.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF COL_LENGTH('lims_testigos', 'id_laboratorio') IS NULL
BEGIN
    ALTER TABLE lims_testigos
        ADD id_laboratorio INT NULL
        CONSTRAINT fk_testigos_laboratorio REFERENCES lims_laboratorios(id_laboratorio);
    PRINT 'Columna id_laboratorio agregada a lims_testigos';
END
GO
