-- ============================================================
-- MIGRACIÓN: laboratorios que requieren el COAS (protocolo) del proveedor
-- ------------------------------------------------------------
-- Algunos laboratorios externos exigen que se les envíe el protocolo que
-- entrega el proveedor junto con el lote (ya cargado en Solicitudes de
-- Muestreo, ver lims_solicitudes_muestreo.protocolo_proveedor_path) para
-- poder analizar la muestra. requiere_coas_proveedor marca esos
-- laboratorios -- al generar el remito, si está en 1, se adjunta ese
-- protocolo a la copia que va al laboratorio (nunca a la de archivo
-- interno), o se avisa antes de continuar si todavía no está cargado.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD correspondiente (SQL Server Management Studio) --
-- USE apunta a LIMSS_DEV; para producción, cambiar a [LIMSS] antes de
-- correrla ahí.
-- ============================================================

USE [LIMSS_DEV];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_laboratorios') AND name = 'requiere_coas_proveedor'
)
BEGIN
    ALTER TABLE lims_laboratorios
        ADD requiere_coas_proveedor BIT NOT NULL CONSTRAINT DF_lims_laboratorios_requiere_coas_proveedor DEFAULT 0;
    PRINT 'Columna requiere_coas_proveedor agregada a lims_laboratorios';
END
GO
