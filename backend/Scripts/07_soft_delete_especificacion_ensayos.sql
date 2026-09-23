/* =====================================================================
   Soft-delete para ensayos de especificacion (LIMSS)
   Generado: 2026-08-07

   Problema: eliminar_ensayo_especificacion hace un DELETE fisico sobre
   lims_especificacion_ensayos. Si ese ensayo ya tiene resultados
   cargados en lims_envio_ensayos (FK_envio_ensayos_espec_ensayo), el
   DELETE fisico rompe la integridad referencial y SQL Server lo
   rechaza (error 547 confirmado).

   Solucion: agregar activo (BIT) a lims_especificacion_ensayos, igual
   que el resto de las tablas maestras del proyecto (testigos,
   categorias, origenes, etc. ya usan este patron). La "baja" pasa a
   ser activo = 0 en vez de DELETE.

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF COL_LENGTH('dbo.lims_especificacion_ensayos', 'activo') IS NULL
    ALTER TABLE dbo.lims_especificacion_ensayos ADD activo BIT NOT NULL DEFAULT 1;
GO

-- Verificacion
SELECT id_espec_ensayo, id_especificacion, id_ensayo_maestro, analito, activo
FROM dbo.lims_especificacion_ensayos
WHERE id_especificacion = 317;
