# On-premise keepalive script.
# Simulates the "periodic availability report (curl/cron)" box in the architecture diagram.
# Run this on a schedule (e.g. every 1 minute via Windows Task Scheduler) on the machine
# that plays the "on-premise" role.
#
# Two independent liveness signals are sent:
#   1. A ping to Healthchecks.io (the real "external monitoring service" from the diagram).
#      Healthchecks.io tracks staleness itself and fires a webhook -> GitHub repository_dispatch
#      -> dr-trigger.yml when the grace period expires. This is reliable and not subject to
#      GitHub Actions' own cron scheduling delays.
#   2. A git commit (kept as a secondary/backup signal + audit trail; dr-trigger.yml's
#      schedule-based check still uses this as a fallback).
#
# Stop this script (simulate the on-premise machine going down) to let Healthchecks.io detect
# staleness after its grace period and trigger DR activation automatically.
#
# SECURITY NOTE: the Healthchecks.io ping URL is a semi-sensitive identifier (anyone who has it
# can send fake "alive" pings), so it is intentionally NOT hardcoded here. It's read from
# hc-ping-url.local.txt (gitignored, never committed) next to this script. Run
# setup-hc-ping-url.ps1 once to create that local file.

param(
    [string]$RepoPath = $PSScriptRoot,
    [string]$HealthchecksPingUrl
)

if (-not $HealthchecksPingUrl) {
    $localUrlFile = Join-Path $PSScriptRoot "hc-ping-url.local.txt"
    if (Test-Path $localUrlFile) {
        $HealthchecksPingUrl = (Get-Content $localUrlFile -Raw).Trim()
    }
}

if ($HealthchecksPingUrl) {
    try {
        Invoke-WebRequest -Uri $HealthchecksPingUrl -UseBasicParsing -TimeoutSec 10 | Out-Null
    } catch {
        Write-Warning "Healthchecks ping failed: $_"
    }
} else {
    Write-Warning "No Healthchecks ping URL configured. Run setup-hc-ping-url.ps1 first (see README note in that script)."
}

Set-Location -Path $RepoPath

git pull --quiet origin main

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Set-Content -Path (Join-Path $RepoPath "KEEPALIVE.txt") -Value "last_keepalive: $timestamp"

git add KEEPALIVE.txt
git commit -m "keepalive: $timestamp" --quiet
git push --quiet origin main

Write-Output "Keepalive sent at $timestamp (Healthchecks ping + git push)"
