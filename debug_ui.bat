@echo off
setlocal
title Smite Plugin Base — Debug UI
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo         Run launch.bat first to set it up.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo [DEBUG UI] Starting...
python src\gui\debug_ui.py

echo.
echo Debug UI exited.
pause
