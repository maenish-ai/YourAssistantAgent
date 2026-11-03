@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
 py -3 APPLY-ANDROID-STARTUP-FIX.py
) else (
 python APPLY-ANDROID-STARTUP-FIX.py
)
pause
