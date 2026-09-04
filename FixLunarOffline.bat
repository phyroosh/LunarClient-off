@echo off
setlocal EnableDelayedExpansion
title Lunar Client Offline 1-Click Fixer
color 0B
cls

echo ========================================================
echo           LUNAR CLIENT OFFLINE 1-CLICK FIXER
echo ========================================================
echo.

:: 1. Find Node.js executable
set "NODE_BIN=node"
where node >nul 2>&1
if %ERRORLEVEL% neq 0 (
    if exist "C:\Program Files\nodejs\node.exe" (
        set "NODE_BIN=C:\Program Files\nodejs\node.exe"
    ) else if exist "C:\Program Files (x86)\nodejs\node.exe" (
        set "NODE_BIN=C:\Program Files (x86)\nodejs\node.exe"
    ) else (
        color 0C
        echo [ERROR] Node.js is required to execute the fix, but was not found!
        echo Please make sure Node.js is installed on your computer.
        echo.
        pause
        exit /b 1
    )
)

:: 2. Set script path
set "FIX_SCRIPT=%USERPROFILE%\.lunarclient\fix_lunar.js"

if not exist "%FIX_SCRIPT%" (
    color 0C
    echo [ERROR] Fix script not found at: "%FIX_SCRIPT%"
    echo.
    pause
    exit /b 1
)

:: 3. Execute fixer script
"%NODE_BIN%" "%FIX_SCRIPT%"
if %ERRORLEVEL% neq 0 (
    color 0C
    echo.
    echo [!] An error occurred while applying the fix.
    echo.
    pause
    exit /b 1
)

color 0A
echo.
set /p LAUNCH="Would you like to launch Lunar Client now? (Y/N, default Y): "
if /I "%LAUNCH%"=="" set LAUNCH=Y
if /I "%LAUNCH%"=="Y" (
    echo Launching Lunar Client...
    start "" "%LOCALAPPDATA%\Programs\Lunar Client\Lunar Client.exe"
)

echo.
echo All done! Have fun playing!
ping -n 3 127.0.0.1 >nul 2>&1
exit /b 0
