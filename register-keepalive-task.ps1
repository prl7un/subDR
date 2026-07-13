# Registers a Windows Scheduled Task that runs keepalive.ps1 every 1 minute.
# Run this ONCE on the "on-premise" machine, from inside the cloned subDR folder:
#   powershell -ExecutionPolicy Bypass -File .\register-keepalive-task.ps1

$taskName = "DR-Keepalive"
$scriptPath = Join-Path $PSScriptRoot "keepalive.ps1"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Write-Output "Task '$taskName' already exists. Removing old one first..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Hours 4)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger | Out-Null

Write-Output "Registered scheduled task '$taskName' - running every 1 minute for the next 4 hours."
Write-Output "To stop it (simulate on-premise going down): Stop-ScheduledTask -TaskName '$taskName'; Disable-ScheduledTask -TaskName '$taskName'"
Write-Output "To resume it: Enable-ScheduledTask -TaskName '$taskName'; Start-ScheduledTask -TaskName '$taskName'"
Write-Output "To remove it entirely: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
