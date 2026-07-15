-- ============================================================
-- MIGRACIÓN: Observaciones en testigos y estándares
-- ------------------------------------------------------------
-- Agrega un campo de texto libre opcional a lims_testigos para notas
-- manuales (ej. condiciones de almacenamiento particulares, contexto
-- que no entra en el campo acotado de lims_testigo_movimientos, etc.)
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_testigos') AND name = 'observaciones'
)
BEGIN
    ALTER TABLE lims_testigos ADD observaciones NVARCHAR(500) NULL;
    PRINT 'Columna observaciones agregada a lims_testigos';
END
GO
