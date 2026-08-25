$ErrorActionPreference = "Stop"
$sha = (git rev-parse HEAD).Trim().ToLowerInvariant()
$outputDir = "artifacts/certification/$sha"
python -m industrial_reliability.phase9_live_gate --git-sha $sha --output-dir $outputDir
