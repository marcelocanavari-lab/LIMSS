-- ============================================================
-- MIGRACIÓN: datos de proveedor/lote/vencimiento en lims_solicitudes_muestreo
-- ------------------------------------------------------------
-- Amplía la Solicitud de Muestreo para poder generar los formularios
-- P_CC002-1 (Orden de Trabajo de Control de Calidad) y P_CC002-2
-- (Planilla de Muestreo de Materias Primas), que necesitan datos del
-- proveedor/ingreso (traídos del ERP al buscar el IR) más varios campos
-- que solo carga el usuario a mano (lote de proveedor, país de origen,
-- fecha de reanálisis, bultos, metodología, fabricante).
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_solicitudes_muestreo') AND name = 'proveedor_codigo'
)
BEGIN
    ALTER TABLE lims_solicitudes_muestreo
        ADD proveedor_codigo     VARCHAR(20)   NULL,
            proveedor_nombre     VARCHAR(200)  NULL,
            lote_proveedor       VARCHAR(20)   NULL,
            fecha_ingreso        DATE          NULL,
            fecha_vencimiento    DATE          NULL,
            fecha_reanalisis     DATE          NULL,
            pais_origen          VARCHAR(100)  NULL,
            cantidad_ingresada   DECIMAL(18,4) NULL,
            unidad_cantidad      VARCHAR(20)   NULL,
            nro_bultos           INT           NULL,
            metodologia_analisis VARCHAR(200)  NULL,
            fabricante           VARCHAR(200)  NULL;
    PRINT 'Columnas de datos de proveedor/ingreso agregadas a lims_solicitudes_muestreo';
END
GO
