/* =====================================================================
   Checklist de etapa "muestreo" configurable por especificacion
   Generado: 2026-08-14

   Reemplaza los campos fijos de muestreo fisico (aspecto_externo,
   cierre, aspecto_interno, precintos -- los que se convirtieron a
   botones Cumple/No cumple en una sesion anterior) por items
   configurables por especificacion, igual que ya funcionan los
   ensayos de laboratorio. Cada especificacion define que items de
   "etapa muestreo" le corresponden -- no hay logica especial por
   categoria de material, es la misma tabla y el mismo mecanismo que
   ya existe para ensayos de analisis.

   Las solicitudes/muestras YA EXISTENTES (confirmado: solo 1 solicitud
   y 4 muestras en produccion) conservan sus columnas fijas viejas
   (aspecto_externo, cierre, etc.) intactas -- no se tocan, quedan como
   registro historico. Las solicitudes NUEVAS usan el mecanismo nuevo.

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

-- 1) Columna "etapa" en el catalogo de ensayos de especificacion
IF COL_LENGTH('dbo.lims_especificacion_ensayos', 'etapa') IS NULL
    ALTER TABLE dbo.lims_especificacion_ensayos
        ADD etapa VARCHAR(20) NOT NULL DEFAULT 'analisis';
        -- 'muestreo' | 'analisis' -- todo lo existente hasta ahora
        -- queda clasificado como 'analisis' automaticamente por el
        -- DEFAULT, sin necesidad de tocarlo.
GO

-- 2) Tabla de resultados de etapa muestreo -- paralela a lims_resultados,
--    SIN id_envio (el muestreo fisico pasa antes de que exista ningun
--    envio). Misma forma que lims_resultados para que sea facil de
--    entender y de reportar en paralelo.
IF OBJECT_ID('dbo.lims_resultados_muestreo', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_resultados_muestreo (
        id_resultado          INT IDENTITY(1,1) PRIMARY KEY,
        id_muestra             INT NOT NULL,
        id_espec_ensayo        INT NOT NULL,
        valor_cualitativo      VARCHAR(50) NULL,   -- 'Cumple' / 'No cumple'
        dentro_especificacion  BIT NULL,
        id_usuario_carga       INT NOT NULL,
        fecha_carga             DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT FK_resultados_muestreo_muestra
            FOREIGN KEY (id_muestra) REFERENCES dbo.lims_muestras(id_muestra),
        CONSTRAINT FK_resultados_muestreo_espec_ensayo
            FOREIGN KEY (id_espec_ensayo) REFERENCES dbo.lims_especificacion_ensayos(id_espec_ensayo),
        CONSTRAINT FK_resultados_muestreo_usuario
            FOREIGN KEY (id_usuario_carga) REFERENCES dbo.lims_usuarios(id_usuario),
        -- Un mismo item de checklist no deberia cargarse dos veces
        -- para la misma muestra
        CONSTRAINT UQ_resultados_muestreo UNIQUE (id_muestra, id_espec_ensayo)
    );
END
GO

-- 3) Sembrar los items de etapa "muestreo" por defecto en las
--    especificaciones existentes, segun tipo_material -- punto de
--    partida razonable, cada especificacion se puede ajustar despues
--    a mano (agregar/sacar items puntuales) desde la pantalla de
--    especificaciones, igual que ya se hace con los ensayos de
--    analisis.
--
--    OJO: este bloque asume que existe un id_ensayo_maestro por cada
--    item de checklist (Aspecto externo del contenedor, Cierre, etc.)
--    en lims_ensayos_maestro. Si todavia no existen, crearlos primero
--    (ver paso 3a) antes de correr el paso 3b.

-- 3a) Crear los ensayos maestro del checklist si no existen todavia
--     (nombre debe coincidir exacto con lo que se use en el paso 3b)
IF NOT EXISTS (SELECT 1 FROM dbo.lims_ensayos_maestro WHERE nombre_ensayo = 'Aspecto externo del contenedor')
    INSERT INTO dbo.lims_ensayos_maestro (nombre_ensayo) VALUES ('Aspecto externo del contenedor');

IF NOT EXISTS (SELECT 1 FROM dbo.lims_ensayos_maestro WHERE nombre_ensayo = 'Cierre')
    INSERT INTO dbo.lims_ensayos_maestro (nombre_ensayo) VALUES ('Cierre');

IF NOT EXISTS (SELECT 1 FROM dbo.lims_ensayos_maestro WHERE nombre_ensayo = 'Aspecto interno')
    INSERT INTO dbo.lims_ensayos_maestro (nombre_ensayo) VALUES ('Aspecto interno');

IF NOT EXISTS (SELECT 1 FROM dbo.lims_ensayos_maestro WHERE nombre_ensayo = 'Precintos')
    INSERT INTO dbo.lims_ensayos_maestro (nombre_ensayo) VALUES ('Precintos');

IF NOT EXISTS (SELECT 1 FROM dbo.lims_ensayos_maestro WHERE nombre_ensayo = 'Materias extrañas')
    INSERT INTO dbo.lims_ensayos_maestro (nombre_ensayo) VALUES ('Materias extrañas');

IF NOT EXISTS (SELECT 1 FROM dbo.lims_ensayos_maestro WHERE nombre_ensayo = 'Olor')
    INSERT INTO dbo.lims_ensayos_maestro (nombre_ensayo) VALUES ('Olor');

IF NOT EXISTS (SELECT 1 FROM dbo.lims_ensayos_maestro WHERE nombre_ensayo = 'Color')
    INSERT INTO dbo.lims_ensayos_maestro (nombre_ensayo) VALUES ('Color');
GO

-- 3b) Sembrar en cada especificacion vigente que TODAVIA NO tenga
--     ningun item de etapa 'muestreo' cargado -- no pisa nada si ya
--     se configuro algo a mano.
DECLARE @orden_base INT = 900; -- despues de los ensayos de analisis existentes, para que aparezcan al final salvo que se reordenen a mano

INSERT INTO dbo.lims_especificacion_ensayos
    (id_especificacion, id_ensayo_maestro, orden, tipo_dato, obligatorio, requerido_por_defecto, etapa, activo)
SELECT
    e.id_especificacion,
    em.id_ensayo_maestro,
    @orden_base + ROW_NUMBER() OVER (PARTITION BY e.id_especificacion ORDER BY em.nombre_ensayo),
    'cualitativo',
    0,
    1,
    'muestreo',
    1
FROM dbo.lims_especificaciones e
CROSS JOIN dbo.lims_ensayos_maestro em
WHERE e.vigente = 1
  AND (
        -- Material de Empaque: set reducido
        (e.tipo_material = 'Material de Empaque' AND em.nombre_ensayo IN
            ('Aspecto externo del contenedor'))
        OR
        -- Cualquier otro tipo: set completo (sin Cierre, sacado a
        -- pedido -- no aplica bien como chequeo generico tampoco)
        (e.tipo_material <> 'Material de Empaque' AND em.nombre_ensayo IN
            ('Aspecto externo del contenedor', 'Aspecto interno',
             'Precintos', 'Materias extrañas', 'Olor', 'Color'))
      )
  AND NOT EXISTS (
        SELECT 1 FROM dbo.lims_especificacion_ensayos ex
        WHERE ex.id_especificacion = e.id_especificacion AND ex.etapa = 'muestreo'
      );
GO

-- Verificacion
SELECT e.erp_CODART, e.tipo_material, ee.etapa, em.nombre_ensayo, ee.orden
FROM dbo.lims_especificacion_ensayos ee
JOIN dbo.lims_especificaciones e ON e.id_especificacion = ee.id_especificacion
JOIN dbo.lims_ensayos_maestro em ON em.id_ensayo_maestro = ee.id_ensayo_maestro
WHERE ee.etapa = 'muestreo'
ORDER BY e.erp_CODART;
