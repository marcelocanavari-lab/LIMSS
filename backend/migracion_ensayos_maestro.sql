-- ============================================================
-- MIGRACIÓN: Normalizar tabla de ensayos
-- Separar ensayos maestros de ensayos por especificación
-- ============================================================
USE [LIMSS];
GO

-- ── PASO 1: Crear tabla maestra de ensayos ────────────────────
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_ensayos_maestro')
BEGIN
    CREATE TABLE lims_ensayos_maestro (
        id_ensayo_maestro   INT IDENTITY(1,1)   PRIMARY KEY,
        nombre_ensayo       VARCHAR(300)         NOT NULL,
        bibliografia        VARCHAR(500)         NULL,
        observaciones       NVARCHAR(500)        NULL,
        -- Para deduplicar: mismo nombre = mismo ensayo maestro
        CONSTRAINT uq_ensayo_nombre UNIQUE (nombre_ensayo)
    );
    PRINT 'Tabla lims_ensayos_maestro creada OK';
END
GO

-- ── PASO 2: Poblar maestro con nombres únicos de ensayos ──────
INSERT INTO lims_ensayos_maestro (nombre_ensayo, bibliografia, observaciones)
SELECT DISTINCT 
    nombre_ensayo,
    -- Si todos los registros del mismo nombre tienen la misma bibliografía, usarla
    MAX(bibliografia)  AS bibliografia,
    MAX(observaciones) AS observaciones
FROM lims_ensayos
WHERE nombre_ensayo IS NOT NULL AND nombre_ensayo <> ''
GROUP BY nombre_ensayo;

PRINT 'Ensayos maestros poblados: ' + CAST(@@ROWCOUNT AS VARCHAR);
GO

-- ── PASO 3: Crear nueva tabla de ensayos por especificación ───
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_especificacion_ensayos')
BEGIN
    CREATE TABLE lims_especificacion_ensayos (
        id_espec_ensayo         INT IDENTITY(1,1)   PRIMARY KEY,
        id_especificacion       INT                 NOT NULL
                                REFERENCES lims_especificaciones(id_especificacion),
        id_ensayo_maestro       INT                 NOT NULL
                                REFERENCES lims_ensayos_maestro(id_ensayo_maestro),
        orden                   INT                 NOT NULL,
        metodologia             VARCHAR(500)        NULL,
        tipo_dato               VARCHAR(15)         NOT NULL DEFAULT 'cualitativo'
                                CHECK (tipo_dato IN ('numerico','cualitativo')),
        limite_inferior         DECIMAL(18,4)       NULL,
        limite_superior         DECIMAL(18,4)       NULL,
        unidad_medida           VARCHAR(20)         NULL,
        valor_requerido         NVARCHAR(2000)      NULL,
        especificacion_texto    NVARCHAR(2000)      NULL,
        obligatorio             BIT                 NOT NULL DEFAULT 1,
        requerido_por_defecto   BIT                 NOT NULL DEFAULT 1,
        CONSTRAINT uq_espec_ensayo UNIQUE (id_especificacion, id_ensayo_maestro)
    );
    PRINT 'Tabla lims_especificacion_ensayos creada OK';
END
GO

-- ── PASO 4: Migrar datos de lims_ensayos → nueva tabla ────────
INSERT INTO lims_especificacion_ensayos (
    id_especificacion, id_ensayo_maestro, orden,
    metodologia, tipo_dato, limite_inferior, limite_superior,
    unidad_medida, valor_requerido, especificacion_texto,
    obligatorio, requerido_por_defecto
)
SELECT 
    e.id_especificacion,
    m.id_ensayo_maestro,
    e.orden,
    e.metodologia,
    e.tipo_dato,
    e.limite_inferior,
    e.limite_superior,
    e.unidad_medida,
    e.valor_requerido,
    e.especificacion_texto,
    e.obligatorio,
    e.requerido_por_defecto
FROM lims_ensayos e
INNER JOIN lims_ensayos_maestro m ON m.nombre_ensayo = e.nombre_ensayo;

PRINT 'Ensayos migrados: ' + CAST(@@ROWCOUNT AS VARCHAR);
GO

-- ── PASO 5: Verificación ──────────────────────────────────────
SELECT 
    'lims_ensayos (original)'        AS tabla, COUNT(*) AS registros 
FROM lims_ensayos
UNION ALL
SELECT 
    'lims_ensayos_maestro (nueva)',  COUNT(*) 
FROM lims_ensayos_maestro
UNION ALL
SELECT 
    'lims_especificacion_ensayos (nueva)', COUNT(*) 
FROM lims_especificacion_ensayos;
GO

-- ── PASO 6: Crear índices ─────────────────────────────────────
CREATE INDEX ix_espec_ensayos_espec 
    ON lims_especificacion_ensayos(id_especificacion, orden);
CREATE INDEX ix_espec_ensayos_maestro 
    ON lims_especificacion_ensayos(id_ensayo_maestro);
GO
PRINT 'Índices creados OK';

-- ── PASO 7 (OPCIONAL — ejecutar solo cuando el sistema esté
--    actualizado y verificado): renombrar tabla vieja
-- EXEC sp_rename 'lims_ensayos', 'lims_ensayos_OLD';
-- GO
PRINT '';
PRINT 'MIGRACIÓN COMPLETA.';
PRINT 'La tabla lims_ensayos original se mantiene intacta.';
PRINT 'Verificar el resultado antes de ejecutar el PASO 7.';
GO
