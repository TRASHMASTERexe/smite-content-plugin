@echo off
setlocal EnableDelayedExpansion
title Smite Plugin Base

:: ============================================================
::  Smite Plugin Base — Setup & Launch
::  Double-click this file to install and run the app.
::  Re-running it after the first time is fast (venv reused).
:: ============================================================

:: --- Require Administrator (keyboard library needs it) -------
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: --- Move to the script's directory -------------------------
cd /d "%~dp0"

echo.
echo  ================================================
echo   Smite Plugin Base
echo  ================================================
echo.

:: --- Check Python is available ------------------------------
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    echo         Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYVER=%%i
echo  Python: %PYVER%

:: --- Create virtual environment if missing ------------------
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo  [SETUP] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [SETUP] Virtual environment created.
)

:: --- Activate venv ------------------------------------------
call .venv\Scripts\activate.bat

:: --- Install / update requirements --------------------------
echo.
echo  [SETUP] Installing requirements (this may take a minute on first run)...
pip install -q --upgrade pip
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Dependency installation failed. Check the output above.
    pause
    exit /b 1
)
echo  [SETUP] Requirements OK.

:: --- Launch the app -----------------------------------------
echo.
echo  [RUN] Starting Smite Plugin Base...
echo  [RUN] Press Ctrl+C to stop.
echo.

python main.py

:: --- Keep window open if it crashes -------------------------
echo.
echo  App exited (code %errorlevel%).
pause
