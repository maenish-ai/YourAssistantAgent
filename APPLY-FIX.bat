@echo off
setlocal
cd /d "%~dp0"
if not exist ".github\workflows\build-windows.yml" (
  echo ERROR: Extract this ZIP into the YourAssistantAgent repository ROOT first.
  pause
  exit /b 1
)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "FIX-GITHUB-ACTIONS.py"
) else (
  python "FIX-GITHUB-ACTIONS.py"
)
if errorlevel 1 (
 echo Fix failed. See error above.
 pause
 exit /b 1
)
echo.
echo Done. Open GitHub Desktop, review 2 changes, Commit and Push.
pause
