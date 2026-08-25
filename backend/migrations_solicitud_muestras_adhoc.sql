-- ============================================================
-- MIGRACIÓN: soporte para muestras ad-hoc en lims_solicitud_muestras
-- ------------------------------------------------------------
-- Hasta ahora cada fila de lims_solicitud_muestras tenía que referenciar una
-- muestra definida en lims_especificacion_muestras (id_espec_muestra NOT
-- NULL). Para poder agregar una muestra puntual al confirmar el muestreo
-- (una vez, sin modificar la especificación del producto), esta migración:
--   1) vuelve nullable id_espec_muestra,
--   2) agrega tipo_muestra/unidad propios de la fila (se usan solo cuando
--      id_espec_muestra es NULL -- ver COALESCE en
--      _obtener_muestras_confirmadas, backend/app/api/routes/solicitudes_muestreo.py),
--   3) agrega ad_hoc para poder distinguir en el historial cuáles filas
--      fueron agregadas a mano.
--
-- Cada paso va en su propio batch (separado con GO): una columna agregada
-- con ALTER TABLE ADD no se puede referenciar (ej. en un CHECK) dentro del
-- mismo batch -- el parser resuelve los nombres de columna contra el
-- esquema que existía al empezar el batch, no contra lo que se agregó más
-- arriba en ese mismo batch (por eso el error "El nombre de columna
-- 'tipo_muestra' no es válido" si todo va junto).
--
-- Idempotente (se puede correr más de una vez sin error).
--
-- Ejecutar en la BD LIMSS_DEV (SQL Server Management Studio) -- el usuario
-- de aplicación (limss_app) no tiene permiso ALTER/VIEW DEFINITION.
-- ============================================================

USE [LIMSS_DEV];
GO

-- 1) id_espec_muestra nullable (la FK existente sigue vigente; NULL
--    simplemente no se valida contra ella, que es el comportamiento de
--    SQL Server para columnas FK nullable).
IF OBJECT_ID('lims_solicitud_muestras') IS NOT NULL AND EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_solicitud_muestras')
      AND name = 'id_espec_muestra' AND is_nullable = 0
)
BEGIN
    ALTER TABLE lims_solicitud_muestras ALTER COLUMN id_espec_muestra INT NULL;
    PRINT 'id_espec_muestra ahora es nullable';
END
GO

-- 2) tipo_muestra propio de la fila (solo para filas ad-hoc)
IF OBJECT_ID('lims_solicitud_muestras') IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_solicitud_muestras') AND name = 'tipo_muestra'
)
BEGIN
    ALTER TABLE lims_solicitud_muestras ADD tipo_muestra VARCHAR(20) NULL;
    PRINT 'Columna tipo_muestra agregada';
END
GO

-- El CHECK va en su propio batch: recién acá tipo_muestra ya existe de
-- verdad para el parser.
IF OBJECT_ID('lims_solicitud_muestras') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_solicitud_muestras') AND name = 'tipo_muestra')
   AND NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID('lims_solicitud_muestras')
      AND name = 'CK_lims_solicitud_muestras_tipo_muestra'
)
BEGIN
    ALTER TABLE lims_solicitud_muestras
        ADD CONSTRAINT CK_lims_solicitud_muestras_tipo_muestra
        CHECK (tipo_muestra IS NULL OR tipo_muestra IN ('analisis','contramuestra','testigo'));
    PRINT 'CHECK CK_lims_solicitud_muestras_tipo_muestra agregado';
END
GO

-- 3) unidad propia de la fila (solo para filas ad-hoc)
IF OBJECT_ID('lims_solicitud_muestras') IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_solicitud_muestras') AND name = 'unidad'
)
BEGIN
    ALTER TABLE lims_solicitud_muestras ADD unidad VARCHAR(20) NULL;
    PRINT 'Columna unidad agregada';
END
GO

-- 4) ad_hoc: trazabilidad de qué filas se agregaron a mano
IF OBJECT_ID('lims_solicitud_muestras') IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_solicitud_muestras') AND name = 'ad_hoc'
)
BEGIN
    ALTER TABLE lims_solicitud_muestras ADD ad_hoc BIT NOT NULL DEFAULT 0;
    PRINT 'Columna ad_hoc agregada';
END
GO
