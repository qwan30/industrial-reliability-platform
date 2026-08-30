#!/usr/bin/env bash
set -euo pipefail

STAMP=$(date -u +"%Y%m%dT%H%M%SZ")
OUTPUT_DIR="artifacts/backups/${STAMP}"
mkdir -p "${OUTPUT_DIR}"
DUMP_FILE="${OUTPUT_DIR}/irp.dump"
RESTORE_DB="irp_restore_$(echo "${STAMP}" | tr -d 'TZ')"
CONTAINER_DUMP="/tmp/irp-${STAMP}.dump"

cleanup() {
    echo "Cleaning up drill resources..."
    docker compose exec -T postgres dropdb -U irp --if-exists "${RESTORE_DB}" >/dev/null 2>&1 || true
    docker compose exec -T postgres rm -f "${CONTAINER_DUMP}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "========================================================================"
echo "  Industrial Reliability Platform — PostgreSQL Recovery Drill"
echo "========================================================================"
echo "Timestamp: ${STAMP}"
echo "Backup artifact: ${DUMP_FILE}"
echo "Target restore DB: ${RESTORE_DB}"
echo ""

echo "[1/5] Dumping source database 'irp'..."
docker compose exec -T postgres sh -c "pg_dump -U irp -d irp -Fc -f '${CONTAINER_DUMP}'"

echo "[2/5] Copying backup archive to host..."
docker compose cp "postgres:${CONTAINER_DUMP}" "${DUMP_FILE}"

echo "[3/5] Creating temporary restore database '${RESTORE_DB}'..."
docker compose exec -T postgres createdb -U irp "${RESTORE_DB}"

echo "[4/5] Restoring backup to '${RESTORE_DB}'..."
docker compose exec -T postgres pg_restore -U irp -d "${RESTORE_DB}" --exit-on-error "${CONTAINER_DUMP}"

echo "[5/5] Validating row count parity across critical tables..."
TABLES=("replay_sessions" "score_decisions" "alerts" "rca_reports")
JSON_COUNTS=""

for i in "${!TABLES[@]}"; do
    table="${TABLES[$i]}"
    source_count=$(docker compose exec -T postgres psql -U irp -d irp -Atc "SELECT count(*) FROM ${table}" | tr -d '[:space:]')
    restored_count=$(docker compose exec -T postgres psql -U irp -d "${RESTORE_DB}" -Atc "SELECT count(*) FROM ${table}" | tr -d '[:space:]')

    if [ "${source_count}" != "${restored_count}" ]; then
        echo "ERROR: row count mismatch on table ${table}: source=${source_count}, restored=${restored_count}" >&2
        exit 1
    fi
    echo "  - ${table}: ${source_count} rows (MATCH)"
    if [ $i -gt 0 ]; then
        JSON_COUNTS="${JSON_COUNTS},"
    fi
    JSON_COUNTS="${JSON_COUNTS}\"${table}\": ${source_count}"
done

if command -v sha256sum >/dev/null 2>&1; then
    DUMP_SHA=$(sha256sum "${DUMP_FILE}" | awk '{print $1}')
elif command -v shasum >/dev/null 2>&1; then
    DUMP_SHA=$(shasum -a 256 "${DUMP_FILE}" | awk '{print $1}')
else
    DUMP_SHA=""
fi

REPORT_FILE="${OUTPUT_DIR}/restore-report.json"
cat <<EOF > "${REPORT_FILE}"
{
  "verdict": "PASS",
  "timestamp": "${STAMP}",
  "restore_db": "${RESTORE_DB}",
  "dump_sha256": "${DUMP_SHA}",
  "counts": {
    ${JSON_COUNTS}
  }
}
EOF

echo ""
echo "Recovery drill completed successfully. Report saved to ${REPORT_FILE}"
