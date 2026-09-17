@echo off
setlocal EnableDelayedExpansion
title Lunar Client Offline Manager
color 0B

:: Determine working directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: 1. Check for Python installation
set "PYTHON_EXE="
set "PYTHONW_EXE="

where pythonw.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHONW_EXE=pythonw.exe"
    set "PYTHON_EXE=python.exe"
) else (
    where python.exe >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=python.exe"
        set "PYTHONW_EXE=python.exe"
    ) else (
        where py.exe >nul 2>&1
        if %ERRORLEVEL% equ 0 (
            set "PYTHON_EXE=py -3"
            set "PYTHONW_EXE=pyw -3"
        )
    )
)

:: Search local AppData / ProgramFiles if not in PATH
if "!PYTHON_EXE!"=="" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
        if exist "%%D\python.exe" (
            set "PYTHON_EXE=%%D\python.exe"
            if exist "%%D\pythonw.exe" (
                set "PYTHONW_EXE=%%D\pythonw.exe"
            ) else (
                set "PYTHONW_EXE=%%D\python.exe"
            )
        )
    )
)

if "!PYTHON_EXE!"=="" (
    for /d %%D in ("%ProgramFiles%\Python*") do (
        if exist "%%D\python.exe" (
            set "PYTHON_EXE=%%D\python.exe"
            if exist "%%D\pythonw.exe" (
                set "PYTHONW_EXE=%%D\pythonw.exe"
            ) else (
                set "PYTHONW_EXE=%%D\python.exe"
            )
        )
    )
)

:: 2. Launch mode: GUI vs CLI
if not "%~1"=="" (
    :: CLI parameters were passed
    if not "!PYTHON_EXE!"=="" (
        !PYTHON_EXE! "%SCRIPT_DIR%lunar_offline_manager.py" %*
        exit /b %ERRORLEVEL%
    ) else (
        powershell -ExecutionPolicy Bypass -NoProfile -File "%SCRIPT_DIR%scripts\lunar_offline_gui.ps1" -Command "%~1" -Username "%~2" -Skin "%~3" -Target "%~4"
        exit /b %ERRORLEVEL%
    )
)

:: No CLI parameters: Open Graphical UI
if not "!PYTHONW_EXE!"=="" (
    start "" "!PYTHONW_EXE!" "%SCRIPT_DIR%lunar_offline_manager.py" gui
    exit /b 0
)

:: Fallback to built-in Windows PowerShell GUI (Zero external installation required!)
if exist "%SCRIPT_DIR%scripts\lunar_offline_gui.ps1" (
    start "" powershell -ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File "%SCRIPT_DIR%scripts\lunar_offline_gui.ps1"
    exit /b 0
)

:: If neither Python nor PowerShell script was reachable
color 0C
echo ========================================================
echo   [!] Could not start Lunar Client Offline GUI
echo ========================================================
echo.
echo Python was not detected on this system.
echo.
echo Would you like to automatically install Python now via Windows Package Manager (winget)?
echo [1] Install Python 3 (Recommended)
echo [2] Exit
echo.
set /p CHOICE="Enter your choice (1/2): "
if "%CHOICE%"=="1" (
    echo.
    echo [*] Installing Python... Please wait a moment.
    winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    echo.
    echo [✓] Python installation finished! Restarting Lunar Offline Manager...
    pause
    goto :eof
)

exit /b 1
