param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8000",
    [string]$AlertId = ""
)

$ErrorActionPreference = "Stop"
$sha = (git rev-parse HEAD).Trim().ToLowerInvariant()
$outputDir = "artifacts/certification/$sha"
$phase8Path = Join-Path $outputDir "phase-8-live-fault-drills.json"
if (-not (Test-Path -LiteralPath $phase8Path)) {
    throw "Phase 8 runtime report is missing: $phase8Path"
}

$phase8 = Get-Content -Raw -LiteralPath $phase8Path | ConvertFrom-Json
if ($phase8.verdict -ne "PASS" -or $phase8.evidence_level -ne "INTEGRATION") {
    throw "Phase 8 report is not a passing dependency-backed integration report."
}

$abnormalDrills = @($phase8.drills | Where-Object { $_.drill_type -eq "known-abnormal-replay" })
if ($abnormalDrills.Count -ne 1 -or -not $abnormalDrills[0].alert_id) {
    throw "Phase 8 report must contain exactly one known-abnormal-replay alert_id."
}
$phase8AlertId = [string]$abnormalDrills[0].alert_id
if ($AlertId -and $AlertId -ne $phase8AlertId) {
    throw "Provided AlertId does not match the Phase 8 known-abnormal-replay alert."
}

python -m industrial_reliability.phase9_live_gate `
    --git-sha $sha `
    --output-dir $outputDir `
    --base-url $ApiBaseUrl `
    --alert-id $phase8AlertId
if ($LASTEXITCODE -ne 0) {
    throw "Phase 9 grounded RCA gate failed with exit code $LASTEXITCODE."
}
