@echo off
title CoinDCX Paper Bot V3 PRECISION
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
 echo Python not found. Install Python 3.13 64-bit and add it to PATH.
 start https://www.python.org/downloads/windows/
 pause
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo Starting CoinDCX Paper Bot V3 PRECISION...
echo PAPER TRADING ONLY. Close window or press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" engine.py
pause
