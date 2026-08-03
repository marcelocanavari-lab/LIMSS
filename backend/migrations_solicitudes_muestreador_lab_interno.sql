-- ============================================================
-- MIGRACIÓN: reestructuración del flujo de Solicitudes de Muestreo
-- ------------------------------------------------------------
-- 1. lims_solicitudes_muestreo.id_muestreador: QA asigna un muestreador al
--    crear la solicitud (Etapa 1). El muestreador ve solo lo asignado a él
--    (Etapa 2) y ejecuta el muestreo confirmando la Orden de Trabajo, que
--    ahora crea la muestra automáticamente.
-- 2. lims_laboratorios.es_interno: distingue qué laboratorio es el propio
--    (análisis interno, se carga en la misma Orden de Trabajo) de los
--    externos (van por el flujo de Envío ya existente). El UPDATE que marca
--    cuál lo es NO se incluye acá -- se corre aparte, en solo lectura/DML,
--    una vez confirmada la fila correcta (ver conversación).
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_solicitudes_muestreo') AND name = 'id_muestreador'
)
BEGIN
    ALTER TABLE lims_solicitudes_muestreo
        ADD id_muestreador INT NULL REFERENCES lims_usuarios(id_usuario);
    PRINT 'Columna lims_solicitudes_muestreo.id_muestreador agregada';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_laboratorios') AND name = 'es_interno'
)
BEGIN
    ALTER TABLE lims_laboratorios
        ADD es_interno BIT NOT NULL DEFAULT 0;
    PRINT 'Columna lims_laboratorios.es_interno agregada';
END
GO

-- "Datos del contenedor" (Sección 1 de la Orden de Trabajo digital) -- no
-- había ninguna columna prevista para esto; hoy solo existían como líneas
-- en blanco en el PDF de la Planilla de Muestreo, para completar a mano.
IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_solicitudes_muestreo') AND name = 'aspecto_externo'
)
BEGIN
    ALTER TABLE lims_solicitudes_muestreo
        ADD aspecto_externo VARCHAR(200) NULL,
            cierre           VARCHAR(200) NULL,
            aspecto_interno  VARCHAR(200) NULL,
            precintos        VARCHAR(200) NULL;
    PRINT 'Columnas de datos del contenedor agregadas a lims_solicitudes_muestreo';
END
GO
