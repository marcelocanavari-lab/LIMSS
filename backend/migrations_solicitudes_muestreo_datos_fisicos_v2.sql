-- ============================================================
-- MIGRACIÓN: campos físicos adicionales de la Orden de Trabajo digital
-- ------------------------------------------------------------
-- Sección A del formulario digital del muestreador incorpora datos que
-- todavía no tenían columna propia en lims_solicitudes_muestreo:
--   - identificacion_contenedor: texto libre (rótulo/código físico del
--     contenedor), se imprime junto a las fechas reales en la sección
--     "2. IDENTIFICACIÓN DEL CONTENEDOR" de la Planilla de Muestreo.
--   - fecha_vencimiento_real / fecha_reanalisis_real: fechas verificadas
--     físicamente por el muestreador al momento de muestrear -- distintas
--     de fecha_vencimiento (dato del ERP) y fecha_reanalisis (estimada por
--     QA al crear la solicitud).
--   - aspecto_mp: aspecto general de la materia prima, distinto de
--     materias_extranas (que ya existe, ver migrations_solicitudes_datos_
--     identificacion_mp.sql).
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_solicitudes_muestreo') AND name = 'aspecto_mp'
)
BEGIN
    ALTER TABLE lims_solicitudes_muestreo
        ADD identificacion_contenedor VARCHAR(200) NULL,
            fecha_vencimiento_real    DATETIME NULL,
            fecha_reanalisis_real     DATETIME NULL,
            aspecto_mp                VARCHAR(200) NULL;
    PRINT 'Columnas físicas adicionales (v2) agregadas a lims_solicitudes_muestreo';
END
GO
