@echo off
cd /d "%~dp0"
echo Starting DCPM System...

REM Try to use python from D:\py3.12.9\python.exe first
set PYTHON_EXE=D:\py3.12.9\python.exe

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -m dcpm
) else (
    echo Python not found at %PYTHON_EXE%, trying global python...
    python -m dcpm
)

if %errorlevel% neq 0 (
    echo.
    echo --------------------------------------------------
    echo Error occurred (Exit Code: %errorlevel%)
    echo Please check if Python and dependencies are installed.
    echo Install dependencies: pip install -r requirements.txt
    echo --------------------------------------------------
    pause
)
