$ErrorActionPreference = "Stop"
$packageDir = "artifacts/research-candidate"
$manifest = Join-Path $packageDir "manifest.json"
$valid = $false
if (Test-Path -LiteralPath $manifest) {
  $schema = (Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json).schema_version
  if ($schema -eq "champion-package-v2") {
    python -m industrial_reliability.package_champion --verify-package $packageDir
    if ($LASTEXITCODE -ne 0) { throw "v2 research package verification failed" }
    $valid = $true
  }
}
if (-not $valid) {
  if (Test-Path -LiteralPath $packageDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $backupDir = "$packageDir.legacy-$stamp"
    Move-Item -LiteralPath $packageDir -Destination $backupDir
  }
  python -m industrial_reliability.package_research_candidate `
    --run-dir artifacts/phase1b/phase1b-run-6050e71c7543 `
    --features data/processed/phase1b/features.parquet `
    --feature-manifest data/processed/phase1b/feature_manifest.json `
    --output-dir $packageDir
}
(Get-FileHash -Algorithm SHA256 -LiteralPath $manifest).Hash.ToLowerInvariant()
