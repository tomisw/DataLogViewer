@echo off
setlocal

rem Lanzador de un clic para dlv-app (docs/09, seccion de arranque en local).
rem No sustituye al empaquetado con PyInstaller (F5-01, ver dlv-app/dlv_app.spec):
rem solo automatiza lo que ya hace "cd dlv-ui && npm run build" seguido de
rem "uv run python -m dlv_app <log>" para no tener que abrir dos terminales.

cd /d "%~dp0"

set "LOG=%~1"
if "%LOG%"=="" set "LOG=samples\real\AutoLog_20260729_1830.csv"

set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYTHONW%" (
    echo No se encuentra %PYTHONW%
    echo Ejecuta primero: uv sync --all-packages
    pause
    exit /b 1
)

if not exist "%~dp0dlv-ui\dist\index.html" (
    echo Compilando dlv-ui por primera vez, esto puede tardar un momento...
    pushd "%~dp0dlv-ui"
    if not exist node_modules (
        call npm install
        if errorlevel 1 (
            echo Fallo "npm install" en dlv-ui.
            popd
            pause
            exit /b 1
        )
    )
    call npm run build
    if errorlevel 1 (
        echo Fallo "npm run build" en dlv-ui.
        popd
        pause
        exit /b 1
    )
    popd
)

start "" "%PYTHONW%" -m dlv_app "%LOG%"
