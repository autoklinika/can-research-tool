param(
    [double]$IntervalSeconds = 1.0
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$env:CRT_LIVE_PERF = "1"
$env:CRT_LIVE_PERF_INTERVAL_S = [string]::Format(
    [System.Globalization.CultureInfo]::InvariantCulture,
    "{0}",
    $IntervalSeconds
)

Write-Host "CRT Stage H: ENABLED"
Write-Host "CRT_LIVE_PERF=$env:CRT_LIVE_PERF"
Write-Host "CRT_LIVE_PERF_INTERVAL_S=$env:CRT_LIVE_PERF_INTERVAL_S"
Write-Host "Repo: $repoRoot"
Write-Host "Raport zostanie utworzony po Start Capture w: <projekt>\reports"

$python = Get-Command python -ErrorAction Stop
& $python.Source ".\crt_gui.py"
exit $LASTEXITCODE
