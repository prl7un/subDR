# On-premise heartbeat script.
# Simulates the "periodic availability report (curl/cron)" box in the architecture diagram.
# Run this on a schedule (e.g. every 1-2 minutes via Windows Task Scheduler) on the
# machine that plays the "on-premise" role. As long as this keeps running, dr-trigger.yml
# (checked every 5 minutes on GitHub's side) will see a recent commit and do nothing.
# Stop this script (simulate the on-premise machine going down) to let dr-trigger.yml
# detect staleness after its grace period and flip dr_active to true automatically.

param(
    [string]$RepoPath = $PSScriptRoot
)

Set-Location -Path $RepoPath

git pull --quiet origin main

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Set-Content -Path (Join-Path $RepoPath "HEARTBEAT.txt") -Value "last_heartbeat: $timestamp"

git add HEARTBEAT.txt
git commit -m "heartbeat: $timestamp" --quiet
git push --quiet origin main

Write-Output "Heartbeat sent at $timestamp"
