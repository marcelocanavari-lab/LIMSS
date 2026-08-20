-- ============================================================
-- MIGRACIÓN: Material de Empaque como tipo_material + módulo de Novedades
-- ------------------------------------------------------------
-- 1. tipo_material admite 'material_empaque' -- cubre los dos subartículos
--    del ERP GIT59SAR '0005' (MATERIAL DE EMPAQUE, codificado) y '0006'
--    (MATERIAL DE EMPAQUE SIN CODIFICAR): en LIMSS es UN solo tipo_material
--    (mismo criterio de especificación/circuito), la distinción codificado/
--    sin codificar solo importa al crear la Solicitud de Muestreo (ver
--    lote_proveedor/fecha_vencimiento condicionales en solicitudes_muestreo.py),
--    no para separar en dos tipos de especificación. Mismo patrón ya usado
--    para agregar 'semi_elaborado' (ver migrations_especificaciones_semi_elaborado.sql
--    y migrations_muestras_tipo_material.sql) -- se ubica la restricción CHECK
--    por nombre fijo (ya tiene nombre en ambas tablas) y se reemplaza.
-- 2. lims_erp_config: 'codsar_material_empaque' = '0005,0006' (lista separada
--    por comas -- a diferencia del resto de los tipos, que son un único
--    CODSAR, ver obtener_codsars_material_empaque() en erp_materiales.py).
-- 3. lims_novedades_empaque -- tabla ya creada manualmente antes de esta
--    migración; el CREATE TABLE queda acá solo para que el archivo refleje
--    el esquema real (mismo criterio ya usado en migrations_cajas.sql).
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS_DEV (SQL Server Management Studio) -- LIMSS_DEV
-- es una copia independiente de LIMSS para desarrollo, no tocar producción.
-- ============================================================

USE [LIMSS_DEV];
GO

-- 1a. lims_especificaciones.tipo_material -----------------------------------

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_lims_especificaciones_tipo_material')
BEGIN
    ALTER TABLE lims_especificaciones DROP CONSTRAINT CK_lims_especificaciones_tipo_material;
END
GO
ALTER TABLE lims_especificaciones
    ADD CONSTRAINT CK_lims_especificaciones_tipo_material
    CHECK (tipo_material IN ('materia_prima','granel','semi_elaborado','producto_terminado','material_empaque'));
GO
PRINT 'CK_lims_especificaciones_tipo_material actualizado (agregado material_empaque)';
GO

-- 1b. lims_muestras.tipo_material --------------------------------------------

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_lims_muestras_tipo_material')
BEGIN
    ALTER TABLE lims_muestras DROP CONSTRAINT CK_lims_muestras_tipo_material;
END
GO
ALTER TABLE lims_muestras
    ADD CONSTRAINT CK_lims_muestras_tipo_material
    CHECK (tipo_material IN ('materia_prima','granel','semi_elaborado','producto_terminado','material_empaque'));
GO
PRINT 'CK_lims_muestras_tipo_material actualizado (agregado material_empaque)';
GO

-- 2. CODSAR de Material de Empaque en lims_erp_config ------------------------

IF NOT EXISTS (SELECT 1 FROM lims_erp_config WHERE clave = 'codsar_material_empaque')
BEGIN
    INSERT INTO lims_erp_config (clave, valor, descripcion, editable) VALUES
    ('codsar_material_empaque', '0005,0006',
     'Códigos CODSAR de Material de Empaque en GIT59SAR (ERP GI_LX) -- lista separada por comas: 0005 codificado, 0006 sin codificar', 1);
    PRINT 'Valor codsar_material_empaque insertado en lims_erp_config';
END
GO

-- 3. Módulo de Novedades (Material de Empaque) -------------------------------

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_novedades_empaque')
BEGIN
    CREATE TABLE lims_novedades_empaque (
        id_novedad                 INT IDENTITY(1,1)  PRIMARY KEY,
        erp_CODART                 VARCHAR(20)         NOT NULL,
        titulo                     VARCHAR(200)        NOT NULL,
        descripcion                NVARCHAR(2000)      NOT NULL,
        estado                     VARCHAR(20)         NOT NULL DEFAULT 'pendiente',
        id_usuario_carga           INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_carga                DATETIME            NOT NULL DEFAULT GETDATE(),
        id_usuario_resolucion      INT                 NULL     REFERENCES lims_usuarios(id_usuario),
        fecha_resolucion           DATETIME            NULL,
        observaciones_resolucion   NVARCHAR(1000)       NULL
    );
    PRINT 'Tabla lims_novedades_empaque creada';
END
GO
