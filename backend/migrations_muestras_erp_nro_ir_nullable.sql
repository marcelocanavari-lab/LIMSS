-- ============================================================
-- MIGRACIÓN: lims_muestras.erp_nro_ir pasa a ser nullable
-- ------------------------------------------------------------
-- La Mod 5/6 (migrations_muestras_tipo_referencia.sql) reemplazó
-- erp_nro_ir por tipo_referencia/nro_referencia como identificador
-- canónico, pero en esta base nunca se ejecutó el paso final que
-- deja erp_nro_ir nullable (quedó NOT NULL). El INSERT de
-- crear_muestra (muestras.py) ya no completa esa columna -- por
-- eso hoy falla con "No se puede insertar NULL en 'erp_nro_ir'".
--
-- No se reutiliza migrations_muestras_tipo_referencia.sql completo:
-- su bloque para lims_aprobaciones_lote volvería a crear la UNIQUE
-- que se sacó a propósito en migrations_aprobaciones_lote_append_only.sql.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_muestras') AND name = 'erp_nro_ir' AND is_nullable = 0
)
BEGIN
    ALTER TABLE lims_muestras ALTER COLUMN erp_nro_ir VARCHAR(20) NULL;
    PRINT 'lims_muestras.erp_nro_ir ahora es NULL (deprecada, reemplazada por tipo_referencia/nro_referencia)';
END
GO
