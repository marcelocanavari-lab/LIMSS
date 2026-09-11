-- ============================================================
-- MIGRACIÓN: IR manual para testigos comprados externamente
-- ------------------------------------------------------------
-- ir_manual: distingue un nro_ir real (vinculado a un comprobante IR
-- verdadero en el ERP, GIN01CPB) de uno asignado manualmente (avanzando
-- el contador GIT30NUM.NUMCOM sin comprobante real detrás) -- ver
-- asignar_ir_manual en app/api/routes/maestros.py. Default 0: todo
-- testigo existente hoy queda marcado como "no manual" (lo que ya
-- tenían cargado, si algo, se asume real).
--
-- nro_ir queda en VARCHAR(6) tal como está hoy -- el correlativo de IR
-- resetea a 1 cada año (confirmado con el usuario), así que "NNN/AA"
-- nunca supera 3 dígitos dentro de un mismo año y siempre entra en 6
-- caracteres. No hace falta ensancharla.
--
-- Idempotente: no hace nada si la columna ya existe.
--
-- Ejecutar en la BD LIMSS (SQL Server Management Studio)
-- ============================================================

USE [LIMSS];
GO

IF COL_LENGTH('lims_testigos', 'ir_manual') IS NULL
BEGIN
    ALTER TABLE lims_testigos
        ADD ir_manual BIT NOT NULL CONSTRAINT df_testigos_ir_manual DEFAULT 0;
    PRINT 'Columna ir_manual agregada a lims_testigos';
END
GO
