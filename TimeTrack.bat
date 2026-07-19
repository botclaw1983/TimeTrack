@echo off
setlocal
cd /d "%~dp0"

set "PYTHONW="
if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
if not defined PYTHONW if exist "%~dp0.venv\Scripts\python.exe" set "PYTHONW=%~dp0.venv\Scripts\python.exe"
if not defined PYTHONW where pythonw >nul 2>&1 && set "PYTHONW=pythonw"
if not defined PYTHONW where python >nul 2>&1 && set "PYTHONW=python"

if not defined PYTHONW (
    echo Python не найден. Установите Python 3.10+ или создайте виртуальное окружение:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

start "" "%PYTHONW%" "%~dp0main.py"
exit /b 0
