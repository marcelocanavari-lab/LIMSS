/* =====================================================================
   Agregar nombre del material a lims_agente_control
   Generado: 2026-08-12

   Hoy la tabla solo guarda erp_codart (codigo), no el nombre del
   material -- la pantalla de evaluaciones del agente no puede mostrar
   a que material corresponde un error sin ir a buscarlo aparte.

   Correr contra LIMSS (produccion) Y LIMSS_DEV.
   ===================================================================== */

IF COL_LENGTH('dbo.lims_agente_control', 'erp_desart') IS NULL
    ALTER TABLE dbo.lims_agente_control ADD erp_desart VARCHAR(100) NULL;
GO

SELECT TOP 5 * FROM dbo.lims_agente_control ORDER BY id DESC;
