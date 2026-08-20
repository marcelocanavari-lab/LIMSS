-- ============================================================
-- MIGRACIÓN: Comparación de etiquetas de Material de Empaque con IA
-- (asistencia visual, no reemplaza el criterio de quien inspecciona)
-- ------------------------------------------------------------
-- 1. lims_empaque_referencia: imagen de referencia (arte aprobado) por
--    erp_CODART -- soft-delete (activo=0) al subir una nueva referencia
--    para el mismo artículo, se conserva el historial de versiones. Un
--    índice único FILTRADO (WHERE activo = 1) garantiza a nivel de base
--    que haya como máximo una referencia activa por artículo a la vez
--    (mismo patrón que UQ_caja_muestras_activa en migrations_cajas.sql).
-- 2. lims_resultados.imagen_comparacion_path / observacion_ia: la foto de
--    la etiqueta recibida en esta inspección puntual y el texto de
--    diferencias que devuelve Claude (ver app/services/comparacion_
--    empaque_ia.py) -- ninguna de las dos decide ni pre-carga el
--    Cumple/No cumple, que lo sigue completando la persona.
--
-- Tablas ya creadas manualmente antes de esta migración; el CREATE/ALTER
-- queda acá solo para que el archivo refleje el esquema real (mismo
-- criterio ya usado en migrations_cajas.sql).
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS_DEV (SQL Server Management Studio) -- LIMSS_DEV
-- es una copia independiente de LIMSS para desarrollo, no tocar producción.
-- ============================================================

USE [LIMSS_DEV];
GO

-- 1. Imagen de referencia por artículo de empaque -----------------------

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_empaque_referencia')
BEGIN
    CREATE TABLE lims_empaque_referencia (
        id_referencia       INT IDENTITY(1,1)  PRIMARY KEY,
        erp_CODART          VARCHAR(20)         NOT NULL,
        imagen_path         VARCHAR(300)        NOT NULL,
        nombre_original     VARCHAR(200)        NOT NULL,
        activo              BIT                 NOT NULL DEFAULT 1,
        id_usuario_carga    INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_carga         DATETIME            NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Tabla lims_empaque_referencia creada';

    CREATE UNIQUE INDEX UQ_empaque_referencia_activa ON lims_empaque_referencia(erp_CODART) WHERE activo = 1;
    PRINT 'Índice único filtrado UQ_empaque_referencia_activa creado';
END
GO

-- 2. Comparación con IA en lims_resultados -----------------------------

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_resultados') AND name = 'imagen_comparacion_path'
)
BEGIN
    ALTER TABLE lims_resultados ADD imagen_comparacion_path VARCHAR(300) NULL;
    PRINT 'Columna lims_resultados.imagen_comparacion_path agregada';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_resultados') AND name = 'observacion_ia'
)
BEGIN
    ALTER TABLE lims_resultados ADD observacion_ia NVARCHAR(2000) NULL;
    PRINT 'Columna lims_resultados.observacion_ia agregada';
END
GO
