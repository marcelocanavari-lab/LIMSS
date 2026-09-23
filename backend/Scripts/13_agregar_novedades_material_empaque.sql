/* =====================================================================
   Novedades de Material de Empaque (LIMSS)
   Generado: 2026-08-13

   Tabla standalone, sin cruce automatico con solicitudes/muestras
   (decision confirmada). Un solo estado de resolucion ("resuelta") --
   "Cumplida"/"Ejecutada" son variantes de texto segun contexto, no
   estados distintos.

   No hace falta tocar lims_especificacion_ensayos ni
   lims_solicitudes_muestreo con esta migracion: la primera ya soporta
   varios ensayos por especificacion (se usa tal cual), y los campos
   lote_proveedor / fecha_vencimiento de la segunda ya son nullable --
   el cambio de que sean opcionales para material sin codificar es
   logica de validacion, no de esquema.

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF OBJECT_ID('dbo.lims_novedades_empaque', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_novedades_empaque (
        id_novedad              INT IDENTITY(1,1) PRIMARY KEY,
        erp_CODART               VARCHAR(20) NOT NULL,
        titulo                   VARCHAR(200) NOT NULL,
        descripcion               NVARCHAR(2000) NOT NULL,
        estado                    VARCHAR(20) NOT NULL DEFAULT 'pendiente',  -- 'pendiente' | 'resuelta'
        id_usuario_carga         INT NOT NULL,
        fecha_carga               DATETIME NOT NULL DEFAULT GETDATE(),
        id_usuario_resolucion    INT NULL,
        fecha_resolucion          DATETIME NULL,
        observaciones_resolucion NVARCHAR(1000) NULL,
        CONSTRAINT FK_novedades_empaque_usuario_carga
            FOREIGN KEY (id_usuario_carga) REFERENCES dbo.lims_usuarios(id_usuario),
        CONSTRAINT FK_novedades_empaque_usuario_resolucion
            FOREIGN KEY (id_usuario_resolucion) REFERENCES dbo.lims_usuarios(id_usuario)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_novedades_empaque_codart'
      AND object_id = OBJECT_ID('dbo.lims_novedades_empaque')
)
    CREATE INDEX IX_novedades_empaque_codart ON dbo.lims_novedades_empaque (erp_CODART);
GO

-- =====================================================================
-- Comparación de etiquetas con IA (asistencia visual, no reemplaza el
-- chequeo humano)
-- =====================================================================

-- Imagen de referencia (el "original aprobado") por articulo de empaque.
-- No esta atada a una especificacion/version puntual -- el arte aprobado
-- se actualiza independientemente de cuando cambia la especificacion.
IF OBJECT_ID('dbo.lims_empaque_referencia', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.lims_empaque_referencia (
        id_referencia       INT IDENTITY(1,1) PRIMARY KEY,
        erp_CODART           VARCHAR(20) NOT NULL,
        imagen_path           VARCHAR(300) NOT NULL,
        nombre_original       VARCHAR(200) NOT NULL,
        activo                BIT NOT NULL DEFAULT 1,
        id_usuario_carga     INT NOT NULL,
        fecha_carga           DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT FK_empaque_referencia_usuario
            FOREIGN KEY (id_usuario_carga) REFERENCES dbo.lims_usuarios(id_usuario)
    );
    -- Solo una referencia ACTIVA por articulo a la vez (igual patron de
    -- soft-delete que el resto del proyecto: al cargar una nueva, la
    -- anterior se marca activo=0 en vez de borrarse, para conservar
    -- historial de versiones de arte aprobado).
    CREATE UNIQUE INDEX UQ_empaque_referencia_activa
        ON dbo.lims_empaque_referencia (erp_CODART)
        WHERE activo = 1;
END
GO

-- Columnas nuevas en lims_resultados: la foto de la etiqueta recibida
-- en ESTA inspeccion puntual, y el texto de diferencias que devuelve
-- la comparacion con IA (asistencia, no el resultado en si -- el
-- Cumple/No cumple lo sigue completando la persona).
IF COL_LENGTH('dbo.lims_resultados', 'imagen_comparacion_path') IS NULL
    ALTER TABLE dbo.lims_resultados ADD imagen_comparacion_path VARCHAR(300) NULL;

IF COL_LENGTH('dbo.lims_resultados', 'observacion_ia') IS NULL
    ALTER TABLE dbo.lims_resultados ADD observacion_ia NVARCHAR(2000) NULL;
GO

-- Verificacion
SELECT * FROM dbo.lims_novedades_empaque;
SELECT * FROM dbo.lims_empaque_referencia;
SELECT id_resultado, imagen_comparacion_path, observacion_ia FROM dbo.lims_resultados WHERE imagen_comparacion_path IS NOT NULL;
