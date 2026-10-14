@echo off
setlocal
cd /d %~dp0

where powershell >nul 2>&1
if errorlevel 1 (
  echo PowerShell was not found.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows.ps1"

echo.
echo Build process finished.
echo Check the release folder for output files.
pause
