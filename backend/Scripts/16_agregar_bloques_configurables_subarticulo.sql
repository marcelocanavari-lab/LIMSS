/* =====================================================================
   Bloques configurables por subarticulo + vinculo especificacion-subarticulo
   Generado: 2026-08-14

   1) lims_especificaciones.erp_codsar: vincula cada especificacion a su
      subarticulo real del ERP (GIT59SAR), resuelto una vez al crear la
      especificacion. Reemplaza tipo_material como fuente de verdad
      para decidir comportamiento -- tipo_material sigue existiendo
      como campo descriptivo, no se borra.

   2) lims_erp_subarticulo_config: 4 columnas nuevas, todas tildadas
      por defecto (para no cambiar nada de lo que ya funciona hasta
      que alguien las ajuste a proposito).

   IMPORTANTE: el backfill de erp_codsar para las especificaciones YA
   EXISTENTES no puede hacerse en este script SQL puro -- requiere
   consultar el ERP en vivo (no hay linked server configurado), y por
   lo tanto tiene que correr a traves del backend (ver el prompt de
   Claude Code que acompaña esta migracion).

   Correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

-- 1) Vinculo especificacion -> subarticulo
IF COL_LENGTH('dbo.lims_especificaciones', 'erp_codsar') IS NULL
    ALTER TABLE dbo.lims_especificaciones ADD erp_codsar VARCHAR(20) NULL;
GO

-- 2) Bloques configurables por subarticulo
IF COL_LENGTH('dbo.lims_erp_subarticulo_config', 'incluye_bloque_muestras') IS NULL
    ALTER TABLE dbo.lims_erp_subarticulo_config ADD incluye_bloque_muestras BIT NOT NULL DEFAULT 1;

IF COL_LENGTH('dbo.lims_erp_subarticulo_config', 'incluye_bloque_analisis_laboratorio') IS NULL
    ALTER TABLE dbo.lims_erp_subarticulo_config ADD incluye_bloque_analisis_laboratorio BIT NOT NULL DEFAULT 1;

IF COL_LENGTH('dbo.lims_erp_subarticulo_config', 'incluye_bloque_muestreo_fisico') IS NULL
    ALTER TABLE dbo.lims_erp_subarticulo_config ADD incluye_bloque_muestreo_fisico BIT NOT NULL DEFAULT 1;

IF COL_LENGTH('dbo.lims_erp_subarticulo_config', 'incluye_bloque_testigos') IS NULL
    ALTER TABLE dbo.lims_erp_subarticulo_config ADD incluye_bloque_testigos BIT NOT NULL DEFAULT 1;
GO

-- Verificacion
SELECT erp_codsar, descripcion, requiere_muestreo, incluye_bloque_muestras,
       incluye_bloque_analisis_laboratorio, incluye_bloque_muestreo_fisico,
       incluye_bloque_testigos
FROM dbo.lims_erp_subarticulo_config;

SELECT id_especificacion, erp_CODART, tipo_material, erp_codsar
FROM dbo.lims_especificaciones;
