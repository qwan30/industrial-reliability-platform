# Run Phase 8 Observability & Reliability Fault Drills
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
Set-Location $rootDir

Write-Host "Executing Phase 8 Fault Drills Suite..." -ForegroundColor Cyan

$pythonExe = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

& $pythonExe -m industrial_reliability.fault_report `
    --json-output docs/results/phase-8-observability-reliability.json `
    --md-output docs/results/phase-8-observability-reliability.md

if ($LASTEXITCODE -ne 0) {
    Write-Host "Phase 8 Fault Drills failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Phase 8 Fault Drills completed successfully." -ForegroundColor Green
