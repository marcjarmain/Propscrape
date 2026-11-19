$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Get-Command python.exe -ErrorAction SilentlyContinue
$probe = $null
if ($python) {
    $probe = & $python.Source -c 'import sys; assert sys.version_info.major == 3; print(sys.executable)'
    if ($LASTEXITCODE -ne 0) { $probe = $null }
}
if (-not $probe) {
    $python = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($python) { $probe = & $python.Source -3 -c 'import sys; print(sys.executable)' }
    if (-not $python -or $LASTEXITCODE -ne 0) { throw 'Install Python 3, then run setup_weekly.bat again.' }
}
$exe = ($probe | Select-Object -Last 1).Trim()
if (Test-Path 'output\listings.csv') {
    & $exe market.py --import-csv 'output\listings.csv'
    if ($LASTEXITCODE -ne 0) { throw 'Could not import existing listings. Schedule was not installed.' }
}
$action = New-ScheduledTaskAction -Execute $exe -Argument ('"' + (Join-Path $PSScriptRoot 'scheduled_run.py') + '"') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday -At '09:00'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Propscrape Weekly' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Weekly Property24 search snapshot; local database and market report.' -Force | Out-Null
Write-Host 'Installed: Mondays 09:00 using this PC clock. PC must be on, online and you must be signed in.'
Write-Host 'If missed, Windows is configured to catch up when available. No scrape starts during setup.'
Write-Host 'Open output\dashboard.html to read the report.'
