@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_weekly.ps1"
if errorlevel 1 echo Setup failed. Read the error above.
pause
