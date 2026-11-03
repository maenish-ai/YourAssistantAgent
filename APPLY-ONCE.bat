@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0APPLY-ONCE.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
