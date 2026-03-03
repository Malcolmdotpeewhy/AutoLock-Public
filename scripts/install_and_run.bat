@echo off
echo ===================================================
echo      LoL Script Architect - Installer
echo ===================================================
echo ===================================================
echo.
cd /d "%~dp0"
cd ..

echo [1/3] Checking for Python Environment...
if exist ".venv\Scripts\python.exe" (
    echo Found active virtual environment.
    set "PYTHON_CMD=.venv\Scripts\python.exe"
    set "PIP_CMD=.venv\Scripts\pip.exe"
    goto :DEPENDENCIES
)

echo No .venv found. Checking for system Python...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    set "PIP_CMD=python -m pip"
    goto :DEPENDENCIES
)

py --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py"
    set "PIP_CMD=py -m pip"
    goto :DEPENDENCIES
)

echo Python is not installed.
pause
exit /b

:DEPENDENCIES

echo.
echo [2/3] Installing Dependencies...
"%PIP_CMD%" install customtkinter requests psutil packaging pillow --quiet
if %errorlevel% neq 0 (
    echo.
    echo Error installing dependencies.
    pause
    exit /b
)
echo Dependencies installed.

echo.
echo [3/3] Launching League Agent...
echo.
"%PYTHON_CMD%" -m core.main
