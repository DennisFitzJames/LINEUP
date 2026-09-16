@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_CMD=%~dp0venv\Scripts\python.exe"
if not defined PYTHON_CMD where py >nul 2>&1 && set "PYTHON_CMD=py"
if not defined PYTHON_CMD where python >nul 2>&1 && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
    echo ERROR: Python could not be found.
    pause
    exit /b 1
)

echo Installing LINEUP requirements using: %PYTHON_CMD% 
"%PYTHON_CMD%" -m pip install --proxy http://127.0.0.1:9000 -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Requirements installation failed.
    pause
    exit /b 1
)

echo.
echo Requirements installed successfully.
pause
