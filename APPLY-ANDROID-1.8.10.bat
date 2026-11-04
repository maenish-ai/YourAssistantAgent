@echo off
cd /d "%~dp0"
py -3 APPLY-ANDROID-1.8.10.py
if errorlevel 1 python APPLY-ANDROID-1.8.10.py
pause
