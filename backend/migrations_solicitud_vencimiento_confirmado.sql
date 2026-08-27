-- ============================================================
-- MIGRACIÓN: confirmación explícita de "sin vencimiento" en Ejecutar Muestreo
-- ------------------------------------------------------------
-- fecha_vencimiento_real (ver migrations_solicitudes_muestreo_datos_
-- fisicos_v2.sql) queda en NULL tanto si el muestreador todavía no revisó
-- el campo como si revisó el envase y confirmó que el artículo genuinamente
-- no tiene vencimiento -- son dos situaciones distintas (una es un olvido,
-- la otra una confirmación real) que hasta ahora se guardaban igual.
--
-- sin_vencimiento_confirmado (bit, default 0) distingue el segundo caso: se
-- marca en 1 solo cuando la persona tildó explícitamente "Este material no
-- tiene fecha de vencimiento" en Ejecutar Muestreo, nunca por omisión.
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
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_solicitudes_muestreo') AND name = 'sin_vencimiento_confirmado'
)
BEGIN
    ALTER TABLE lims_solicitudes_muestreo
        ADD sin_vencimiento_confirmado BIT NOT NULL CONSTRAINT DF_lims_solicitudes_muestreo_sin_vencimiento_confirmado DEFAULT 0;
    PRINT 'Columna sin_vencimiento_confirmado agregada a lims_solicitudes_muestreo';
END
GO
