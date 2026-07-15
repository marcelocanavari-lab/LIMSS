-- ============================================================
-- MIGRACIÓN: Observaciones en ensayos de especificación
-- ------------------------------------------------------------
-- Agrega un campo de texto libre opcional a lims_ensayos para notas
-- manuales del ensayo (ej. condiciones particulares de medición,
-- aclaraciones sobre la metodología, etc.)
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_ensayos') AND name = 'observaciones'
)
BEGIN
    ALTER TABLE lims_ensayos ADD observaciones NVARCHAR(500) NULL;
    PRINT 'Columna observaciones agregada a lims_ensayos';
END
GO
