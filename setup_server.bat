@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_server.ps1"
if errorlevel 1 echo Setup failed. Read the message above.
pause
