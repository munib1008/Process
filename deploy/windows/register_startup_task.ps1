<#  Registers MEA Process Hub as a task that starts with the server and restarts after a failure.
    Run once in an elevated PowerShell:   .\register_startup_task.ps1 -Account "DOMAIN\svc_processhub"
    Use a service account without interactive logon rights that has Modify rights on the data folder only.
    Remove again with:   Unregister-ScheduledTask -TaskName "MEA Process Hub" -Confirm:$false                 #>
param([Parameter(Mandatory = $true)][string]$Account)
$bat = Join-Path $PSScriptRoot "start_server.bat"
if (-not (Test-Path $bat)) { throw "start_server.bat not found next to this script" }
$cred = Get-Credential -UserName $Account -Message "Password of the service account"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`"" -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
Register-ScheduledTask -TaskName "MEA Process Hub" -Action $action -Trigger $trigger -Settings $settings `
  -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null
Start-ScheduledTask -TaskName "MEA Process Hub"
Start-Sleep 8
try { $r = Invoke-RestMethod "http://127.0.0.1:$(if ($env:MEA_HUB_PORT) { $env:MEA_HUB_PORT } else { 8765 })/api/health"; Write-Host "Running, version $($r.version)" }
catch { Write-Warning "The task was registered but the app does not answer yet. Check server.log in the data folder." }
