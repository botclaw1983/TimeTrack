@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === TimeTrack portable build ===

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
    echo Python не найден. Создайте .venv или установите Python 3.10+.
    exit /b 1
)

echo Using: %PY%

"%PY%" -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 exit /b 1

if not exist "%~dp0resources" mkdir "%~dp0resources"
if not exist "%~dp0resources\icon.png" (
    echo Creating placeholder icon...
    "%PY%" "%~dp0tools\create_icon.py"
)

echo Building with PyInstaller...
"%PY%" -m PyInstaller TimeTrack.spec --noconfirm --clean
if errorlevel 1 exit /b 1

set "OUT=%~dp0portable\TimeTrack"
if exist "%OUT%" rmdir /s /q "%OUT%"
if not exist "%~dp0portable" mkdir "%~dp0portable"
xcopy /E /I /Y "%~dp0dist\TimeTrack" "%OUT%" >nul
if errorlevel 1 exit /b 1

echo.>"%OUT%\portable.flag"
if not exist "%OUT%\data" mkdir "%OUT%\data"
copy /Y "%~dp0portable\README.txt" "%OUT%\README.txt" >nul 2>&1

echo.
echo Ready: portable\TimeTrack\
echo Copy the whole TimeTrack folder to another PC and run TimeTrack.exe
echo No install and no admin rights required.
echo.
exit /b 0
