@echo off
setlocal
cd /d "%~dp0"
if not exist ".git" (
  echo ERROR: Place this file in the repository root next to the .git folder.
  pause
  exit /b 1
)
if not exist ".github\workflows\build-windows.yml" (
  echo ERROR: Canonical build-windows.yml not found.
  pause
  exit /b 1
)
if exist ".github\workflows\android-female-voice.yml" (
  del /f /q ".github\workflows\android-female-voice.yml"
  if exist ".github\workflows\android-female-voice.yml" (
    echo ERROR: Could not remove duplicate workflow.
    pause
    exit /b 1
  )
  echo SUCCESS: Duplicate Android workflow deleted.
) else (
  echo Duplicate workflow already absent.
)
echo.
echo Now use GitHub Desktop: Commit to main, then Push origin.
pause
