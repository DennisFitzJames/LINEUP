@echo off
setlocal
cd /d "%~dp0"

if not exist logs mkdir logs

call :resolve_python
if errorlevel 1 (
    pause
    exit /b 1
)

echo ===================================
echo Starting LINEUP web server
echo %date% %time%
echo ===================================
echo Using Python: %PYTHON_CMD%
echo.

"%PYTHON_CMD%" -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Flask is not installed for this Python installation.
    echo Run this command from the LINEUP folder:
    echo   "%PYTHON_CMD%" -m pip install -r requirements.txt
    pause
    exit /b 1
)

"%PYTHON_CMD%" app.py
exit /b %errorlevel%

:resolve_python
set "PYTHON_CMD="

if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0venv\Scripts\python.exe"
    goto :python_found
)

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    goto :python_found
)

where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :python_found
)

echo ERROR: Python could not be found.
echo Install Python or create the project virtual environment, then run again.
echo Suggested setup command: py -m venv venv
exit /b 1

:python_found
"%PYTHON_CMD%" --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was found but could not be started: %PYTHON_CMD%
    exit /b 1
)
exit /b 0
