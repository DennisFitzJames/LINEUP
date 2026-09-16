@echo off
setlocal

cd /d "%~dp0"

if not exist logs mkdir logs

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set LOG_STAMP=%%i
set "LOG_FILE=logs\lineup_run_%LOG_STAMP%.log"

call :resolve_python
if errorlevel 1 exit /b 1

echo. >> "%LOG_FILE%"
echo =================================== >> "%LOG_FILE%"
echo LINEUP background update started >> "%LOG_FILE%"
echo %date% %time% >> "%LOG_FILE%"
echo Python: %PYTHON_CMD% >> "%LOG_FILE%"
echo =================================== >> "%LOG_FILE%"

echo ===================================
echo LINEUP background update started
echo %date% %time%
echo ===================================
echo Using Python: %PYTHON_CMD%

echo.
echo Step 0 - Marking LINEUP run as started...
echo [%date% %time%] Step 0 - Marking LINEUP run as started... >> "%LOG_FILE%"

"%PYTHON_CMD%" app\status.py running >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERROR: Could not update LINEUP status file.
    echo [%date% %time%] ERROR: Could not update LINEUP status file. >> "%LOG_FILE%"
    exit /b 1
)

echo.
echo Step 1 - Backing up LINEUP config...
echo [%date% %time%] Step 1 - Backing up LINEUP config... >> "%LOG_FILE%"

"%PYTHON_CMD%" app\backup_config.py >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERROR: Config backup failed.
    echo [%date% %time%] ERROR: Config backup failed. >> "%LOG_FILE%"

    "%PYTHON_CMD%" app\status.py failed "Config backup" "Config backup failed" >> "%LOG_FILE%" 2>&1
    "%PYTHON_CMD%" app\build_dashboard.py >> "%LOG_FILE%" 2>&1

    exit /b 1
)

echo.
echo Step 2 - Running SAP capacity export...
echo [%date% %time%] Step 2 - Running SAP capacity export... >> "%LOG_FILE%"

cscript //nologo sap_scripts\export_coois_capacities.vbs >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERROR: SAP capacity export failed.
    echo [%date% %time%] ERROR: SAP capacity export failed. >> "%LOG_FILE%"

    "%PYTHON_CMD%" app\status.py failed "SAP capacity export" "SAP capacity export failed" >> "%LOG_FILE%" 2>&1
    "%PYTHON_CMD%" app\build_dashboard.py >> "%LOG_FILE%" 2>&1

    echo LINEUP update stopped.
    exit /b 1
)

echo.
echo Step 3 - Running SAP production list export...
echo [%date% %time%] Step 3 - Running SAP production list export... >> "%LOG_FILE%"

cscript //nologo sap_scripts\export_coois_production_list.vbs >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERROR: SAP production list export failed.
    echo [%date% %time%] ERROR: SAP production list export failed. >> "%LOG_FILE%"

    "%PYTHON_CMD%" app\status.py failed "SAP production list export" "SAP production list export failed" >> "%LOG_FILE%" 2>&1
    "%PYTHON_CMD%" app\build_dashboard.py >> "%LOG_FILE%" 2>&1

    echo LINEUP update stopped.
    exit /b 1
)

echo.
echo Step 4 - Running SAP LX02 logistics text export...
echo [%date% %time%] Step 4 - Running SAP LX02 logistics text export... >> "%LOG_FILE%"

cscript //nologo sap_scripts\export_lx02.vbs >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo WARNING: LX02 export failed. Continuing with the previous or sample file.
    echo [%date% %time%] WARNING: LX02 export failed. Continuing with the previous or sample file. >> "%LOG_FILE%"
)

echo.
echo Step 5 - Running SAP LRF2 logistics text export...
echo [%date% %time%] Step 5 - Running SAP LRF2 logistics text export... >> "%LOG_FILE%"

cscript //nologo sap_scripts\export_lrf2.vbs >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo WARNING: LRF2 export failed. Continuing with the previous or sample file.
    echo [%date% %time%] WARNING: LRF2 export failed. Continuing with the previous or sample file. >> "%LOG_FILE%"
)

echo.
echo Step 6 - Running LINEUP processing pipeline...
echo [%date% %time%] Step 6 - Running LINEUP processing pipeline... >> "%LOG_FILE%"

"%PYTHON_CMD%" app\main.py >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERROR: LINEUP processing failed.
    echo [%date% %time%] ERROR: LINEUP processing failed. >> "%LOG_FILE%"

    "%PYTHON_CMD%" app\status.py failed "LINEUP processing pipeline" "LINEUP processing failed" >> "%LOG_FILE%" 2>&1
    "%PYTHON_CMD%" app\build_dashboard.py >> "%LOG_FILE%" 2>&1

    exit /b 1
)

echo.
echo Step 7 - Marking LINEUP run as successful...
echo [%date% %time%] Step 7 - Marking LINEUP run as successful... >> "%LOG_FILE%"

"%PYTHON_CMD%" app\status.py success >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERROR: Could not mark LINEUP run as successful.
    echo [%date% %time%] ERROR: Could not mark LINEUP run as successful. >> "%LOG_FILE%"
    exit /b 1
)

echo.
echo Step 8 - Rebuilding dashboard with final status...
echo [%date% %time%] Step 8 - Rebuilding dashboard with final status... >> "%LOG_FILE%"

"%PYTHON_CMD%" app\build_dashboard.py >> "%LOG_FILE%" 2>&1

if errorlevel 1 (
    echo ERROR: Final dashboard rebuild failed.
    echo [%date% %time%] ERROR: Final dashboard rebuild failed. >> "%LOG_FILE%"

    "%PYTHON_CMD%" app\status.py failed "Final dashboard rebuild" "Dashboard failed to rebuild after successful LINEUP processing" >> "%LOG_FILE%" 2>&1

    exit /b 1
)

echo.
echo ===================================
echo LINEUP background update finished
echo %date% %time%
echo ===================================

echo =================================== >> "%LOG_FILE%"
echo LINEUP background update finished >> "%LOG_FILE%"
echo %date% %time% >> "%LOG_FILE%"
echo =================================== >> "%LOG_FILE%"

exit /b 0

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
