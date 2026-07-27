-- ============================================================
-- MIGRACIÓN: recepción/copia firmada para el remito de MUESTRAS
-- ------------------------------------------------------------
-- Replica para lims_remitos (remito de muestra a laboratorio, ver
-- envios.py/pdf_remito.py) la misma constancia de recepción que ya
-- existía solo para lims_remito_testigos_cab (remito de testigos,
-- ver testigos_remitos.py): fecha de recepción, quién lo recibió,
-- y el PDF escaneado de la copia firmada por el laboratorio.
--
-- lims_remitos es append-only (cada "generar" inserta una fila
-- nueva, nunca se pisa una existente -- ver comentario en
-- envios.py). La recepción se registra sobre la fila más reciente
-- de cada envío, igual criterio que ya usa GET /api/envios/{id}/remito
-- (TOP 1 ... ORDER BY id_remito DESC).
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_remitos') AND name = 'pdf_copia_firmada'
)
BEGIN
    ALTER TABLE lims_remitos ADD pdf_copia_firmada VARCHAR(300) NULL;
    PRINT 'Columna lims_remitos.pdf_copia_firmada agregada';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_remitos') AND name = 'fecha_recepcion'
)
BEGIN
    ALTER TABLE lims_remitos ADD fecha_recepcion DATE NULL;
    PRINT 'Columna lims_remitos.fecha_recepcion agregada';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_remitos') AND name = 'recibido_por'
)
BEGIN
    ALTER TABLE lims_remitos ADD recibido_por VARCHAR(100) NULL;
    PRINT 'Columna lims_remitos.recibido_por agregada';
END
GO
