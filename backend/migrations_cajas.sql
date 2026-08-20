-- ============================================================
-- MIGRACIÓN: Archivo de Contramuestras (cajas físicas)
-- ------------------------------------------------------------
-- 1. lims_cajas: una caja física donde se archivan contramuestras. Estado
--    'activa'/'cerrada' controlado a nivel de aplicación (sin CHECK
--    constraint, mismo criterio que el resto de los "estado" varchar del
--    proyecto). codigo es UNIQUE -- se sugiere un correlativo tipo
--    "CAJA-2026-001" desde la pantalla, pero es editable.
-- 2. lims_caja_muestras: vincula muestras (lims_muestras) a una caja.
--    fecha_retiro en vez de DELETE para conservar historial (mismo
--    criterio que el resto del proyecto -- ver lims_solicitudes_muestreo,
--    lims_agente_control). Un índice único FILTRADO (WHERE fecha_retiro IS
--    NULL) garantiza a nivel de base que una muestra esté en como máximo
--    una caja activa (sin retirar) a la vez -- necesario porque un simple
--    SELECT antes del INSERT no cubre la carrera entre dos personas
--    agregando la misma muestra a dos cajas en simultáneo.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS_DEV (SQL Server Management Studio) -- LIMSS_DEV
-- es una copia independiente de LIMSS para desarrollo, no tocar producción.
-- ============================================================

USE [LIMSS_DEV];
GO

-- 1. Cajas ---------------------------------------------------------------

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_cajas')
BEGIN
    CREATE TABLE lims_cajas (
        id_caja             INT IDENTITY(1,1)  PRIMARY KEY,
        codigo              VARCHAR(20)         NOT NULL,
        ubicacion           VARCHAR(100)        NULL,
        estado              VARCHAR(20)         NOT NULL DEFAULT 'activa',
        fecha_apertura      DATETIME            NOT NULL DEFAULT GETDATE(),
        fecha_cierre        DATETIME            NULL,
        id_usuario_apertura INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        id_usuario_cierre   INT                 NULL     REFERENCES lims_usuarios(id_usuario),
        observaciones       VARCHAR(500)        NULL,
        CONSTRAINT UQ_cajas_codigo UNIQUE (codigo)
    );
    PRINT 'Tabla lims_cajas creada';
END
GO

-- 2. Muestras archivadas por caja -----------------------------------------

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_caja_muestras')
BEGIN
    CREATE TABLE lims_caja_muestras (
        id                  INT IDENTITY(1,1)  PRIMARY KEY,
        id_caja             INT                 NOT NULL REFERENCES lims_cajas(id_caja),
        id_muestra          INT                 NOT NULL REFERENCES lims_muestras(id_muestra),
        fecha_ingreso       DATETIME            NOT NULL DEFAULT GETDATE(),
        id_usuario_ingreso  INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_retiro        DATETIME            NULL,
        id_usuario_retiro   INT                 NULL     REFERENCES lims_usuarios(id_usuario)
    );
    PRINT 'Tabla lims_caja_muestras creada';

    CREATE INDEX IX_caja_muestras_caja ON lims_caja_muestras(id_caja);

    -- Único filtrado: una muestra, como máximo, en una caja activa a la vez.
    CREATE UNIQUE INDEX UQ_caja_muestras_activa ON lims_caja_muestras(id_muestra) WHERE fecha_retiro IS NULL;

    PRINT 'Índices de lims_caja_muestras creados';
END
GO
