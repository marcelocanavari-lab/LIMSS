-- ============================================================
-- MIGRACIÓN: lims_aprobaciones_lote pasa a ser append-only real
-- ------------------------------------------------------------
-- La Mod 5/6 había migrado la clave puente de erp_nro_ir a nro_referencia
-- pero mantuvo la restricción UNIQUE(nro_referencia, erp_CODART) con upsert
-- (UPDATE si ya existía la fila). El URS (REQ-DEC-005, Etapa 3/3 Parte C)
-- pide explícitamente que NUNCA se haga UPDATE: cada dictamen inserta una
-- fila nueva, y el eBR toma siempre la más reciente por (nro_referencia,
-- erp_CODART) ordenando por fecha_hora. Esto coincide con el comentario
-- original del script de creación ("Inmutable: no se borra, se agrega una
-- fila nueva si cambia"), que la UNIQUE contradecía.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

-- La Mod 5/6 (migrations_muestras_tipo_referencia.sql) nunca llegó a
-- correr la parte de lims_aprobaciones_lote en esta base: la columna
-- nro_referencia no existía y erp_nro_ir seguía NOT NULL. Se completa acá
-- (sin volver a crear la UNIQUE vieja, que es justamente lo que este script
-- elimina más abajo).
IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_aprobaciones_lote') AND name = 'nro_referencia')
BEGIN
    ALTER TABLE lims_aprobaciones_lote ADD nro_referencia VARCHAR(50) NULL;
    PRINT 'Columna nro_referencia agregada a lims_aprobaciones_lote';
END
GO

UPDATE lims_aprobaciones_lote
SET nro_referencia = erp_nro_ir
WHERE nro_referencia IS NULL;
GO

IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_aprobaciones_lote') AND name = 'nro_referencia' AND is_nullable = 1)
BEGIN
    ALTER TABLE lims_aprobaciones_lote ALTER COLUMN nro_referencia VARCHAR(50) NOT NULL;
    PRINT 'nro_referencia ahora es NOT NULL en lims_aprobaciones_lote';
END
GO

-- erp_nro_ir queda deprecada: el INSERT append-only (dictamenes.py) ya no
-- la completa, así que no puede seguir siendo NOT NULL.
IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_aprobaciones_lote') AND name = 'erp_nro_ir' AND is_nullable = 0)
BEGIN
    ALTER TABLE lims_aprobaciones_lote ALTER COLUMN erp_nro_ir VARCHAR(20) NULL;
    PRINT 'lims_aprobaciones_lote.erp_nro_ir ahora es NULL (deprecada)';
END
GO

IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'uq_aprobacion_ir_art' AND parent_object_id = OBJECT_ID('lims_aprobaciones_lote'))
BEGIN
    ALTER TABLE lims_aprobaciones_lote DROP CONSTRAINT uq_aprobacion_ir_art;
    PRINT 'Restricción UNIQUE de lims_aprobaciones_lote eliminada -- la tabla ahora es append-only real';
END
GO

-- El eBR toma siempre la fila más reciente por (nro_referencia, erp_CODART,
-- fecha_hora); se agrega fecha_hora al índice existente para esa lectura.
IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_aprobaciones_ir' AND object_id = OBJECT_ID('lims_aprobaciones_lote'))
BEGIN
    DROP INDEX ix_aprobaciones_ir ON lims_aprobaciones_lote;
END
CREATE INDEX ix_aprobaciones_ir ON lims_aprobaciones_lote(nro_referencia, estado, fecha_hora);
GO
