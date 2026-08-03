-- ============================================================
-- MIGRACIÓN: datos físicos de identificación de la MP en la Orden de
-- Trabajo digital del muestreador
-- ------------------------------------------------------------
-- Corrección de flujo: el muestreador NO carga resultados de ensayos (eso
-- es tarea de QC/QA vía el flujo de Envío ya existente). Lo único que
-- completa al ejecutar el muestreo son datos físicos observables:
--   - Datos del contenedor: ya existían (aspecto_externo, cierre,
--     aspecto_interno, precintos -- ver migrations_solicitudes_muestreador_
--     lab_interno.sql).
--   - Datos de identificación de la MP (réplica de la sección "3. ASPECTO
--     DE LA MATERIA PRIMA" de la Planilla de Muestreo P_CC002-2): materias
--     extrañas, olor, color -- no había columnas para esto.
--   - N° de bultos efectivamente muestreados: distinto de nro_bultos (el
--     total de bultos del ingreso, cargado por QA al crear la solicitud).
--   - Observaciones propias del muestreo: se agrega una columna separada de
--     "observaciones" (esa la carga QA al crear la solicitud) para no pisar
--     ese dato.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_solicitudes_muestreo') AND name = 'materias_extranas'
)
BEGIN
    ALTER TABLE lims_solicitudes_muestreo
        ADD materias_extranas      VARCHAR(200) NULL,
            olor                   VARCHAR(200) NULL,
            color                  VARCHAR(200) NULL,
            nro_bultos_muestreados INT NULL,
            observaciones_muestreo VARCHAR(500) NULL;
    PRINT 'Columnas de identificación de la MP y muestreo agregadas a lims_solicitudes_muestreo';
END
GO
