@echo off
setlocal

REM Levanta backend y frontend de LIMSS, cada uno en su propia ventana
REM (ambos quedan corriendo en primer plano, por eso van en ventanas
REM separadas). Usa %~dp0 para ubicar los otros dos .bat sin importar
REM desde donde se ejecute este archivo, siempre que los tres esten
REM en la misma carpeta.

echo Iniciando backend y frontend de LIMSS...

start "LIMSS - Backend"  cmd /k "%~dp0iniciar_backend.bat"
start "LIMSS - Frontend" cmd /k "%~dp0iniciar_frontend.bat"

endlocal
