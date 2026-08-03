-- ============================================================
-- MIGRACIÓN: restringir lims_testigos.unidad_medida a mg / ml
-- ------------------------------------------------------------
-- Antes de agregar la restricción, normaliza cualquier valor que
-- no sea 'mg' ni 'ml' (o NULL) a 'mg'. Verificado en vivo: al momento
-- de escribir esta migración solo había 2 registros con 'G' (ya
-- normalizados por la app usando el mismo criterio); este UPDATE
-- queda igual por si se cargó algo nuevo entre medio.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

UPDATE lims_testigos
SET unidad_medida = 'mg'
WHERE unidad_medida NOT IN ('mg', 'ml') OR unidad_medida IS NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = 'ck_testigo_unidad'
)
BEGIN
    ALTER TABLE lims_testigos
        ADD CONSTRAINT ck_testigo_unidad
        CHECK (unidad_medida IN ('mg', 'ml'));
    PRINT 'Restricción CHECK ck_testigo_unidad agregada a lims_testigos.unidad_medida';
END
GO
