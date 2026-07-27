-- ============================================================
-- MIGRACIÓN: flujo de muestras con múltiples envíos por muestra
-- ------------------------------------------------------------
-- Reestructuración del flujo: una muestra puede enviarse a varios
-- laboratorios en paralelo (múltiples filas en lims_envios por
-- id_muestra, cosa que el esquema ya permitía). Lo que no permitía
-- era cargar resultados/protocolo POR ENVÍO: lims_resultados y
-- lims_protocolos estaban anclados a id_muestra. Se agrega id_envio
-- a ambas tablas.
--
-- Además se colapsan los estados intermedios de lims_muestras
-- ('en_transito', 'en_carga_resultados', 'pendiente_dictamen') en
-- un único estado 'en_análisis': con múltiples envíos, "confirmar
-- envío" y "cargar resultados" pueden intercalarse libremente para
-- distintos laboratorios de la misma muestra, así que ya no tiene
-- sentido una cadena lineal de estados para eso. La aptitud para
-- dictamen (¿están todos los ensayos de todos los envíos cargados?)
-- pasa a calcularse en el momento (NOT EXISTS), no a guardarse.
--
-- Verificado contra la base real (solo 7 muestras / 5 envíos / 2
-- resultados / 1 protocolo en este entorno): no hay filas en
-- 'en_transito' ni 'pendiente_dictamen' hoy, solo 4 en
-- 'en_carga_resultados' que se migran a 'en_análisis'.
--
-- Idempotente (igual que el resto de backend/*.sql): cada bloque
-- verifica si ya se aplicó antes de tocar nada.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

-- 1) Reemplazar el CHECK de estado (nombre autogenerado, se ubica
--    dinámicamente como en migrations_especificaciones_semi_elaborado.sql)
--    y migrar los datos a 'en_análisis'. El DROP tiene que ir antes del
--    UPDATE: la restricción vieja no admite 'en_análisis', así que
--    mientras esté activa el UPDATE de datos fallaría.
IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = 'CK_lims_muestras_estado'
)
BEGIN
    DECLARE @constraint_name NVARCHAR(200);
    SELECT @constraint_name = cc.name
    FROM sys.check_constraints cc
    INNER JOIN sys.columns col
        ON col.object_id = cc.parent_object_id AND col.column_id = cc.parent_column_id
    WHERE cc.parent_object_id = OBJECT_ID('lims_muestras') AND col.name = 'estado';

    IF @constraint_name IS NOT NULL
    BEGIN
        EXEC('ALTER TABLE lims_muestras DROP CONSTRAINT [' + @constraint_name + ']');
        PRINT 'Restricción CHECK anterior de lims_muestras.estado eliminada: ' + @constraint_name;
    END

    UPDATE lims_muestras
    SET estado = 'en_análisis'
    WHERE estado IN ('en_transito', 'en_carga_resultados', 'pendiente_dictamen');
    PRINT 'Datos migrados: estados intermedios colapsados a en_análisis';

    ALTER TABLE lims_muestras
        ADD CONSTRAINT CK_lims_muestras_estado
        CHECK (estado IN ('pendiente_envio', 'en_análisis', 'aprobado', 'rechazado', 'cuarentena'));
    PRINT 'Restricción CHECK de lims_muestras.estado actualizada (estados colapsados a en_análisis)';
END
GO

-- 3) lims_resultados: agregar id_envio, backfill, y mover la UNIQUE
--    de (id_muestra, id_espec_ensayo) a (id_envio, id_espec_ensayo)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_resultados') AND name = 'id_envio'
)
BEGIN
    ALTER TABLE lims_resultados ADD id_envio INT NULL;
    PRINT 'Columna lims_resultados.id_envio agregada';
END
GO

UPDATE r
SET r.id_envio = (
    SELECT TOP 1 e.id_envio FROM lims_envios e
    WHERE e.id_muestra = r.id_muestra
    ORDER BY e.id_envio DESC
)
FROM lims_resultados r
WHERE r.id_envio IS NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_resultados') AND name = 'id_envio' AND is_nullable = 1
)
BEGIN
    ALTER TABLE lims_resultados ALTER COLUMN id_envio INT NOT NULL;
    PRINT 'Columna lims_resultados.id_envio promovida a NOT NULL';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_resultados_envio'
)
BEGIN
    ALTER TABLE lims_resultados
        ADD CONSTRAINT FK_resultados_envio FOREIGN KEY (id_envio) REFERENCES lims_envios(id_envio);
    PRINT 'FK_resultados_envio agregada';
END
GO

IF EXISTS (
    SELECT 1 FROM sys.key_constraints WHERE name = 'uq_resultado_muestra_ensayo'
)
BEGIN
    ALTER TABLE lims_resultados DROP CONSTRAINT uq_resultado_muestra_ensayo;
    PRINT 'uq_resultado_muestra_ensayo eliminada';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints WHERE name = 'uq_resultado_envio_ensayo'
)
BEGIN
    ALTER TABLE lims_resultados
        ADD CONSTRAINT uq_resultado_envio_ensayo UNIQUE (id_envio, id_espec_ensayo);
    PRINT 'uq_resultado_envio_ensayo agregada';
END
GO

-- 4) lims_protocolos: agregar id_envio y backfill (mismo patrón)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_protocolos') AND name = 'id_envio'
)
BEGIN
    ALTER TABLE lims_protocolos ADD id_envio INT NULL;
    PRINT 'Columna lims_protocolos.id_envio agregada';
END
GO

UPDATE p
SET p.id_envio = (
    SELECT TOP 1 e.id_envio FROM lims_envios e
    WHERE e.id_muestra = p.id_muestra
    ORDER BY e.id_envio DESC
)
FROM lims_protocolos p
WHERE p.id_envio IS NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_protocolos') AND name = 'id_envio' AND is_nullable = 1
)
BEGIN
    ALTER TABLE lims_protocolos ALTER COLUMN id_envio INT NOT NULL;
    PRINT 'Columna lims_protocolos.id_envio promovida a NOT NULL';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_protocolos_envio'
)
BEGIN
    ALTER TABLE lims_protocolos
        ADD CONSTRAINT FK_protocolos_envio FOREIGN KEY (id_envio) REFERENCES lims_envios(id_envio);
    PRINT 'FK_protocolos_envio agregada';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = 'ix_protocolos_envio'
)
BEGIN
    CREATE INDEX ix_protocolos_envio ON lims_protocolos(id_envio);
    PRINT 'Índice ix_protocolos_envio creado';
END
GO
