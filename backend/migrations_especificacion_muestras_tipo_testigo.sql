-- ============================================================
-- MIGRACIÓN: tipo_muestra admite 'testigo'
-- ------------------------------------------------------------
-- lims_especificacion_muestras.tipo_muestra solo aceptaba
-- ('analisis','contramuestra'); se agrega 'testigo' como tercer valor
-- válido (muestras definidas que en realidad son testigos a tomar, no
-- análisis ni contramuestra propiamente dichos).
--
-- La restricción original se creó sin nombre explícito (SQL Server le
-- asignó uno autogenerado tipo CK__lims_espe__..., confirmado en vivo:
-- CK__lims_espe__tipo___0E391C95), así que hay que ubicarla dinámicamente
-- antes de reemplazarla -- mismo patrón que migrations_especificaciones_
-- semi_elaborado.sql. Idempotente: si la restricción nueva (con nombre
-- fijo) ya existe, no hace nada.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = 'ck_tipo_muestra'
)
BEGIN
    DECLARE @constraint_name NVARCHAR(200);
    SELECT @constraint_name = cc.name
    FROM sys.check_constraints cc
    INNER JOIN sys.columns col
        ON col.object_id = cc.parent_object_id AND col.column_id = cc.parent_column_id
    WHERE cc.parent_object_id = OBJECT_ID('lims_especificacion_muestras') AND col.name = 'tipo_muestra';

    IF @constraint_name IS NOT NULL
    BEGIN
        EXEC('ALTER TABLE lims_especificacion_muestras DROP CONSTRAINT [' + @constraint_name + ']');
        PRINT 'Restricción CHECK anterior de tipo_muestra eliminada: ' + @constraint_name;
    END

    ALTER TABLE lims_especificacion_muestras
        ADD CONSTRAINT ck_tipo_muestra
        CHECK (tipo_muestra IN ('analisis','contramuestra','testigo'));
    PRINT 'Restricción CHECK de tipo_muestra actualizada (agregado testigo)';
END
GO
