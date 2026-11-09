@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (start "" "http://127.0.0.1:8768" & py -3 market.py dashboard & goto end)
start "" "http://127.0.0.1:8768"
python market.py dashboard
:end
pause
