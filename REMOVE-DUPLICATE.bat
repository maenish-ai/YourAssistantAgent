@echo off
setlocal
cd /d "%~dp0"
if not exist ".github\workflows\build-windows.yml" (
  echo ERROR: Extract the ZIP into the root of YourAssistantAgent repository.
  pause
  exit /b 1
)
if exist ".github\workflows\android-female-voice.yml" del /f /q ".github\workflows\android-female-voice.yml"
if exist ".github\workflows\windows-build.yml" del /f /q ".github\workflows\windows-build.yml"
if exist ".github\workflows\android-female-voice.yml" (
 echo ERROR: Could not delete duplicate workflow.
 pause
 exit /b 1
)
echo Fixed workflow files. Open GitHub Desktop, commit and PUSH.
pause
