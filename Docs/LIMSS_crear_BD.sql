-- ============================================================
-- LIMSS — Creación de Base de Datos y Tablas
-- Sistema LIMS Simplificado para Gestión de Análisis Externos
-- Laboratorio Lamar SRL
-- ============================================================
USE master;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'LIMSS')
BEGIN
    CREATE DATABASE [LIMSS] COLLATE Modern_Spanish_CI_AS;
    PRINT 'Base de datos LIMSS creada OK';
END
GO

USE [LIMSS];
GO

-- ============================================================
-- SEGURIDAD Y USUARIOS
-- ============================================================

-- Usuarios del sistema (espejo de ebr_usuarios, sin FK entre BDs)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_usuarios')
BEGIN
    CREATE TABLE lims_usuarios (
        id_usuario      INT IDENTITY(1,1)   PRIMARY KEY,
        codigo          VARCHAR(20)         NOT NULL UNIQUE,
        nombre          VARCHAR(100)        NOT NULL,
        apellido        VARCHAR(100)        NOT NULL,
        pin_hash        VARCHAR(256)        NOT NULL,
        -- Roles LIMSS (distintos a los del eBR)
        rol             VARCHAR(20)         NOT NULL
                        CHECK (rol IN ('muestreador','analista_qc','qa','admin')),
        activo          BIT                 NOT NULL DEFAULT 1,
        fecha_creacion  DATETIME            NOT NULL DEFAULT GETDATE(),
        ultimo_login    DATETIME            NULL
    );
    PRINT 'Tabla lims_usuarios creada OK';
END
GO

-- Sesiones JWT
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_sesiones')
BEGIN
    CREATE TABLE lims_sesiones (
        id_sesion       INT IDENTITY(1,1)   PRIMARY KEY,
        id_usuario      INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        token           VARCHAR(512)        NOT NULL UNIQUE,
        ip_origen       VARCHAR(45)         NULL,
        dispositivo     VARCHAR(200)        NULL,
        fecha_inicio    DATETIME            NOT NULL DEFAULT GETDATE(),
        fecha_expira    DATETIME            NOT NULL,
        fecha_cierre    DATETIME            NULL,
        motivo_cierre   VARCHAR(20)         NULL
    );
    PRINT 'Tabla lims_sesiones creada OK';
END
GO

-- Audit trail inmutable (misma estructura que eBR)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_audit_trail')
BEGIN
    CREATE TABLE lims_audit_trail (
        id_audit        BIGINT IDENTITY(1,1)    PRIMARY KEY,
        id_usuario      INT                     NULL,
        entidad         VARCHAR(50)             NOT NULL,
        id_entidad      INT                     NULL,
        accion          VARCHAR(50)             NOT NULL,
        valor_anterior  NVARCHAR(MAX)           NULL,
        valor_nuevo     NVARCHAR(MAX)           NULL,
        motivo          VARCHAR(300)            NULL,
        fecha_hora      DATETIME                NOT NULL DEFAULT GETDATE(),
        ip_origen       VARCHAR(45)             NULL
    );
    PRINT 'Tabla lims_audit_trail creada OK';
END
GO

-- ============================================================
-- DATOS MAESTROS
-- ============================================================

-- Laboratorios externos
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_laboratorios')
BEGIN
    CREATE TABLE lims_laboratorios (
        id_laboratorio  INT IDENTITY(1,1)   PRIMARY KEY,
        nombre          VARCHAR(150)        NOT NULL,
        direccion       VARCHAR(200)        NULL,
        contacto        VARCHAR(100)        NULL,
        email           VARCHAR(100)        NULL,
        telefono        VARCHAR(30)         NULL,
        activo          BIT                 NOT NULL DEFAULT 1
    );
    PRINT 'Tabla lims_laboratorios creada OK';
END
GO

-- Especificaciones por producto/material
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_especificaciones')
BEGIN
    CREATE TABLE lims_especificaciones (
        id_especificacion   INT IDENTITY(1,1)   PRIMARY KEY,
        -- Referencia al artículo del ERP
        erp_IdM21           INT                 NOT NULL,
        erp_CODART          VARCHAR(20)         NOT NULL,
        erp_DESART          VARCHAR(100)        NOT NULL,
        tipo_material       VARCHAR(20)         NOT NULL
                            CONSTRAINT CK_lims_especificaciones_tipo_material
                            CHECK (tipo_material IN ('materia_prima','granel','semi_elaborado','producto_terminado')),
        version             VARCHAR(10)         NOT NULL DEFAULT '1.0',
        vigente             BIT                 NOT NULL DEFAULT 1,
        id_usuario_carga    INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_carga         DATETIME            NOT NULL DEFAULT GETDATE()
    );
    CREATE INDEX ix_espec_material ON lims_especificaciones(erp_IdM21, vigente);
    PRINT 'Tabla lims_especificaciones creada OK';
END
GO

-- Ensayos dentro de cada especificación (REQ-MAS-002)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_ensayos')
BEGIN
    CREATE TABLE lims_ensayos (
        id_ensayo           INT IDENTITY(1,1)   PRIMARY KEY,
        id_especificacion   INT                 NOT NULL
                            REFERENCES lims_especificaciones(id_especificacion),
        orden               INT                 NOT NULL,
        nombre_ensayo       VARCHAR(100)        NOT NULL,
        metodologia         VARCHAR(100)        NULL,
        tipo_dato           VARCHAR(15)         NOT NULL
                            CHECK (tipo_dato IN ('numerico','cualitativo')),
        -- Para numéricos
        limite_inferior     DECIMAL(18,4)       NULL,
        limite_superior     DECIMAL(18,4)       NULL,
        unidad_medida       VARCHAR(20)         NULL,
        -- Para cualitativos
        valor_requerido     VARCHAR(200)        NULL,
        obligatorio         BIT                 NOT NULL DEFAULT 1,
        observaciones       NVARCHAR(500)       NULL
    );
    CREATE INDEX ix_ensayos_espec ON lims_ensayos(id_especificacion, orden);
    PRINT 'Tabla lims_ensayos creada OK';
END
GO

-- Testigos y estándares (REQ-MAS-003)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_testigos')
BEGIN
    CREATE TABLE lims_testigos (
        id_testigo          INT IDENTITY(1,1)   PRIMARY KEY,
        codigo              VARCHAR(20)         NOT NULL UNIQUE,
        nombre              VARCHAR(150)        NOT NULL,
        nro_lote            VARCHAR(50)         NOT NULL,
        fecha_vencimiento   DATE                NOT NULL,
        stock_actual        DECIMAL(10,4)       NOT NULL DEFAULT 0,
        stock_minimo        DECIMAL(10,4)       NOT NULL DEFAULT 0,
        unidad_medida       VARCHAR(20)         NULL,
        -- PDF del certificado analítico
        pdf_certificado     VARCHAR(300)        NULL,
        activo              BIT                 NOT NULL DEFAULT 1,
        id_usuario_carga    INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_carga         DATETIME            NOT NULL DEFAULT GETDATE(),
        observaciones       NVARCHAR(500)       NULL
    );
    PRINT 'Tabla lims_testigos creada OK';
END
GO

-- ============================================================
-- MÓDULO I: MUESTRAS Y ENVÍOS
-- ============================================================

-- Registro de muestras (REQ-ENV-001)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_muestras')
BEGIN
    CREATE TABLE lims_muestras (
        id_muestra          INT IDENTITY(1,1)   PRIMARY KEY,
        -- ID secuencial visible (SAMP-YYYY-NNNN)
        codigo_muestra      VARCHAR(20)         NOT NULL UNIQUE,
        -- Identificador de origen: IR del ERP para Materia Prima,
        -- número de lote interno (ebr_lotes) para Granel/Semi-Elaborado/PT.
        -- erp_nro_ir queda deprecada (nullable, no se completa en altas nuevas).
        tipo_referencia     VARCHAR(10)         NOT NULL
                            CONSTRAINT CK_lims_muestras_tipo_referencia
                            CHECK (tipo_referencia IN ('ir','lote')),
        nro_referencia      VARCHAR(50)         NOT NULL,
        erp_nro_ir          VARCHAR(20)         NULL,
        -- Datos del ERP (REQ-ENV-002)
        erp_IdM21           INT                 NOT NULL,
        erp_CODART          VARCHAR(20)         NOT NULL,
        erp_DESART          VARCHAR(100)        NOT NULL,
        erp_cantidad_lote   DECIMAL(18,4)       NULL,
        erp_proveedor       VARCHAR(100)        NULL,
        -- Especificación aplicable
        id_especificacion   INT                 NULL
                            REFERENCES lims_especificaciones(id_especificacion),
        -- Estado del flujo
        estado              VARCHAR(30)         NOT NULL DEFAULT 'pendiente_envio'
                            CHECK (estado IN (
                                'pendiente_envio',
                                'en_transito',
                                'en_carga_resultados',
                                'pendiente_dictamen',
                                'aprobado',
                                'rechazado',
                                'cuarentena'
                            )),
        -- Muestreo
        id_usuario_muestreo INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_muestreo      DATETIME            NOT NULL DEFAULT GETDATE(),
        observaciones       VARCHAR(500)        NULL
    );
    CREATE INDEX ix_muestras_ir   ON lims_muestras(nro_referencia);
    CREATE INDEX ix_muestras_est  ON lims_muestras(estado);
    PRINT 'Tabla lims_muestras creada OK';
END
GO

-- Envíos al laboratorio externo (REQ-ENV-005)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_envios')
BEGIN
    CREATE TABLE lims_envios (
        id_envio            INT IDENTITY(1,1)   PRIMARY KEY,
        id_muestra          INT                 NOT NULL REFERENCES lims_muestras(id_muestra),
        id_laboratorio      INT                 NOT NULL REFERENCES lims_laboratorios(id_laboratorio),
        id_testigo          INT                 NULL REFERENCES lims_testigos(id_testigo),
        cantidad_testigo    DECIMAL(10,4)       NULL,
        fecha_despacho      DATETIME            NOT NULL DEFAULT GETDATE(),
        temperatura_transporte VARCHAR(50)      NULL,
        nro_remito          VARCHAR(50)         NULL,
        transportista       VARCHAR(100)        NULL,
        analisis_solicitados VARCHAR(500)       NULL,
        protocolo_utilizar  VARCHAR(100)        NULL,
        id_usuario_envio    INT                 NOT NULL REFERENCES lims_usuarios(id_usuario)
    );
    PRINT 'Tabla lims_envios creada OK';
END
GO

-- Movimientos de stock de testigos (inmutable)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_testigo_movimientos')
BEGIN
    CREATE TABLE lims_testigo_movimientos (
        id_movimiento   BIGINT IDENTITY(1,1)    PRIMARY KEY,
        id_testigo      INT                     NOT NULL REFERENCES lims_testigos(id_testigo),
        id_envio        INT                     NULL REFERENCES lims_envios(id_envio),
        tipo            VARCHAR(15)             NOT NULL
                        CHECK (tipo IN ('ingreso','egreso','ajuste')),
        cantidad        DECIMAL(10,4)           NOT NULL,
        stock_resultante DECIMAL(10,4)          NOT NULL,
        id_usuario      INT                     NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_hora      DATETIME                NOT NULL DEFAULT GETDATE(),
        observaciones   VARCHAR(200)            NULL
    );
    PRINT 'Tabla lims_testigo_movimientos creada OK';
END
GO

-- ============================================================
-- MÓDULO II: RESULTADOS ANALÍTICOS
-- ============================================================

-- Resultados por ensayo (REQ-RES-002)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_resultados')
BEGIN
    CREATE TABLE lims_resultados (
        id_resultado        INT IDENTITY(1,1)   PRIMARY KEY,
        id_muestra          INT                 NOT NULL REFERENCES lims_muestras(id_muestra),
        id_ensayo           INT                 NOT NULL REFERENCES lims_ensayos(id_ensayo),
        -- Valor ingresado
        valor_numerico      DECIMAL(18,4)       NULL,
        valor_cualitativo   VARCHAR(200)        NULL,
        -- Validación automática OOS (REQ-RES-003)
        dentro_especificacion BIT               NULL,  -- NULL = no validado aún
        -- Trazabilidad
        id_usuario_carga    INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_carga         DATETIME            NOT NULL DEFAULT GETDATE(),
        CONSTRAINT uq_resultado_muestra_ensayo UNIQUE (id_muestra, id_ensayo)
    );
    PRINT 'Tabla lims_resultados creada OK';
END
GO

-- Protocolo del laboratorio externo (REQ-RES-004 y REQ-RES-005)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_protocolos')
BEGIN
    CREATE TABLE lims_protocolos (
        id_protocolo        INT IDENTITY(1,1)   PRIMARY KEY,
        id_muestra          INT                 NOT NULL REFERENCES lims_muestras(id_muestra),
        nro_protocolo_ext   VARCHAR(50)         NOT NULL,
        fecha_emision       DATE                NOT NULL,
        -- PDF almacenado en servidor (REQ-TEC-002)
        pdf_path            VARCHAR(300)        NOT NULL,
        pdf_nombre_original VARCHAR(200)        NOT NULL,
        id_usuario_carga    INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_carga         DATETIME            NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Tabla lims_protocolos creada OK';
END
GO

-- ============================================================
-- MÓDULO III: DICTAMEN Y LIBERACIÓN
-- ============================================================

-- Dictamen final de QA (REQ-DEC-003)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_dictamenes')
BEGIN
    CREATE TABLE lims_dictamenes (
        id_dictamen         INT IDENTITY(1,1)   PRIMARY KEY,
        id_muestra          INT                 NOT NULL REFERENCES lims_muestras(id_muestra),
        estado_dictamen     VARCHAR(20)         NOT NULL
                            CHECK (estado_dictamen IN ('aprobado','rechazado','cuarentena')),
        -- Justificación obligatoria si hay OOS (REQ-DEC-002)
        justificacion_oos   VARCHAR(1000)       NULL,
        observaciones       VARCHAR(500)        NULL,
        -- Firma electrónica QA (REQ-DEC-004)
        id_usuario_qa       INT                 NOT NULL REFERENCES lims_usuarios(id_usuario),
        fecha_dictamen      DATETIME            NOT NULL DEFAULT GETDATE(),
        CONSTRAINT uq_dictamen_muestra UNIQUE (id_muestra)
    );
    PRINT 'Tabla lims_dictamenes creada OK';
END
GO

-- ============================================================
-- PUENTE HACIA EL eBR (REQ-DEC-005)
-- Esta tabla es consultada por el eBR en SOLO LECTURA
-- para validar si un IR puede usarse en pesaje
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'lims_aprobaciones_lote')
BEGIN
    CREATE TABLE lims_aprobaciones_lote (
        id_aprobacion   INT IDENTITY(1,1)   PRIMARY KEY,
        -- nro_referencia = IR (Materia Prima) o número de lote interno (resto).
        -- erp_nro_ir queda deprecada (nullable).
        nro_referencia  VARCHAR(50)         NOT NULL,
        erp_nro_ir      VARCHAR(20)         NULL,
        erp_CODART      VARCHAR(20)         NOT NULL,
        estado          VARCHAR(20)         NOT NULL
                        CHECK (estado IN ('aprobado','rechazado','cuarentena','pendiente')),
        id_dictamen     INT                 NOT NULL REFERENCES lims_dictamenes(id_dictamen),
        fecha_hora      DATETIME            NOT NULL DEFAULT GETDATE(),
        -- Inmutable: no se borra, se agrega una fila nueva si cambia
        CONSTRAINT UQ_lims_aprobaciones_lote_referencia UNIQUE (nro_referencia, erp_CODART)
    );
    CREATE INDEX ix_aprobaciones_ir ON lims_aprobaciones_lote(nro_referencia, estado);
    PRINT 'Tabla lims_aprobaciones_lote creada OK';
END
GO

-- ============================================================
-- ÍNDICES ADICIONALES
-- ============================================================
CREATE INDEX ix_sesiones_token    ON lims_sesiones(token);
CREATE INDEX ix_resultados_muestra ON lims_resultados(id_muestra);
CREATE INDEX ix_audit_entidad     ON lims_audit_trail(entidad, id_entidad, fecha_hora);
GO

PRINT '';
PRINT '============================================';
PRINT 'BD LIMSS creada correctamente.';
PRINT 'Tablas creadas: 16';
PRINT 'Próximo paso: crear usuarios SQL y cargar';
PRINT 'datos maestros (laboratorios, testigos).';
PRINT '============================================';
GO
