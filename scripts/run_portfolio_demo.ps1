# Industrial Reliability Platform — End-to-End Portfolio Demo Runner
param(
    [switch]$CheckPreflight = $true,
    [switch]$SkipDocker = $false,
    [switch]$SeedReplay = $true,
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

function Assert-CommandSuccess {
    param([string]$StepDescription)
    if ($LASTEXITCODE -ne 0) {
        Write-Error "ERROR: $StepDescription failed with exit code $LASTEXITCODE."
        exit 1
    }
}

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Industrial Reliability Platform — Live Demonstration Runner" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "Status: Research-only candidate package active (ALLOW_RESEARCH_CANDIDATE=true)"
Write-Host "Invariants: Grounded RCA with closed-world citations; 100% fail-closed"
Write-Host ""

# 1. Preflight Verification
if ($CheckPreflight) {
    Write-Host "[1/7] Running host environment preflight checks..." -ForegroundColor Green
    python deploy/preflight.py
    Assert-CommandSuccess "Preflight check"
}

# 2. Resolve Git SHA
$sha = (git rev-parse HEAD).Trim().ToLowerInvariant()
Write-Host "[2/7] Current Git SHA: $sha" -ForegroundColor Green

# 3. Verify / Build Research Package
Write-Host "[3/7] Verifying research scoring candidate package..." -ForegroundColor Green
$pkgDir = "artifacts/research-candidate"
if (-not (Test-Path "$pkgDir/manifest.json")) {
    .\scripts\build_research_candidate.ps1
    Assert-CommandSuccess "Build research candidate package"
}
Write-Host "Research candidate package ready at $pkgDir."

# 4. Measure Calibration Replay Benchmark
Write-Host "[4/7] Measuring frozen replay workload benchmark..." -ForegroundColor Green
$benchDir = "artifacts/benchmarks/$sha"
python -m industrial_reliability.replay_benchmark --workload ops/benchmarks/replay-workload.json --git-sha $sha --package-manifest "$pkgDir/manifest.json" --output-dir $benchDir
Assert-CommandSuccess "Replay benchmark"

# 5. Execute Phase 8 Fault Isolation Drills
Write-Host "[5/7] Running Phase 8 fault isolation drills..." -ForegroundColor Green
.\scripts\run_phase8_live_fault_drills.ps1
Assert-CommandSuccess "Phase 8 fault isolation drills"

# 6. Execute Phase 9 Grounded RCA Gate
Write-Host "[6/7] Running Phase 9 grounded RCA gate..." -ForegroundColor Green
.\scripts\run_phase9_live_gate.ps1
Assert-CommandSuccess "Phase 9 grounded RCA gate"

# 7. Execute Exact-SHA Release Certification
Write-Host "[7/7] Running exact-SHA release certification..." -ForegroundColor Green
$certDir = "artifacts/certification/$sha"
if (-not (Test-Path $certDir)) {
    New-Item -ItemType Directory -Path $certDir -Force | Out-Null
}

# Copy immutable authoritative Phase 1B metrics to certification directory
if (Test-Path "docs/results/phase-1b-metrics.json") {
    Copy-Item "docs/results/phase-1b-metrics.json" "$certDir/phase-1b-metrics.json" -Force
}

$certJson = "$certDir/release-certification.json"
python -m industrial_reliability.release_certification --artifact-dir $certDir --output $certJson --git-sha $sha
Assert-CommandSuccess "Release certification execution"

# Verify Certification Result
if (-not (Test-Path $certJson)) {
    Write-Error "Release certification report was not generated."
    exit 1
}

$reportData = Get-Content $certJson -Raw | ConvertFrom-Json
if (-not $reportData.is_certified) {
    Write-Error "Platform release certification failed ($($reportData.verdict)). Review limitations in $certJson."
    exit 1
}

# Portfolio Demo Summary
Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Portfolio Demo Completed Successfully!" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "Certification Artifacts:" -ForegroundColor Yellow
Write-Host "  - Phase 1B Baseline:   $certDir/phase-1b-metrics.json"
Write-Host "  - Phase 8 Drills:      $certDir/phase-8-live-fault-drills.json"
Write-Host "  - Phase 9 RCA:         $certDir/phase-9-rca-fallback.json (or openai)"
Write-Host "  - Benchmark:           $benchDir/benchmark.json"
Write-Host "  - Release Cert:        $certJson"
Write-Host ""
Write-Host "Live Web Interfaces:" -ForegroundColor Yellow
Write-Host "  - Operator Console:    http://127.0.0.1:5173"
Write-Host "  - Scoring API Docs:    http://127.0.0.1:8000/docs"
Write-Host "  - Grafana Dashboards:  http://127.0.0.1:3001"
Write-Host "  - Prometheus Engine:   http://127.0.0.1:9090"
Write-Host "  - MLflow Registry:     http://127.0.0.1:5000"
Write-Host "========================================================================" -ForegroundColor Cyan
