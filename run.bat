@echo off
setlocal enableextensions enabledelayedexpansion

rem Determine the directory where this script lives and switch to it
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Unable to change to script directory: %SCRIPT_DIR%
    exit /b 1
)

rem Find an available Python interpreter
set "PYTHON_CMD="
for %%P in (py python python3) do (
    where %%P >nul 2>&1 && (
        set "PYTHON_CMD=%%P"
        goto :python_found
    )
)

echo [ERROR] Python 3 was not found in PATH. Please install it and try again.
popd >nul
exit /b 1

:python_found
rem Create the virtual environment if it does not exist yet
if not exist "venv\Scripts\activate.bat" (
    echo Creating Python virtual environment...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        popd >nul
        exit /b 1
    )
)

rem Activate the virtual environment
call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Could not activate the virtual environment.
    popd >nul
    exit /b 1
)

rem Ensure pip and project dependencies are installed
python -m pip install --upgrade pip >nul
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    popd >nul
    exit /b 1
)

python -m pip install --upgrade flask requests beautifulsoup4
if errorlevel 1 (
    echo [ERROR] Failed to install required Python packages.
    popd >nul
    exit /b 1
)

echo.
echo Launching Chat Unreal server...
python Chat_Unreal_Server.py
set "EXIT_CODE=%ERRORLEVEL%"

rem Deactivate virtual environment and restore directory
if exist "%VIRTUAL_ENV%" (
    call deactivate >nul 2>&1
)

popd >nul
exit /b %EXIT_CODE%
