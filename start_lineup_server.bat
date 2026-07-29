@echo off
cd /d "%~dp0"

if not exist logs mkdir logs

echo ===================================
echo Starting LINEUP web server
echo %date% %time%
echo ===================================

call venv\Scripts\activate.bat

if errorlevel 1 (
    echo ERROR: Could not activate virtual environment.
    pause
    exit /b 1
)

python app.py
