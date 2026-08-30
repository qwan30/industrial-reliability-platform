# Industrial Reliability Platform — Operations Runbook

## 1. System Overview

The Industrial Reliability Platform is a high-throughput, local-first industrial anomaly detection and Root-Cause Analysis (RCA) platform. It processes high-frequency sensor telemetry, evaluates rolling temporal anomaly scores, enforces locked operational alert policies, provides real-time operator streaming dashboards, and surfaces grounded root-cause insights with strict closed-world citation enforcement.

---

## 2. Pinned One-Command Deployment

### Prerequisites:
- Python 3.12+
- Docker & Docker Compose
- Node.js 20+ (for operator console development)
- 4GB+ available RAM, 10GB+ available disk

### Launch Stack:
```bash
# 1. Start core infrastructure and services
docker compose up -d

# 2. Run database migrations
# Migrations execute automatically on stack startup via the db-migrate service, or manually via:
python -m industrial_reliability.migrations --database-url postgresql://irp:irp_password@localhost:5432/irp --path db/migrations
```

### Verified Service Endpoints (Localhost Only):
- **FastAPI Control & Scoring API:** `http://127.0.0.1:8000` (Docs: `http://127.0.0.1:8000/docs`, Metrics: `http://127.0.0.1:8000/metrics`)
- **Operator Console Web UI:** `http://127.0.0.1:3000`
- **Prometheus Metrics Engine:** `http://127.0.0.1:9090`
- **Grafana Observability Dashboards:** `http://127.0.0.1:3001` (Dashboards: `irp-system`, `irp-data-quality`, `irp-model-machine`)
- **MLflow Model Registry & Tracking Server:** `http://127.0.0.1:5000`
- **PostgreSQL Database:** `127.0.0.1:5432` (`irp`/`irp_password`)
- **Kafka Message Broker:** `127.0.0.1:29092`

---

## 3. Standard Operational Procedures

### A. Run Ordered Database Migrations (Task 11)
```bash
# Apply ordered, checksum-verified SQL migrations to PostgreSQL:
python -m industrial_reliability.migrations \
  --database-url postgresql://irp:irp_password@localhost:5432/irp \
  --path db/migrations
```

### B. Dependency-Backed Integration Test Execution (Task 10)
```powershell
# Start required integration backing services
docker compose up -d postgres kafka db-migrate

# Set mandatory integration environment variables
$env:REQUIRE_INTEGRATION_SERVICES = "true"
$env:DATABASE_URL = "postgresql://irp:irp_password@localhost:5432/irp"
$env:KAFKA_BOOTSTRAP_SERVERS = "localhost:29092"

# Execute dependency-backed integration test suite
.\.venv\Scripts\python.exe -m pytest -m integration -v
```

### C. PostgreSQL Backup & Restore Recovery Drill (Task 11)
```powershell
# Run the automated backup, restore, and table parity recovery drill on Windows:
.\scripts\test_postgres_restore.ps1

# Or on Linux / macOS:
./scripts/test_postgres_restore.sh
```

### D. Train-Only Drift Reference Generation (Task 12)
```bash
# Build frozen drift reference distribution strictly from training features:
python -m industrial_reliability.drift build-reference \
  --manifest artifacts/champion/manifest.json \
  --features data/processed/phase1b/metropt3/features.parquet \
  --output artifacts/champion/drift-reference.json
```

### E. Phase 1C Contract-v2 Pipeline Execution (Tasks 13-14)
```powershell
# 1. Prepare raw telemetry with contract-v2 validation and split containment:
.\.venv\Scripts\python.exe -m industrial_reliability.phase1b_data \
  --archive data/raw/metropt3/metropt+3+dataset.zip \
  --output-dir data/processed/phase1c/metropt3

# 2. Extract causal window features with rejection audit logging:
.\.venv\Scripts\python.exe -m industrial_reliability.phase1b_features \
  --prepared-dir data/processed/phase1c/metropt3 \
  --output data/processed/phase1c/features.parquet

# 3. Execute offline benchmark and publish versioned metrics:
.\.venv\Scripts\python.exe -m industrial_reliability.phase1b_benchmark \
  --prepared-dir data/processed/phase1c/metropt3 \
  --features data/processed/phase1c/features.parquet \
  --artifact-dir artifacts/phase1c \
  --publish-dir docs/results/phase1c

# 4. Copy published Phase 1C evidence to root docs/results:
Copy-Item docs/results/phase1c/phase-1b-metrics.json docs/results/phase-1c-metrics.json
Copy-Item docs/results/phase1c/phase-1b-metropt3-fresh-validation.md docs/results/phase-1c-metropt3-validation.md
```

### F. Live Fault Drill Certification (Phase 8)
```powershell
# Run the 3 automated fault drills (Service Outage, Malformed Data, Machine Anomaly):
.\scripts\run_phase8_live_fault_drills.ps1
```

### G. Grounded RCA Certification Gate (Phase 9)
```powershell
# Run the Phase 9 dual-mode RCA certification gate:
.\scripts\run_phase9_live_gate.ps1
```

### H. Exact-SHA Release Certification (Task 14)
```powershell
# Certify release packaging against committed git HEAD and verified receipts:
$sha = git rev-parse HEAD
.\.venv\Scripts\python.exe -m industrial_reliability.release_certification \
  --artifact-dir "artifacts/certification/$sha" \
  --git-sha $sha
```

### I. Start Historical Telemetry Replay
```bash
# Trigger 100x speed replay for MetroPT compressor dataset
curl -X POST http://127.0.0.1:8000/v1/replays \
  -H "Content-Type: application/json" \
  -d '{"action":"START","speed":100,"range_start":"2020-04-18T00:00:00","range_end":"2020-04-18T23:59:00"}'
```

### J. Trigger & Inspect Grounded RCA
```bash
# Request Root-Cause Analysis for an open alert
curl -X POST http://127.0.0.1:8000/v1/alerts/<alert-id>/rca
```
*Note:* If `RCA_OPENAI_API_KEY` is not set, the platform immediately returns HTTP 200 `status: "UNAVAILABLE"` with all preserved evidence items without disrupting operator triage.

### K. Run Full Portfolio Demo
```powershell
# Execute the end-to-end portfolio demonstration
.\scripts\run_portfolio_demo.ps1
```

---

## 4. Troubleshooting & Alarm Responses

| Condition / Alarm | Primary Indicator | Root Cause / Remediation |
| :--- | :--- | :--- |
| **High Ingestion Quarantine Rate** | `irp_telemetry_events_total{outcome="quarantined"} > 0` | Malformed telemetry payload or schema mismatch. Inspect quarantined records in DLQ topic. |
| **Segment Break Alert** | `irp_segment_breaks_total > 0` | Timestamp gap or missing sensor readings. Streaming worker automatically resets rolling PSI and window statistics to prevent stale inference. |
| **High Feature PSI Shift ($\ge 0.2$)** | `irp_feature_psi_max >= 0.2` | Sensor input distribution drift relative to training set. Investigate physical calibration without altering anomaly detectors. |
| **Scoring API Unavailable (HTTP 503)** | `irp_dependency_health{dependency="scoring_api"} == 0` | Check scoring API container health and champion model package SHA checksum integrity. |
