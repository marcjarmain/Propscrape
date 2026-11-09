@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (py -3 market.py collect --max-pages 100 & exit /b %errorlevel%)
python market.py collect --max-pages 100
