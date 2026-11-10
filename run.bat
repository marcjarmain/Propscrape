@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 server.py --open
    goto finished
)
where python >nul 2>&1
if not errorlevel 1 (
    python server.py --open
    goto finished
)
echo Python 3 was not found. Install it from https://www.python.org/downloads/
echo During installation select Add Python to PATH.
:finished
echo.
echo The dashboard opens at http://127.0.0.1:8768. No scrape was requested.
pause

