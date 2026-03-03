@echo off
cd /d "C:\Users\Administrator\antigravity-worspaces-1\antigravity-worspaces"
set PYTHONPATH=%CD%
".venv\Scripts\python.exe" -m core.main
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo === CRASHED - see above ===
    pause
)
