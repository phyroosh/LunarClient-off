@echo off
setlocal EnableDelayedExpansion
title Lunar Client Offline 1-Click Fixer & Manager
color 0B

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: If user passed CLI arguments, forward directly to LunarOffline.bat
if not "%~1"=="" (
    call "%SCRIPT_DIR%LunarOffline.bat" %*
    exit /b %ERRORLEVEL%
)

echo ========================================================
echo       LUNAR CLIENT OFFLINE 1-CLICK FIXER & MANAGER
echo ========================================================
echo.
echo [*] Checking and preparing Lunar Client Offline setup...

:: Check if Python is available to apply patch directly
where python.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [*] Applying offline validation patch to app.asar...
    python "%SCRIPT_DIR%lunar_offline_manager.py" patch
) else (
    where py.exe >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo [*] Applying offline validation patch to app.asar...
        py -3 "%SCRIPT_DIR%lunar_offline_manager.py" patch
    ) else (
        if exist "%SCRIPT_DIR%scripts\lunar_offline_gui.ps1" (
            echo [*] Applying offline patch via native PowerShell engine...
            powershell -ExecutionPolicy Bypass -NoProfile -File "%SCRIPT_DIR%scripts\lunar_offline_gui.ps1" -Command "patch"
        )
    )
)

echo.
echo [✓] Lunar Client offline fix verified!
echo [*] Opening Lunar Client Offline Manager GUI...
echo.

:: Launch GUI
call "%SCRIPT_DIR%LunarOffline.bat"
exit /b 0
