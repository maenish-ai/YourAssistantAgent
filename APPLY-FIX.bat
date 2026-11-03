@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0APPLY-FIX.ps1"
if errorlevel 1 (
  echo.
  echo Fix did not complete. Read the error above.
  pause
  exit /b 1
)
echo.
echo IMPORTANT: Commit to main and Push origin in GitHub Desktop.
pause
