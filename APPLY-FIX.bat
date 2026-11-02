@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0APPLY-FIX.ps1"
if errorlevel 1 (
 echo.
 echo Fix did not complete. Read the message above.
 pause
 exit /b 1
)
echo.
echo Now open GitHub Desktop: Commit to main, then Push origin.
pause
