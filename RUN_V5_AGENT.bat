@echo off
cd /d "%~dp0"
title CoinDCX V5.1 Adaptive Agent - PAPER ONLY
if not exist ".venv\Scripts\python.exe" (
  echo Creating V5 virtual environment...
  py -m venv .venv
)
echo Installing/checking requirements...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo Starting CoinDCX V5.1 Adaptive Agent...
".venv\Scripts\python.exe" engine_v5.py
pause
