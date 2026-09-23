/* =====================================================================
   Permitir ensayos duplicados por especificacion (LIMSS)
   Generado: 2026-08-07

   Caso de uso: un producto puede tener mas de un testigo asociado (ej.
   Trimetoprima y Sulfametoxazol), y necesita el mismo ensayo del
   catalogo (ej. "Valoracion") repetido una vez por cada analito, cada
   uno con sus propios limites.

   Bloqueante actual: restriccion UNIQUE 'uq_espec_ensayo' sobre
   (id_especificacion, id_ensayo_maestro) en lims_especificacion_ensayos.
   Confirmado con el error real:
     IntegrityError 23000 - UNIQUE KEY 'uq_espec_ensayo' - clave
     duplicada (317, 87)

   Cambios:
   1) Eliminar la restriccion UNIQUE uq_espec_ensayo.
   2) Agregar columna opcional 'analito' (texto libre, sin validacion
      obligatoria) para diferenciar visualmente cuando el mismo ensayo
      se repite. Nullable, a criterio del usuario cargarla o no.

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

-- 1) Sacar la restriccion que bloquea la duplicacion
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'uq_espec_ensayo'
      AND object_id = OBJECT_ID('dbo.lims_especificacion_ensayos')
)
    ALTER TABLE dbo.lims_especificacion_ensayos DROP CONSTRAINT uq_espec_ensayo;
GO

-- Si 'uq_espec_ensayo' resulta ser un indice UNIQUE (no una constraint con
-- nombre de constraint), usar esta variante en su lugar:
-- IF EXISTS (
--     SELECT 1 FROM sys.indexes
--     WHERE name = 'uq_espec_ensayo'
--       AND object_id = OBJECT_ID('dbo.lims_especificacion_ensayos')
-- )
--     DROP INDEX uq_espec_ensayo ON dbo.lims_especificacion_ensayos;
-- GO

-- 2) Columna opcional para diferenciar analito/principio activo
IF COL_LENGTH('dbo.lims_especificacion_ensayos', 'analito') IS NULL
    ALTER TABLE dbo.lims_especificacion_ensayos ADD analito VARCHAR(100) NULL;
GO

-- Verificacion
SELECT id_espec_ensayo, id_especificacion, id_ensayo_maestro, analito, metodologia
FROM dbo.lims_especificacion_ensayos
WHERE id_especificacion = 317;
