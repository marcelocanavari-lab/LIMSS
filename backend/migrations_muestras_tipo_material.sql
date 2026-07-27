-- ============================================================
-- MIGRACIÓN: lims_muestras.tipo_material
-- ------------------------------------------------------------
-- BUG: el filtro por tipo de material en Consulta de Muestras
-- (analista_qc/qa/admin) no encontraba nada al filtrar por
-- "Granel", aunque existieran muestras de ese tipo. Causa: el
-- filtro inferSa el tipo desde la especificación vigente
-- vinculada (lims_muestras.id_especificacion -> lims_especificaciones
-- .tipo_material), pero (a) muchas muestras no tienen especificación
-- vinculada (id_especificacion NULL) y (b) hoy no existe NINGUNA
-- especificación con tipo_material='granel' en el sistema -- el
-- EXISTS estaba condenado a devolver 0 filas para ese valor.
--
-- El tipo de material en realidad SÍ se elige al crear la muestra
-- (Paso 1 del wizard, MuestraNuevaPage.jsx) pero nunca se persistía:
-- se usaba solo para elegir cómo buscar en el ERP (GIT59SAR.CODSAR)
-- y se descartaba. Esta migración agrega la columna para guardarlo
-- directamente, igual que ya se hace con tipo_referencia.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_muestras') AND name = 'tipo_material'
)
BEGIN
    ALTER TABLE lims_muestras ADD tipo_material VARCHAR(20) NULL;
    PRINT 'Columna lims_muestras.tipo_material agregada';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = 'CK_lims_muestras_tipo_material'
)
BEGIN
    ALTER TABLE lims_muestras
        ADD CONSTRAINT CK_lims_muestras_tipo_material
        CHECK (tipo_material IN ('materia_prima', 'granel', 'semi_elaborado', 'producto_terminado'));
    PRINT 'CHECK CK_lims_muestras_tipo_material agregado';
END
GO

-- Backfill de las muestras ya existentes que tienen especificación
-- vinculada (deriva el tipo desde ahí, es la misma fuente que ya
-- usaba -sin éxito- el filtro viejo). Las que no tienen especificación
-- vinculada (id_especificacion NULL) se completan aparte, a mano o
-- con un script, consultando el ERP (GIT59SAR.CODSAR vía erp_IdM21).
UPDATE m
SET m.tipo_material = esp.tipo_material
FROM lims_muestras m
INNER JOIN lims_especificaciones esp ON esp.id_especificacion = m.id_especificacion
WHERE m.tipo_material IS NULL;
GO
