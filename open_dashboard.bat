@echo off
cd /d "%~dp0"
if exist "output\dashboard.html" (
    start "" "output\dashboard.html"
) else (
    echo No dashboard yet. Run setup_weekly.bat to import existing listings, or run.bat for a new collection.
    pause
)
