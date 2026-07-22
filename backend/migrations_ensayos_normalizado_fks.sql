-- ============================================================
-- MIGRACIÓN: redirigir lims_envio_ensayos y lims_resultados hacia
-- el modelo normalizado (lims_especificacion_ensayos), en vez de
-- lims_ensayos_OLD (la tabla vieja, ya renombrada pero no borrada).
-- ------------------------------------------------------------
-- lims_resultados está vacía (0 filas): sin riesgo de datos, solo
-- se reapunta la FK y se renombra la columna.
--
-- lims_envio_ensayos tiene 1 fila real (id=9, de un envío ya
-- confirmado): se migra su valor de id_ensayo (viejo) al
-- id_espec_ensayo correspondiente, cruzando por
-- (id_especificacion, nombre_ensayo) contra lims_ensayos_OLD y
-- lims_especificacion_ensayos/lims_ensayos_maestro.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

-- ── lims_envio_ensayos ──────────────────────────────────────────

IF COL_LENGTH('lims_envio_ensayos', 'id_ensayo') IS NOT NULL
BEGIN
    -- 1) Soltar la FK vieja (hacia lims_ensayos_OLD) para poder reescribir los valores
    DECLARE @fk1 NVARCHAR(128);
    SELECT @fk1 = fk.name FROM sys.foreign_keys fk
    WHERE fk.parent_object_id = OBJECT_ID('lims_envio_ensayos') AND OBJECT_NAME(fk.referenced_object_id) = 'lims_ensayos_OLD';
    IF @fk1 IS NOT NULL EXEC('ALTER TABLE lims_envio_ensayos DROP CONSTRAINT ' + @fk1);

    -- 2) Migrar los valores existentes: id_ensayo (viejo) -> id_espec_ensayo (nuevo)
    UPDATE ee
    SET ee.id_ensayo = se.id_espec_ensayo
    FROM lims_envio_ensayos ee
    INNER JOIN lims_ensayos_OLD old ON old.id_ensayo = ee.id_ensayo
    INNER JOIN lims_especificacion_ensayos se ON se.id_especificacion = old.id_especificacion
    INNER JOIN lims_ensayos_maestro m ON m.id_ensayo_maestro = se.id_ensayo_maestro AND m.nombre_ensayo = old.nombre_ensayo;

    -- 3) Renombrar la columna para reflejar su nuevo significado
    EXEC sp_rename 'lims_envio_ensayos.id_ensayo', 'id_espec_ensayo', 'COLUMN';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys fk
    WHERE fk.parent_object_id = OBJECT_ID('lims_envio_ensayos') AND OBJECT_NAME(fk.referenced_object_id) = 'lims_especificacion_ensayos'
)
BEGIN
    -- Si alguna fila no pudo migrarse (nombre_ensayo sin match), este ALTER
    -- falla con violación de FK -- señal clara de que hay que revisar a mano
    -- antes de reintentar.
    ALTER TABLE lims_envio_ensayos
        ADD CONSTRAINT FK_envio_ensayos_espec_ensayo FOREIGN KEY (id_espec_ensayo) REFERENCES lims_especificacion_ensayos(id_espec_ensayo);
    PRINT 'lims_envio_ensayos.id_espec_ensayo -> lims_especificacion_ensayos OK';
END
GO

-- ── lims_resultados (vacía, sin migración de datos) ─────────────

IF COL_LENGTH('lims_resultados', 'id_ensayo') IS NOT NULL
BEGIN
    DECLARE @fk2 NVARCHAR(128);
    SELECT @fk2 = fk.name FROM sys.foreign_keys fk
    WHERE fk.parent_object_id = OBJECT_ID('lims_resultados') AND OBJECT_NAME(fk.referenced_object_id) = 'lims_ensayos_OLD';
    IF @fk2 IS NOT NULL EXEC('ALTER TABLE lims_resultados DROP CONSTRAINT ' + @fk2);

    EXEC sp_rename 'lims_resultados.id_ensayo', 'id_espec_ensayo', 'COLUMN';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys fk
    WHERE fk.parent_object_id = OBJECT_ID('lims_resultados') AND OBJECT_NAME(fk.referenced_object_id) = 'lims_especificacion_ensayos'
)
BEGIN
    ALTER TABLE lims_resultados
        ADD CONSTRAINT FK_resultados_espec_ensayo FOREIGN KEY (id_espec_ensayo) REFERENCES lims_especificacion_ensayos(id_espec_ensayo);
    PRINT 'lims_resultados.id_espec_ensayo -> lims_especificacion_ensayos OK';
END
GO
