-- ============================================================
-- MIGRACIÓN: el agente no puede generar dos solicitudes para el mismo IR
-- ------------------------------------------------------------
-- lims_agente_control ya tiene UNIQUE en id_comprobante_erp, pero eso solo
-- evita procesar dos veces el MISMO comprobante en el ciclo normal de
-- polling -- no evita que el endpoint de reproceso manual
-- (POST /api/integraciones/agente/reprocesar/{id}) genere una solicitud
-- nueva si por algún motivo ya existe una para ese erp_nro_ir.
--
-- Alcance deliberadamente acotado a origen='agente': la creación MANUAL de
-- una solicitud para un IR ya usado sigue permitida sin restricción (un
-- analista puede tener motivos válidos para repetirla) -- lo único que no
-- debe pasar nunca es que el agente duplique. El chequeo de "ya existe
-- CUALQUIER solicitud activa para este IR" (manual o agente) antes de
-- insertar vive en código (ver _procesar_comprobante en
-- app/services/agente_muestreo.py), este índice es el resguardo a nivel de
-- base solo para el propio agente.
--
-- Excluye estado='anulada': anular una solicitud libera su IR para que se
-- pueda generar una válida después.
--
-- Idempotente (igual que el resto de backend/*.sql).
--
-- Ejecutar en la BD LIMSS_DEV (SQL Server Management Studio) -- LIMSS_DEV
-- es una copia independiente de LIMSS para desarrollo, no tocar producción.
-- ============================================================

USE [LIMSS_DEV];
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_solicitudes_muestreo_ir_agente'
      AND object_id = OBJECT_ID('lims_solicitudes_muestreo')
)
BEGIN
    CREATE UNIQUE INDEX UQ_solicitudes_muestreo_ir_agente
        ON lims_solicitudes_muestreo(erp_nro_ir)
        WHERE erp_nro_ir IS NOT NULL AND estado <> 'anulada' AND origen = 'agente';
    PRINT 'Índice único filtrado UQ_solicitudes_muestreo_ir_agente creado';
END
GO
