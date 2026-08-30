# Industrial Reliability Platform — PostgreSQL Backup & Restore Drill Runner
$ErrorActionPreference = "Stop"

$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$outputDir = Join-Path 'artifacts/backups' $stamp
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$dump = Join-Path $outputDir 'irp.dump'
$restoreDb = "irp_restore_$($stamp.Replace('T','_').Replace('Z',''))"
$containerDump = "/tmp/irp-$stamp.dump"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Industrial Reliability Platform — PostgreSQL Recovery Drill" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "Timestamp: $stamp"
Write-Host "Backup artifact: $dump"
Write-Host "Target restore DB: $restoreDb"
Write-Host ""

try {
    Write-Host "[1/5] Dumping source database 'irp'..." -ForegroundColor Green
    docker compose exec -T postgres sh -c "pg_dump -U irp -d irp -Fc -f '$containerDump'"
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }

    Write-Host "[2/5] Copying backup archive to host..." -ForegroundColor Green
    docker compose cp "postgres:$containerDump" $dump
    if ($LASTEXITCODE -ne 0) { throw 'docker compose cp failed' }

    Write-Host "[3/5] Creating temporary restore database '$restoreDb'..." -ForegroundColor Green
    docker compose exec -T postgres createdb -U irp $restoreDb
    if ($LASTEXITCODE -ne 0) { throw 'createdb failed' }

    Write-Host "[4/5] Restoring backup to '$restoreDb'..." -ForegroundColor Green
    docker compose exec -T postgres pg_restore -U irp -d $restoreDb --exit-on-error $containerDump
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed' }

    Write-Host "[5/5] Validating row count parity across critical tables..." -ForegroundColor Green
    $tables = 'replay_sessions','score_decisions','alerts','rca_reports'
    $counts = @{}
    foreach ($table in $tables) {
        $source = docker compose exec -T postgres psql -U irp -d irp -Atc "SELECT count(*) FROM $table"
        $restored = docker compose exec -T postgres psql -U irp -d $restoreDb -Atc "SELECT count(*) FROM $table"
        if ($source.Trim() -ne $restored.Trim()) { throw "row count mismatch: $table (source=$($source.Trim()), restored=$($restored.Trim()))" }
        $counts[$table] = [int64]$source.Trim()
        Write-Host "  - $table`: $($counts[$table]) rows (MATCH)" -ForegroundColor DarkGreen
    }

    $dumpHash = (Get-FileHash $dump -Algorithm SHA256).Hash.ToLower()
    $reportPath = Join-Path $outputDir 'restore-report.json'
    @{
        verdict = 'PASS'
        timestamp = $stamp
        restore_db = $restoreDb
        dump_sha256 = $dumpHash
        counts = $counts
    } | ConvertTo-Json -Depth 4 | Set-Content $reportPath

    Write-Host ""
    Write-Host "Recovery drill completed successfully. Report saved to $reportPath" -ForegroundColor Cyan
}
finally {
    Write-Host "Cleaning up drill resources..." -ForegroundColor Yellow
    docker compose exec -T postgres dropdb -U irp --if-exists $restoreDb 2>$null
    docker compose exec -T postgres rm -f $containerDump 2>$null
}
