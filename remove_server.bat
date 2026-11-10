@echo off
echo Run this file as administrator to stop and remove the startup task.
schtasks /End /TN "Propscrape Dashboard"
schtasks /Delete /TN "Propscrape Dashboard" /F
echo A server started manually by run.bat will stop when Windows restarts.
pause
