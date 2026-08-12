@echo off
setlocal

REM Inicia el backend de LIMSS (FastAPI + Uvicorn) con el Python embebible.
REM Usa la ruta LOCAL del disco (no la ruta de red \\LAMARSERVER\Empresa\...)
REM porque instalar/operar dependencias a traves de la red demostro ser
REM poco confiable (corrupcion de paquetes). Si en algun momento se mueve
REM la carpeta del proyecto, actualizar la ruta de abajo.

cd /d "C:\ServerFolders\Empresa\Lamar\LIMSS\backend"
if errorlevel 1 (
    echo ERROR: no se encontro la carpeta del backend en la ruta esperada.
    echo Verificar que C:\ServerFolders\Empresa\Lamar\LIMSS\backend exista.
    pause
    exit /b 1
)

echo Verificando dependencias de Python (requirements.txt)...
C:\Python312-embed\python.exe -m pip install -q -r requirements.txt

echo Iniciando backend LIMSS en el puerto 8002...
C:\Python312-embed\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002

endlocal
