/* =====================================================================
   Agregar nro_ir legible a lims_agente_control
   Generado: 2026-08-12

   Hoy la pantalla del agente muestra N01Id (el identificador interno
   del ERP), que no significa nada para un humano. Se guarda el
   "NNN/AA" reconstruido (formatear_nro_ir de erp_ir.py) en el momento
   de la evaluacion, para no tener que recalcularlo cada vez que se
   muestra la pantalla.

   Correr contra LIMSS (produccion) y LIMSS_DEV.
   ===================================================================== */

IF COL_LENGTH('dbo.lims_agente_control', 'nro_ir') IS NULL
    ALTER TABLE dbo.lims_agente_control ADD nro_ir VARCHAR(10) NULL;
GO

SELECT TOP 5 * FROM dbo.lims_agente_control ORDER BY id DESC;
