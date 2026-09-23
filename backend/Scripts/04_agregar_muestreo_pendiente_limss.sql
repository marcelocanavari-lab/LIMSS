/* =====================================================================
   Generar envio desde la solicitud, antes de confirmar el muestreo fisico
   Generado: 2026-08-10

   Hoy lims_muestras solo se crea cuando el muestreador confirma el
   muestreo (Ejecutar Muestreo), con todos los datos fisicos completos
   (aspecto_externo, cierre, etc. -- que ademas viven en
   lims_solicitudes_muestreo, no en lims_muestras).

   Se necesita poder generar un envio teniendo solo la solicitud activa,
   sin esperar la confirmacion fisica del muestreador. Como TODO el
   resto del sistema (resultados, dictamenes, protocolos, auditoria)
   depende de que exista una fila real en lims_muestras, la solucion es
   crear esa fila de forma anticipada (con codigo SAMP-YYYY-NNN real)
   en el momento de generar el envio, dejando pendiente el llenado de
   los datos fisicos del muestreo para mas adelante.

   Se agrega un flag explicito para distinguir una muestra "completa"
   de una "creada por adelantado, con datos fisicos pendientes" -- no
   alcanza con mirar si los campos fisicos estan vacios, porque esos
   campos ya son legitimamente opcionales hoy (nullable) y no
   distinguen "nunca se cargo" de "se cargo pero quedo en blanco a
   proposito".

   IMPORTANTE: correr a mano en SSMS con una cuenta con permisos DDL.
   ===================================================================== */

USE LIMSS;
GO

IF COL_LENGTH('dbo.lims_muestras', 'datos_muestreo_pendientes') IS NULL
    ALTER TABLE dbo.lims_muestras
        ADD datos_muestreo_pendientes BIT NOT NULL DEFAULT 0;
GO

-- Verificacion
SELECT id_muestra, codigo_muestra, estado, datos_muestreo_pendientes
FROM dbo.lims_muestras
ORDER BY id_muestra DESC;
