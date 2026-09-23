/* =====================================================================
   Guardar N01Id junto con el numero de IR, para eliminar la ambiguedad
   de volver a resolver "NNN/AA" -> comprobante cada vez
   Generado: 2026-08-18

   Con esto, cualquier solicitud/muestra que ya resolvio su IR una vez
   (sea por el agente o por carga manual) puede volver a consultar ESE
   comprobante puntual por N01Id -- sin depender de NUMCOMO+año, que
   puede colisionar dentro del mismo tipo de comprobante (confirmado:
   casos activos, no solo del arrastre de 2020).

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF COL_LENGTH('dbo.lims_solicitudes_muestreo', 'erp_n01id') IS NULL
    ALTER TABLE dbo.lims_solicitudes_muestreo ADD erp_n01id INT NULL;

IF COL_LENGTH('dbo.lims_muestras', 'erp_n01id') IS NULL
    ALTER TABLE dbo.lims_muestras ADD erp_n01id INT NULL;
GO

-- Verificacion
SELECT id_solicitud, erp_nro_ir, erp_n01id FROM dbo.lims_solicitudes_muestreo ORDER BY id_solicitud DESC;
SELECT id_muestra, erp_nro_ir, erp_n01id FROM dbo.lims_muestras ORDER BY id_muestra DESC;
