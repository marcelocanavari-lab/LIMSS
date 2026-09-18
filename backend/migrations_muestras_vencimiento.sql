-- ============================================================
-- MIGRACIÓN: vencimiento para muestras de Granel/Semi-Elaborado/Producto
-- Terminado (creadas por "Nueva Muestra", sin Solicitud de Muestreo)
-- ------------------------------------------------------------
-- A diferencia de Materia Prima/Material de Empaque (que resuelven el
-- vencimiento en lims_solicitudes_muestreo.fecha_vencimiento, ver
-- migrations_solicitud_sin_vencimiento_ingreso.sql), Granel/Semi-Elaborado/
-- Producto Terminado se crean directo con "Nueva Muestra" (tipo_referencia
-- 'lote', sin ninguna Solicitud asociada) y lims_muestras nunca tuvo un
-- campo de vencimiento -- el dato quedaba sin pedirse nunca, aunque el ERP
-- sí lo tiene (comprobante de tipo LOTE, ver obtener_vencimiento_lote_
-- produccion en erp_lotes.py).
--
-- fecha_vencimiento: precargada del ERP al buscar el material (igual que
-- MaterialEncontrado.fecha_vencimiento para materia prima), corregible por
-- el usuario en el formulario de "Nueva Muestra".
-- sin_vencimiento_confirmado: mismo criterio que sin_vencimiento_ingreso_
-- confirmado en lims_solicitudes_muestreo -- se marca en 1 solo cuando la
-- persona tildó explícitamente "Sin vencimiento", nunca por omisión.
--
-- Idempotente (igual que el resto de backend/*.sql).
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_muestras') AND name = 'fecha_vencimiento'
)
BEGIN
    ALTER TABLE lims_muestras ADD fecha_vencimiento DATE NULL;
    PRINT 'Columna fecha_vencimiento agregada a lims_muestras';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_muestras') AND name = 'sin_vencimiento_confirmado'
)
BEGIN
    ALTER TABLE lims_muestras
        ADD sin_vencimiento_confirmado BIT NOT NULL CONSTRAINT DF_lims_muestras_sin_vencimiento_confirmado DEFAULT 0;
    PRINT 'Columna sin_vencimiento_confirmado agregada a lims_muestras';
END
GO
