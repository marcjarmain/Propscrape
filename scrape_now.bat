@echo off
cd /d "%~dp0"
where python >nul 2>&1
if not errorlevel 1 (
    python market.py
) else (
    py -3 market.py
)
pause
