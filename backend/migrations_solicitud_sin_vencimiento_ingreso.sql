-- ============================================================
-- MIGRACIÓN: confirmar explícitamente "sin vencimiento" en el ingreso
-- ------------------------------------------------------------
-- lims_solicitudes_muestreo ya tiene fecha_vencimiento (precargada desde el
-- ERP -- VENCOM -- al crear la solicitud, editable por QA) y, aparte,
-- fecha_vencimiento_real / sin_vencimiento_confirmado (confirmados en
-- Ejecutar Muestreo al revisar el envase físico, ver migrations_solicitud_
-- vencimiento_confirmado.sql). Esta columna nueva es un mecanismo
-- INDEPENDIENTE de ese par -- mismo patrón de UX (checkbox "no tiene
-- vencimiento" que limpia/deshabilita el campo de fecha), pero aplicado al
-- campo de vencimiento del INGRESO (fecha_vencimiento, dato del proveedor
-- tal como viene en el ERP), no al confirmado físicamente después. No
-- reutiliza sin_vencimiento_confirmado porque ese nombre ya está tomado por
-- el otro campo, con otro consumidor (el aviso del remito).
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS_DEV (SQL Server Management Studio) -- LIMSS_DEV
-- es una copia independiente de LIMSS para desarrollo, no tocar producción.
-- ============================================================

USE [LIMSS_DEV];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_solicitudes_muestreo') AND name = 'sin_vencimiento_ingreso_confirmado'
)
BEGIN
    ALTER TABLE lims_solicitudes_muestreo
        ADD sin_vencimiento_ingreso_confirmado BIT NOT NULL CONSTRAINT DF_lims_solicitudes_muestreo_sin_venc_ingreso DEFAULT 0;
    PRINT 'Columna sin_vencimiento_ingreso_confirmado agregada a lims_solicitudes_muestreo';
END
GO
