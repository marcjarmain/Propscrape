@echo off
cd /d "%~dp0"
schtasks /Create /F /SC WEEKLY /D SUN /ST 08:00 /TN "PropScrape Weekly Market Snapshot" /TR "cmd.exe /c \"\"%~dp0weekly_collect.bat\"\"" 
if errorlevel 1 (echo Failed to register weekly task. & pause & exit /b 1)
echo Weekly collection set for Sunday 08:00 while PC is on and logged in if required.
pause
