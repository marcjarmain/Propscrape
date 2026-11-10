$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Right-click setup_server.bat and choose Run as administrator. This installs a startup task.' }
$python = Get-Command py.exe -ErrorAction SilentlyContinue
if ($python) { $probe = & $python.Source -3 -c 'import sys; print(sys.executable)' }
else { $python = Get-Command python.exe -ErrorAction Stop; $probe = & $python.Source -c 'import sys; print(sys.executable)' }
if ($LASTEXITCODE -ne 0) { throw 'Python 3 is not working.' }
$exe = ($probe | Select-Object -Last 1).Trim()
$action = New-ScheduledTaskAction -Execute $exe -Argument ('"' + (Join-Path $PSScriptRoot 'server.py') + '"') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'Propscrape Dashboard' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Read-only localhost dashboard. Does not initiate scrapes.' -Force | Out-Null
$existing = $null
try { $existing = Invoke-RestMethod -Uri 'http://127.0.0.1:8768/health' -TimeoutSec 2 } catch {}
if (-not $existing) { Start-ScheduledTask -TaskName 'Propscrape Dashboard' }
Write-Host 'Startup task installed: Propscrape Dashboard. Address: http://127.0.0.1:8768'
Write-Host 'Double-click run.bat from your normal desktop to open it. No scrape starts.'
Write-Host 'Keep this repository in a trusted local folder. The boot task runs its server.py as SYSTEM.'
Write-Host 'The server cannot run while the PC is off or asleep. The weekly scrape schedule is separate.'
