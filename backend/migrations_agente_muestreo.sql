-- ============================================================
-- MIGRACIÓN: Agente de detección automática de IR y generación de
-- Solicitud de Muestreo (GI_LX -> LIMSS)
-- ------------------------------------------------------------
-- 1. lims_erp_subarticulo_config: maestro que dice, por CODSAR (GIT59SAR,
--    ERP GI_LX), si ese subartículo requiere muestreo o no. Sin esta
--    tabla el agente no tiene forma de decidir nada -- se carga a mano
--    desde la pantalla de administración (ver app/api/routes/erp_config.py).
-- 2. lims_agente_control: idempotencia por comprobante IR (N01Id) -- UNIQUE
--    en id_comprobante_erp porque cada IR trae un solo ítem, así que la
--    evaluación es 1 a 1 con el comprobante. Incluye erp_desart (nombre del
--    material) y nro_ir (formato "NNN/AA" que ve el usuario) para que la
--    pantalla del agente los muestre sin resolver contra el ERP en cada
--    consulta.
-- 3. lims_agente_log: historial detallado de cada evaluación (una fila por
--    intento -- reprocesar un comprobante agrega una fila nueva, no pisa
--    la anterior).
-- 4. Tres parámetros nuevos en lims_erp_config: intervalo de polling, la
--    marca de agua (N01Id) del último comprobante ya evaluado, y la fecha
--    (FECCOR) a partir de la cual el agente evalúa comprobantes -- evita
--    que arranque procesando el historial de IR de antes de este mecanismo.
-- 5. lims_solicitudes_muestreo: el agente puede generar una solicitud sin
--    laboratorio asignado (cuando la especificación tiene más de un
--    laboratorio posible, o ninguno) y sin protocolo del proveedor (no
--    está disponible en este flujo) -- id_laboratorio pasa a NULLABLE y se
--    agrega "origen" para distinguir 'manual' de 'agente' en la UI.
-- 6. Usuario de sistema AGENTE_IA (rol 'qa', activo=0 -- solo para
--    atribución en id_usuario_qa de las solicitudes que genera el agente,
--    nunca puede loguearse porque el login exige activo=1).
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS_DEV (SQL Server Management Studio) -- LIMSS_DEV
-- es una copia independiente de LIMSS para desarrollo, no tocar producción.
-- ============================================================

USE [LIMSS_DEV];
GO

-- 1. Maestro de subartículos ------------------------------------------------

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_erp_subarticulo_config')
BEGIN
    CREATE TABLE lims_erp_subarticulo_config (
        id                  INT IDENTITY(1,1)  PRIMARY KEY,
        erp_codsar          VARCHAR(20)         NOT NULL UNIQUE,
        descripcion         VARCHAR(200)        NULL,
        requiere_muestreo   BIT                 NOT NULL DEFAULT 0,
        activo              BIT                 NOT NULL DEFAULT 1,
        id_usuario_carga    INT                 NULL REFERENCES lims_usuarios(id_usuario),
        fecha_carga         DATETIME            NOT NULL DEFAULT GETDATE(),
        observaciones       VARCHAR(500)        NULL
    );
    PRINT 'Tabla lims_erp_subarticulo_config creada';
END
GO

-- 2. Idempotencia por comprobante --------------------------------------------

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_agente_control')
BEGIN
    CREATE TABLE lims_agente_control (
        id                      INT IDENTITY(1,1)  PRIMARY KEY,
        id_comprobante_erp      INT                 NOT NULL UNIQUE, -- GIN01CPB.N01Id
        -- erp_idm21/erp_codart quedan NULL cuando la evaluación falla antes de
        -- poder leer la línea del comprobante en el ERP (ej. ERP caído) -- ver
        -- _registrar_error en app/services/agente_muestreo.py.
        erp_idm21               INT                 NULL,
        erp_codart              VARCHAR(20)         NULL,
        erp_codsar              VARCHAR(20)         NULL,
        erp_desart              VARCHAR(100)        NULL, -- nombre del material (GIM21ART.DESART), para mostrar en la pantalla del agente sin resolver contra el ERP
        nro_ir                  VARCHAR(10)         NULL, -- formato "NNN/AA" (formatear_nro_ir en erp_ir.py) -- identificador principal en pantalla, N01Id no significa nada para un humano
        fecha_evaluacion        DATETIME            NOT NULL DEFAULT GETDATE(),
        resultado               VARCHAR(30)         NOT NULL, -- solicitud_generada|no_requiere_muestreo|subarticulo_no_configurado|error
        id_solicitud_generada   INT                 NULL REFERENCES lims_solicitudes_muestreo(id_solicitud),
        reintentos              INT                 NOT NULL DEFAULT 0
    );
    PRINT 'Tabla lims_agente_control creada';
END
GO

-- 3. Historial detallado ------------------------------------------------------

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_agente_log')
BEGIN
    CREATE TABLE lims_agente_log (
        id                  INT IDENTITY(1,1)  PRIMARY KEY,
        id_control          INT                 NOT NULL REFERENCES lims_agente_control(id),
        fecha_hora          DATETIME            NOT NULL DEFAULT GETDATE(),
        datos_consultados   VARCHAR(MAX)         NULL, -- snapshot JSON de lo que se leyó del ERP/LIMSS
        decision            VARCHAR(30)          NULL,
        justificacion       VARCHAR(1000)        NULL, -- redactada por Claude (ver app/services/agente_muestreo.py)
        error_detalle       VARCHAR(2000)        NULL
    );
    PRINT 'Tabla lims_agente_log creada';
END
GO

-- 4. Parámetros de polling en lims_erp_config --------------------------------

IF NOT EXISTS (SELECT 1 FROM lims_erp_config WHERE clave = 'agente_muestreo_polling_minutos')
BEGIN
    INSERT INTO lims_erp_config (clave, valor, descripcion, editable) VALUES
    ('agente_muestreo_polling_minutos', '5', 'Cada cuántos minutos el agente revisa el ERP en busca de IR nuevos', 1);
    PRINT 'Parámetro agente_muestreo_polling_minutos insertado';
END
GO

IF NOT EXISTS (SELECT 1 FROM lims_erp_config WHERE clave = 'agente_muestreo_ultimo_n01id')
BEGIN
    -- No editable desde la pantalla de Configuración ERP: es una marca de
    -- agua que mantiene el propio agente (ver ciclo_polling) -- editarla a
    -- mano rompe la idempotencia (reprocesaría o saltearía comprobantes).
    INSERT INTO lims_erp_config (clave, valor, descripcion, editable) VALUES
    ('agente_muestreo_ultimo_n01id', '0', 'N01Id del último comprobante IR ya evaluado por el agente (marca de agua, no editar a mano)', 0);
    PRINT 'Parámetro agente_muestreo_ultimo_n01id insertado';
END
GO

IF NOT EXISTS (SELECT 1 FROM lims_erp_config WHERE clave = 'agente_muestreo_fecha_inicio')
BEGIN
    -- Comprobantes con FECCOR anterior a esta fecha quedan completamente
    -- ignorados por el agente (ni se evalúan ni generan fila en
    -- lims_agente_control) -- evita que arranque procesando todo el
    -- historial de IR de antes de que este mecanismo existiera. Editable:
    -- a diferencia de la marca de agua, este sí lo puede cambiar un admin
    -- a mano (ver ciclo_polling, se relee en cada ciclo).
    INSERT INTO lims_erp_config (clave, valor, descripcion, editable) VALUES
    ('agente_muestreo_fecha_inicio', '2026-08-01', 'Fecha (FECCOR) a partir de la cual el agente evalúa comprobantes IR -- los anteriores se ignoran por completo', 1);
    PRINT 'Parámetro agente_muestreo_fecha_inicio insertado';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_agente_control') AND name = 'erp_desart'
)
BEGIN
    ALTER TABLE lims_agente_control ADD erp_desart VARCHAR(100) NULL;
    PRINT 'Columna lims_agente_control.erp_desart agregada';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_agente_control') AND name = 'nro_ir'
)
BEGIN
    ALTER TABLE lims_agente_control ADD nro_ir VARCHAR(10) NULL;
    PRINT 'Columna lims_agente_control.nro_ir agregada';
END
GO

-- 5. lims_solicitudes_muestreo: soporte para solicitudes generadas por el agente --

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('lims_solicitudes_muestreo') AND name = 'id_laboratorio' AND is_nullable = 0
)
BEGIN
    ALTER TABLE lims_solicitudes_muestreo ALTER COLUMN id_laboratorio INT NULL;
    PRINT 'Columna lims_solicitudes_muestreo.id_laboratorio ahora es NULLABLE';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('lims_solicitudes_muestreo') AND name = 'origen'
)
BEGIN
    ALTER TABLE lims_solicitudes_muestreo
        ADD origen VARCHAR(10) NOT NULL DEFAULT 'manual'
            CONSTRAINT CK_lims_solicitudes_muestreo_origen CHECK (origen IN ('manual', 'agente'));
    PRINT 'Columna lims_solicitudes_muestreo.origen agregada';
END
GO

-- 6. Usuario de sistema para atribución de solicitudes generadas por el agente --

IF NOT EXISTS (SELECT 1 FROM lims_usuarios WHERE codigo = 'AGENTE_IA')
BEGIN
    -- El hash de PIN no importa a efectos de seguridad: activo=0 hace que
    -- este usuario nunca pueda loguearse (POST /api/auth/login exige
    -- activo=1), el valor de acá es solo para satisfacer el NOT NULL de la
    -- columna con un hash bcrypt válido (generado con hash_pin() sobre un
    -- valor aleatorio, no es un PIN real ni se conoce en ningún lado).
    INSERT INTO lims_usuarios (codigo, nombre, apellido, pin_hash, rol, activo, fecha_creacion, activo_ebr, debe_cambiar_pin)
    VALUES ('AGENTE_IA', 'Agente IA', 'Muestreo Automático',
            '$2b$12$XRLOHlPaXGzRnUFL5IUr3O8pgElyjI.pPRe5eUfmeh.QrtqXwwccC',
            'qa', 0, GETDATE(), 0, 0);
    PRINT 'Usuario de sistema AGENTE_IA creado (inactivo, solo para atribución)';
END
GO
