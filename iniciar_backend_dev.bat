@echo off
setlocal

REM Inicia el backend de LIMSS_DEV (FastAPI + Uvicorn) con el Python
REM embebible. Usa la ruta LOCAL del disco (no la ruta de red).

cd /d "C:\ServerFolders\Empresa\Lamar\LIMSS_DEV\backend"
if errorlevel 1 (
    echo ERROR: no se encontro la carpeta del backend en la ruta esperada.
    echo Verificar que C:\ServerFolders\Empresa\Lamar\LIMSS_DEV\backend exista.
    pause
    exit /b 1
)

echo Verificando dependencias de Python (requirements.txt)...
C:\Python312-embed\python.exe -m pip install -q -r requirements.txt

echo Iniciando backend LIMSS_DEV en el puerto 8003...
C:\Python312-embed\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8003

endlocal
