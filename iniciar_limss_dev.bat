@echo off
setlocal

REM Levanta backend y frontend de LIMSS_DEV, cada uno en su propia ventana.

echo Iniciando backend y frontend de LIMSS_DEV...

start "LIMSS_DEV - Backend"  cmd /k "%~dp0iniciar_backend_dev.bat"
start "LIMSS_DEV - Frontend" cmd /k "%~dp0iniciar_frontend_dev.bat"

endlocal
