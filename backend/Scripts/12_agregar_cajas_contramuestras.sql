/* =====================================================================
   Archivo de contramuestras: Cajas (LIMSS)
   Generado: 2026-08-13

   Modelo:
   - lims_cajas: una caja fisica de archivo. Estado activa/cerrada,
     se puede reabrir (no hay borrado logico de "cerrada definitiva").
   - lims_caja_muestras: que muestras (contramuestras) contiene cada
     caja. Usa fecha_retiro en vez de DELETE para conservar el
     historial completo de movimientos (una muestra puede haber estado
     en mas de una caja a lo largo del tiempo, si se reorganiza el
     archivo fisico).
   - Un indice filtrado garantiza que una muestra este en como maximo
     UNA caja "activa" (fecha_retiro NULL) a la vez -- no puede estar
     fisicamente en dos cajas al mismo tiempo.

   No se agrega ninguna columna para "marcar" que una muestra es
   contramuestra -- esa distincion ya existe en
   lims_especificacion_muestras.tipo_muestra. El alta valida contra eso
   como chequeo informativo, no estructural.

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF OBJECT_ID('dbo.lims_cajas', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_cajas (
        id_caja               INT IDENTITY(1,1) PRIMARY KEY,
        codigo                VARCHAR(20) NOT NULL,
        ubicacion             VARCHAR(100) NULL,
        estado                VARCHAR(20) NOT NULL DEFAULT 'activa',  -- 'activa' | 'cerrada'
        fecha_apertura        DATETIME NOT NULL DEFAULT GETDATE(),
        fecha_cierre          DATETIME NULL,
        id_usuario_apertura   INT NOT NULL,
        id_usuario_cierre     INT NULL,
        observaciones         VARCHAR(500) NULL,
        CONSTRAINT UQ_cajas_codigo UNIQUE (codigo),
        CONSTRAINT FK_cajas_usuario_apertura FOREIGN KEY (id_usuario_apertura) REFERENCES dbo.lims_usuarios(id_usuario),
        CONSTRAINT FK_cajas_usuario_cierre FOREIGN KEY (id_usuario_cierre) REFERENCES dbo.lims_usuarios(id_usuario)
    );
END
GO

IF OBJECT_ID('dbo.lims_caja_muestras', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_caja_muestras (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        id_caja             INT NOT NULL,
        id_muestra          INT NOT NULL,
        fecha_ingreso       DATETIME NOT NULL DEFAULT GETDATE(),
        id_usuario_ingreso  INT NOT NULL,
        fecha_retiro        DATETIME NULL,
        id_usuario_retiro   INT NULL,
        CONSTRAINT FK_caja_muestras_caja FOREIGN KEY (id_caja) REFERENCES dbo.lims_cajas(id_caja),
        CONSTRAINT FK_caja_muestras_muestra FOREIGN KEY (id_muestra) REFERENCES dbo.lims_muestras(id_muestra),
        CONSTRAINT FK_caja_muestras_usuario_ingreso FOREIGN KEY (id_usuario_ingreso) REFERENCES dbo.lims_usuarios(id_usuario),
        CONSTRAINT FK_caja_muestras_usuario_retiro FOREIGN KEY (id_usuario_retiro) REFERENCES dbo.lims_usuarios(id_usuario)
    );
END
GO

-- Una muestra solo puede estar "actualmente" (fecha_retiro NULL) en UNA caja a la vez
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_caja_muestras_activa'
      AND object_id = OBJECT_ID('dbo.lims_caja_muestras')
)
    CREATE UNIQUE INDEX UQ_caja_muestras_activa
        ON dbo.lims_caja_muestras (id_muestra)
        WHERE fecha_retiro IS NULL;
GO

-- Indices de apoyo para los reportes
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_caja_muestras_caja'
      AND object_id = OBJECT_ID('dbo.lims_caja_muestras')
)
    CREATE INDEX IX_caja_muestras_caja ON dbo.lims_caja_muestras (id_caja);
GO

-- Verificacion
SELECT * FROM dbo.lims_cajas;
SELECT * FROM dbo.lims_caja_muestras;
