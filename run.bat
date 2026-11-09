@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 propscrape.py
    goto finished
)
where python >nul 2>&1
if not errorlevel 1 (
    python propscrape.py
    goto finished
)
echo Python 3 was not found. Install it from https://www.python.org/downloads/
echo During installation select Add Python to PATH.
:finished
echo.
echo If the run succeeded, results are in the output folder next to this file.
pause
