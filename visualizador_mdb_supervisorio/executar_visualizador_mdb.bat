@echo off
setlocal

cd /d C:\Supervisorio

echo ============================================================
echo Visualizador MDB Supervisorio
echo ============================================================
echo.

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)

echo Instalando/atualizando dependencias Python...
%PYTHON_CMD% -m pip install -r requirements_visualizador_mdb.txt
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERRO: Nao foi possivel instalar as dependencias.
    echo Verifique se o Python esta instalado e disponivel no PATH.
    pause
    exit /b 1
)

echo.
echo Iniciando a aplicacao em http://localhost:8501 ...
%PYTHON_CMD% -m streamlit run visualizador_mdb_supervisorio.py --server.address localhost --server.port 8501

pause
endlocal
