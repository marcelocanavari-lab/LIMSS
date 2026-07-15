-- ============================================================
-- MIGRACIÓN: tipo_referencia / nro_referencia en lims_muestras
-- ------------------------------------------------------------
-- Hasta ahora toda muestra se identificaba por un Número de IR del ERP
-- (GIN01CPB.NUMCOMO). Materia Prima sigue por IR, pero Granel/Semi-Elaborado/
-- Producto Terminado se identifican por un número de lote de producción
-- interna (ebr_lotes, en la base del eBR) -- no tienen IR ni proveedor.
--
-- tipo_referencia/nro_referencia reemplazan a erp_nro_ir como identificador
-- canónico. erp_nro_ir queda nullable y deprecada (no se completa en altas
-- nuevas, no se borra para no perder histórico).
--
-- lims_aprobaciones_lote (el puente que el eBR lee para REQ-DEC-005) usaba
-- erp_nro_ir como parte de su clave única -- se migra a nro_referencia para
-- que el puente siga funcionando para los 4 tipos de material.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

-- ── lims_muestras: agregar columnas nuevas ──────────────────────
IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_muestras') AND name = 'tipo_referencia'
)
BEGIN
    ALTER TABLE lims_muestras ADD tipo_referencia VARCHAR(10) NULL;
    PRINT 'Columna tipo_referencia agregada a lims_muestras';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_muestras') AND name = 'nro_referencia'
)
BEGIN
    ALTER TABLE lims_muestras ADD nro_referencia VARCHAR(50) NULL;
    PRINT 'Columna nro_referencia agregada a lims_muestras';
END
GO

-- ── Backfill: todo lo que había hasta ahora fue por IR ──────────
UPDATE lims_muestras
SET tipo_referencia = 'ir', nro_referencia = erp_nro_ir
WHERE tipo_referencia IS NULL;
GO

-- ── Promover a NOT NULL + CHECK ──────────────────────────────────
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_muestras') AND name = 'tipo_referencia' AND is_nullable = 1
)
BEGIN
    ALTER TABLE lims_muestras ALTER COLUMN tipo_referencia VARCHAR(10) NOT NULL;
    ALTER TABLE lims_muestras
        ADD CONSTRAINT CK_lims_muestras_tipo_referencia CHECK (tipo_referencia IN ('ir','lote'));
    PRINT 'tipo_referencia ahora es NOT NULL con CHECK (ir|lote)';
END
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_muestras') AND name = 'nro_referencia' AND is_nullable = 1
)
BEGIN
    ALTER TABLE lims_muestras ALTER COLUMN nro_referencia VARCHAR(50) NOT NULL;
    PRINT 'nro_referencia ahora es NOT NULL';
END
GO

-- ── erp_nro_ir queda deprecada (nullable, sin uso en altas nuevas) ─
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_muestras') AND name = 'erp_nro_ir' AND is_nullable = 0
)
BEGIN
    ALTER TABLE lims_muestras ALTER COLUMN erp_nro_ir VARCHAR(20) NULL;
    PRINT 'erp_nro_ir ahora es NULL (deprecada, reemplazada por tipo_referencia/nro_referencia)';
END
GO

-- ── lims_aprobaciones_lote: migrar la clave puente hacia el eBR ──
IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_aprobaciones_lote') AND name = 'nro_referencia'
)
BEGIN
    ALTER TABLE lims_aprobaciones_lote ADD nro_referencia VARCHAR(50) NULL;
    PRINT 'Columna nro_referencia agregada a lims_aprobaciones_lote';
END
GO

UPDATE lims_aprobaciones_lote
SET nro_referencia = erp_nro_ir
WHERE nro_referencia IS NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints WHERE name = 'UQ_lims_aprobaciones_lote_referencia'
)
BEGIN
    -- Borrar la UNIQUE vieja (erp_nro_ir, erp_CODART) -- nombre explícito
    -- original: uq_aprobacion_ir_art (Docs/LIMSS_crear_BD.sql)
    IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'uq_aprobacion_ir_art')
    BEGIN
        ALTER TABLE lims_aprobaciones_lote DROP CONSTRAINT uq_aprobacion_ir_art;
        PRINT 'Restricción UNIQUE anterior de lims_aprobaciones_lote eliminada: uq_aprobacion_ir_art';
    END

    IF EXISTS (
        SELECT 1 FROM sys.columns
        WHERE object_id = OBJECT_ID('lims_aprobaciones_lote') AND name = 'nro_referencia' AND is_nullable = 1
    )
    BEGIN
        ALTER TABLE lims_aprobaciones_lote ALTER COLUMN nro_referencia VARCHAR(50) NOT NULL;
    END

    ALTER TABLE lims_aprobaciones_lote
        ADD CONSTRAINT UQ_lims_aprobaciones_lote_referencia UNIQUE (nro_referencia, erp_CODART);
    PRINT 'Restricción UNIQUE de lims_aprobaciones_lote migrada a (nro_referencia, erp_CODART)';
END
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_aprobaciones_lote') AND name = 'erp_nro_ir' AND is_nullable = 0
)
BEGIN
    ALTER TABLE lims_aprobaciones_lote ALTER COLUMN erp_nro_ir VARCHAR(20) NULL;
    PRINT 'lims_aprobaciones_lote.erp_nro_ir ahora es NULL (deprecada)';
END
GO
