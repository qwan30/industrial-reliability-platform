# Industrial Reliability Platform — End-to-End Portfolio Demo Runner

$ErrorActionPreference = "Stop"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Industrial Reliability Platform — Live Demonstration Runner" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "Status: Research-only candidate package active (ALLOW_RESEARCH_CANDIDATE=true)"
Write-Host "Invariants: Grounded RCA with closed-world citations; 100% fail-closed"
Write-Host ""

# 1. Resolve Git SHA
$sha = (git rev-parse HEAD).Trim().ToLowerInvariant()
Write-Host "[1/6] Current Git SHA: $sha" -ForegroundColor Green

# 2. Verify / Build Research Package
Write-Host "[2/6] Verifying research scoring candidate package..." -ForegroundColor Green
$pkgDir = "artifacts/research-candidate"
if (-not (Test-Path $pkgDir)) {
    .\scripts\build_research_candidate.ps1
}
Write-Host "Research candidate package ready at $pkgDir."

# 3. Execute Phase 8 Fault Isolation Drills
Write-Host "[3/6] Running Phase 8 fault isolation drills (in-process)..." -ForegroundColor Green
.\scripts\run_phase8_live_fault_drills.ps1

# 4. Execute Phase 9 Grounded RCA Gate
Write-Host "[4/6] Running Phase 9 grounded RCA gate (in-process)..." -ForegroundColor Green
.\scripts\run_phase9_live_gate.ps1

# 5. Execute Exact-SHA Release Certification
Write-Host "[5/6] Running exact-SHA release certification..." -ForegroundColor Green
$certDir = "artifacts/certification/$sha"
python -m industrial_reliability.release_certification --artifact-dir $certDir --output "$certDir/release-certification.json" --git-sha $sha

# 6. Portfolio Demo Summary
Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Portfolio Demo Completed Successfully!" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "Certification Artifacts:" -ForegroundColor Yellow
Write-Host "  - Phase 8 Drills:      $certDir/phase-8-in-process-fault-drills.json"
Write-Host "  - Phase 9 RCA:         $certDir/phase-9-rca-fallback.json (or openai)"
Write-Host "  - Release Cert:        $certDir/release-certification.json"
Write-Host ""
Write-Host "Live Web Interfaces:" -ForegroundColor Yellow
Write-Host "  - Operator Console:    http://127.0.0.1:5173"
Write-Host "  - Scoring API Docs:    http://127.0.0.1:8000/docs"
Write-Host "  - Grafana Dashboards:  http://127.0.0.1:3001"
Write-Host "  - Prometheus Engine:   http://127.0.0.1:9090"
Write-Host "  - MLflow Registry:     http://127.0.0.1:5000"
Write-Host "========================================================================" -ForegroundColor Cyan
