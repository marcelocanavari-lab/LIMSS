@echo off
setlocal

REM Inicia el backend de LIMSS (FastAPI + Uvicorn) con el Python embebible.
REM pushd resuelve la ruta de red (UNC) mapeandola a una unidad temporal;
REM si en el servidor existe una ruta local directa a esta carpeta, se
REM puede reemplazar por esa ruta para evitar el mapeo.

pushd "\\LAMARSERVER\Empresa\Lamar\LIMSS\backend"

echo Verificando dependencias de Python (requirements.txt)...
C:\Python312-embed\python.exe -m pip install -q -r requirements.txt

echo Iniciando backend LIMSS en el puerto 8002...
C:\Python312-embed\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002

popd
endlocal
