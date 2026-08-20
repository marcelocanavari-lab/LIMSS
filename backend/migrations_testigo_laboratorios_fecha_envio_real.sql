-- ============================================================
-- MIGRACIÓN: fecha real de envío del testigo al laboratorio
-- ------------------------------------------------------------
-- lims_testigo_laboratorios no tenía forma de registrar cuándo
-- se despachó realmente el testigo hacia ese laboratorio -- el
-- remito mostraba la fecha tipeada al crear el remito, que no
-- necesariamente coincidía con el despacho real. Se agrega
-- fecha_envio_real NULL (se carga a mano cuando el testigo
-- efectivamente se envía) para que el remito la use como fuente
-- de verdad.
--
-- Idempotente: si la columna ya existe, no hace nada.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS_DEV];
GO

IF COL_LENGTH('lims_testigo_laboratorios', 'fecha_envio_real') IS NULL
BEGIN
    ALTER TABLE lims_testigo_laboratorios
        ADD fecha_envio_real DATE NULL;
    PRINT 'Columna fecha_envio_real agregada a lims_testigo_laboratorios';
END
GO
