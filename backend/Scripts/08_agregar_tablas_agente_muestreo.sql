/* =====================================================================
   Soporte para el Agente de generacion automatica de solicitudes
   (ERP -> LIMSS) -- v2, corrige granularidad a nivel LINEA de comprobante
   Generado: 2026-08-12

   Correccion respecto de la v1: un comprobante IR (GIN01CPB.N01Id) puede
   tener varias lineas (GIN02ITS), cada una con su propio material
   (GIM21ART) y subarticulo (GIT59SAR via GIM21ART.IdT59). La evaluacion
   del agente es POR LINEA, no por comprobante -- un mismo IR puede
   generar una solicitud para un material y ninguna para otro.

   Todas las tablas en la base de LIMSS (decision ya confirmada: no
   crear una base separada para el agente).
   ===================================================================== */

USE LIMSS;
GO

-- 1) Configuracion de subarticulos (sin cambios respecto de v1)
IF OBJECT_ID('dbo.lims_erp_subarticulo_config', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_erp_subarticulo_config (
        id                 INT IDENTITY(1,1) PRIMARY KEY,
        erp_codsar         VARCHAR(20) NOT NULL,   -- GIT59SAR.CODSAR
        descripcion        VARCHAR(200) NULL,       -- GIT59SAR.DESSAR, de referencia
        requiere_muestreo  BIT NOT NULL,
        activo             BIT NOT NULL DEFAULT 1,
        id_usuario_carga   INT NOT NULL,
        fecha_carga        DATETIME NOT NULL DEFAULT GETDATE(),
        observaciones      VARCHAR(300) NULL,
        CONSTRAINT UQ_erp_subarticulo_config UNIQUE (erp_codsar),
        CONSTRAINT FK_erp_subarticulo_config_usuario
            FOREIGN KEY (id_usuario_carga) REFERENCES dbo.lims_usuarios(id_usuario)
    );
END
GO

-- 2) Control de idempotencia -- un comprobante IR = un item = una evaluacion
IF OBJECT_ID('dbo.lims_agente_control', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_agente_control (
        id                     INT IDENTITY(1,1) PRIMARY KEY,
        id_comprobante_erp     INT NOT NULL,        -- GIN01CPB.N01Id
        erp_idm21              INT NULL,            -- GIM21ART.M21Id, de referencia
        erp_codart             VARCHAR(20) NULL,     -- de referencia/lectura rapida
        erp_codsar             VARCHAR(20) NULL,     -- subarticulo del item
        fecha_evaluacion       DATETIME NOT NULL DEFAULT GETDATE(),
        resultado              VARCHAR(30) NOT NULL,
            -- 'solicitud_generada', 'no_requiere_muestreo',
            -- 'subarticulo_no_configurado', 'error'
        id_solicitud_generada  INT NULL,
        reintentos             INT NOT NULL DEFAULT 0,
        CONSTRAINT UQ_agente_control_comprobante UNIQUE (id_comprobante_erp),
        CONSTRAINT FK_agente_control_solicitud
            FOREIGN KEY (id_solicitud_generada) REFERENCES dbo.lims_solicitudes_muestreo(id_solicitud)
    );
END
GO

-- 3) Log detallado (sin cambios de fondo respecto de v1)
IF OBJECT_ID('dbo.lims_agente_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_agente_log (
        id                 BIGINT IDENTITY(1,1) PRIMARY KEY,
        id_control         INT NOT NULL,
        fecha_hora         DATETIME NOT NULL DEFAULT GETDATE(),
        datos_consultados  NVARCHAR(MAX) NULL,
        decision           VARCHAR(30) NOT NULL,
        justificacion      NVARCHAR(MAX) NULL,
        error_detalle      NVARCHAR(MAX) NULL,
        CONSTRAINT FK_agente_log_control
            FOREIGN KEY (id_control) REFERENCES dbo.lims_agente_control(id)
    );
END
GO

-- Parametros configurables del agente (reutiliza lims_erp_config)
IF NOT EXISTS (SELECT 1 FROM dbo.lims_erp_config WHERE clave = 'agente_muestreo_polling_minutos')
    INSERT INTO dbo.lims_erp_config (clave, valor, descripcion, editable, fecha_modificacion)
    VALUES ('agente_muestreo_polling_minutos', '5',
            'Frecuencia (en minutos) con la que el agente revisa el ERP en busca de IRs nuevos',
            1, GETDATE());

IF NOT EXISTS (SELECT 1 FROM dbo.lims_erp_config WHERE clave = 'agente_muestreo_ultimo_n01id')
    INSERT INTO dbo.lims_erp_config (clave, valor, descripcion, editable, fecha_modificacion)
    VALUES ('agente_muestreo_ultimo_n01id', '0',
            'Ultimo N01Id (GIN01CPB) de comprobante IR procesado por el agente -- marca de agua para el polling',
            0, GETDATE());
GO

-- Verificacion
SELECT * FROM dbo.lims_erp_subarticulo_config;
SELECT * FROM dbo.lims_agente_control;
SELECT * FROM dbo.lims_agente_log;
SELECT * FROM dbo.lims_erp_config WHERE clave LIKE 'agente_muestreo%';
