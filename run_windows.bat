@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo Please run setup_windows.bat first.
  pause
  exit /b 1
)
start "" .venv\Scripts\pythonw.exe app.py %*
