# Run this ONCE on the on-premise machine to store your Healthchecks.io ping URL locally.
# The URL is saved to hc-ping-url.local.txt, which is gitignored and never committed -
# keepalive.ps1 reads it from there automatically.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\setup-hc-ping-url.ps1

$url = Read-Host "Paste your Healthchecks.io ping URL (e.g. https://hc-ping.com/xxxxxxxx-...)"

if ($url -notmatch '^https://hc-ping\.com/') {
    Write-Warning "That doesn't look like a Healthchecks.io ping URL (expected https://hc-ping.com/...). Saving it anyway."
}

Set-Content -Path (Join-Path $PSScriptRoot "hc-ping-url.local.txt") -Value $url -NoNewline

Write-Output "Saved. This file is gitignored and will never be committed."
