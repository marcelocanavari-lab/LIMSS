-- ============================================================
-- MIGRACIÓN: Analito opcional + permitir ensayos repetidos en
-- una misma especificación
-- ------------------------------------------------------------
-- Elimina la restricción UNIQUE(id_especificacion, id_ensayo_maestro)
-- que impedía cargar el mismo ensayo del catálogo dos veces en la misma
-- especificación (ej. "Valoración" para Trimetoprima y para
-- Sulfametoxazol en un mismo combinado). Agrega analito (texto libre
-- opcional) para diferenciar visualmente esos casos -- el usuario decide
-- si lo carga o no, no tiene validación obligatoria.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id = OBJECT_ID('lims_especificacion_ensayos') AND name = 'uq_espec_ensayo'
)
BEGIN
    ALTER TABLE lims_especificacion_ensayos DROP CONSTRAINT uq_espec_ensayo;
    PRINT 'Restricción uq_espec_ensayo eliminada de lims_especificacion_ensayos';
END
ELSE
    PRINT 'uq_espec_ensayo ya no existe';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_especificacion_ensayos') AND name = 'analito'
)
BEGIN
    ALTER TABLE lims_especificacion_ensayos ADD analito VARCHAR(100) NULL;
    PRINT 'Columna analito agregada a lims_especificacion_ensayos';
END
ELSE
    PRINT 'La columna analito ya existe en lims_especificacion_ensayos';
GO
