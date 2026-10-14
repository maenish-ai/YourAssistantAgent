@echo off
setlocal
cd /d %~dp0

where py >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer from python.org, then run this file again.
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium

echo.
echo Installation complete.
echo Starting Your Assistant Agent...
python app.py
