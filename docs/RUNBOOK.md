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

### A. Start Historical Telemetry Replay
```bash
# Trigger 100x speed replay for MetroPT compressor dataset
curl -X POST http://127.0.0.1:8000/v1/replays \
  -H "Content-Type: application/json" \
  -d '{"action":"START","speed":100,"range_start":"2020-04-18T00:00:00","range_end":"2020-04-18T23:59:00"}'
```

### B. Trigger & Inspect Grounded RCA
```bash
# Request Root-Cause Analysis for an open alert
curl -X POST http://127.0.0.1:8000/v1/alerts/<alert-id>/rca
```
*Note:* If `RCA_OPENAI_API_KEY` is not set, the platform immediately returns HTTP 200 `status: "UNAVAILABLE"` with all preserved evidence items without disrupting operator triage.

### C. Execute Fault Drill Certification
```powershell
# Run the 3 automated fault drills (Service, Data, Machine)
.\scripts\run_phase8_live_fault_drills.ps1
```

### D. Execute Grounded RCA Gate
```powershell
# Run the Phase 9 RCA certification gate (in-process contract checks)
.\scripts\run_phase9_live_gate.ps1
```

### E. Run Full Portfolio Demo
```powershell
# Execute the end-to-end portfolio demonstration
.\scripts\run_portfolio_demo.ps1
```

### F. Execute PostgreSQL Backup & Restore Recovery Drill
```powershell
# Run the automated backup, restore, and table parity recovery drill
.\scripts\test_postgres_restore.ps1

# Or on Linux / macOS:
./scripts/test_postgres_restore.sh
```

---

## 4. Troubleshooting & Alarm Responses

| Condition / Alarm | Primary Indicator | Root Cause / Remediation |
| :--- | :--- | :--- |
| **High Ingestion Quarantine Rate** | `irp_telemetry_events_total{outcome="quarantined"} > 0` | Malformed telemetry payload or schema mismatch. Inspect quarantined records in DLQ topic. |
| **Segment Break Alert** | `irp_segment_breaks_total > 0` | Timestamp gap or missing sensor readings. Streaming worker automatically resets rolling PSI and window statistics to prevent stale inference. |
| **High Feature PSI Shift ($\ge 0.2$)** | `irp_feature_psi_max >= 0.2` | Sensor input distribution drift relative to training set. Investigate physical calibration without altering anomaly detectors. |
| **Scoring API Unavailable (HTTP 503)** | `irp_dependency_health{dependency="scoring_api"} == 0` | Check scoring API container health and champion model package SHA checksum integrity. |
