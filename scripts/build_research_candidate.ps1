$ErrorActionPreference = "Stop"
$manifest = "artifacts/research-candidate/manifest.json"
if (-not (Test-Path -LiteralPath $manifest)) {
  python -m industrial_reliability.package_research_candidate `
    --run-dir artifacts/phase1b/phase1b-run-6050e71c7543 `
    --features data/processed/phase1b/features.parquet `
    --feature-manifest data/processed/phase1b/feature_manifest.json `
    --output-dir artifacts/research-candidate
}
(Get-FileHash -Algorithm SHA256 -LiteralPath $manifest).Hash.ToLowerInvariant()
