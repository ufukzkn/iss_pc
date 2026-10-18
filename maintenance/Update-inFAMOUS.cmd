@echo off
setlocal
if exist "%~dp0out\tlg-probe.exe" (
  powershell.exe -NoProfile -File "%~dp0Update-inFAMOUS.ps1" -InstallDir "%~dp0."
) else (
  powershell.exe -NoProfile -File "%~dp0Update-inFAMOUS.ps1" -InstallDir "%~dp0infamous-windows-x86_64"
)
set "update_exit=%ERRORLEVEL%"
echo.
if not "%update_exit%"=="0" echo Update failed. Read the message above; the working version is preserved or restored.
pause
exit /b %update_exit%
