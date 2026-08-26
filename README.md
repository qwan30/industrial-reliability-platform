# Industrial Reliability Platform

Production-oriented industrial anomaly detection and reliability intelligence platform.

> **Status:** Phase 1 offline ML feasibility — **NOT FEASIBLE** on the frozen MetroPT holdout; no model met the predeclared gate. This is offline evidence, not production readiness. See the [aggregate Phase 1 result](docs/results/phase-1-offline-ml-feasibility.md).
> Master specification: `docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md`

## Development setup

Requires Python 3.12.

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Quality checks

The same checks CI runs on every push and pull request:

```bash
ruff check .
ruff format --check .
mypy src
pytest -m "not slow"
pip check
python -m build
```

## Project layout

```text
src/industrial_reliability/   # package source (grows with each phase)
tests/                        # test suite
docs/                         # specifications and research notes
references/                   # local-only reference repositories (git-ignored)
data/                         # local-only datasets (git-ignored)
```

## Reproducible ML Lifecycle (Phase 7)

Phase 7 brings MLflow 3.x-backed offline tracking, immutable run provenance, and fail-closed promotion gates to ensure full numerical and artifact reproducibility.

### Optional MLOps Dependencies
Install offline tracking dependencies:
```bash
pip install -e ".[mlops]"
```

### Local MLflow Server
Start the isolated localhost MLflow tracking server backed by PostgreSQL:
```bash
docker compose up -d mlflow
```
The server binds exclusively to `127.0.0.1:5000` with artifacts stored in the `mlflow-artifacts` volume.

### ML Lifecycle CLI
The platform provides three immutable lifecycle commands:

1. **Import Candidate**:
   Logs champion artifacts, contracts, schemas, and git SHA to MLflow under the `candidate` state:
   ```bash
   python -m industrial_reliability.ml_lifecycle import-candidate \
       --champion-package artifacts/champion \
       --phase1b-run-dir artifacts/phase1b/phase1b-run-6050e71c7543
   ```

2. **Reproduce Candidate**:
   Re-fits on train and evaluates on calibration partitions only (never holdout) to verify exact score matching:
   ```bash
   python -m industrial_reliability.ml_lifecycle reproduce \
       --features-path data/processed/phase1b/metropt3/features.parquet \
       --phase1b-run-dir artifacts/phase1b/phase1b-run-6050e71c7543 \
       --champion-package artifacts/champion
   ```

3. **Promote Candidate**:
   Registers the model version under alias `champion` and writes an immutable `promotion-receipt.json`:
   ```bash
   python -m industrial_reliability.ml_lifecycle promote \
       --run-id <candidate-run-id> \
       --approver "lead-reliability-engineer" \
       --expected-source-git-sha <git-sha> \
       --output artifacts/champion/promotion-receipt.json
   ```

### Reproducibility & Lineage Gate
Certifies that candidate reproduction threshold delta $\le 10^{-9}$, score delta $\le 10^{-6}$, and all artifact hashes match:
```bash
python -m industrial_reliability.phase7_gate \
    --champion-package artifacts/champion \
    --features-path data/processed/phase1b/metropt3/features.parquet \
    --phase1b-run-dir artifacts/phase1b/phase1b-run-6050e71c7543 \
    --output-dir artifacts/phase7
```

## Observability & Reliability (Phase 8)

Phase 8 provides real-time Prometheus runtime instrumentation, train-only population stability index (PSI) drift indicators, three purpose-built Grafana operator dashboards, and certified fault drills distinguishing Service Outages, Ingestion Data Faults, and Machine Faults.

### Runtime Metrics & Scrape Endpoints
Bounded metric vocabulary with strictly validated enums:
- `scoring-api:8000/metrics`: Scoring rate, p95 scoring latency (`irp_score_latency_seconds`), and outcome counters.
- `replay-producer:9101/metrics`: Telemetry emission and replay session error counters.
- `streaming-worker:9102/metrics`: Ingestion rates (`irp_telemetry_events_total`), segment breaks (`irp_segment_breaks_total`), feature window coverage ratio, anomaly score & decisions, and maximum feature PSI (`irp_feature_psi_max`).

### Prometheus & Grafana Provisioning
Start the observability stack on local isolated host bindings:
```bash
docker compose up -d prometheus grafana
```
- **Prometheus UI**: `http://127.0.0.1:9090`
- **Grafana UI**: `http://127.0.0.1:3001` (anonymous view access enabled)
  - `irp-system`: System Health, Dependency Readiness, Replay Failures, Kafka Lag.
  - `irp-data-quality`: Telemetry Accepted vs Quarantined, Segment Breaks, Window Coverage Ratio.
  - `irp-model-machine`: Scoring Request Rates, p95 Latency, Train-only Feature PSI Max, Anomaly Score & Active Alerts.

> **Operator Guidance:** *Drift is not a failure diagnosis.* A PSI shift ($\ge 0.2$) indicates input distribution change relative to training data, whereas an anomaly decision reflects detector scoring and an alert reflects locked operational policy.

### Train-Only Drift Reference Generation
```bash
python -m industrial_reliability.drift build-reference \
    --manifest artifacts/champion/manifest.json \
    --features data/processed/phase1b/metropt3/features.parquet \
    --output artifacts/champion/drift-reference.json
```

### Fault Isolation Drills Certification
Execute the certified 3-drill fault-isolation matrix:
```powershell
.\scripts\run_phase8_live_fault_drills.ps1
```
The drills execute the real streaming-worker fault-isolation logic in-process
(scoring client, Kafka producer, and metrics registry are in-process doubles),
and the reports disclose the simulated components with
`evidence_level: IN_PROCESS`. Generates cryptographically self-hashed reports at:
- `artifacts/certification/<git-sha>/phase-8-in-process-fault-drills.json`
- `artifacts/certification/<git-sha>/phase-8-in-process-fault-drills.md`

## Grounded Root-Cause Analysis (Phase 9)

Phase 9 provides closed-world, evidence-grounded anomaly explanation and Root-Cause Analysis (RCA) via direct integration with OpenAI Python SDK structured outputs (`responses.parse` / `text_format`), strict 4-tool allowlisted projection, cryptographic citation enforcement, write-once PostgreSQL persistence, and operator console UI integration.

### Evidence Projection & Closed-World Grounding
The LLM generator is strictly restricted to an allowlist of 4 projection tools:
1. `get_alert`: Alert lifecycle timeline, duration, detection bounds, and machine identifier.
2. `get_score_evidence`: Top statistical feature deviations (`tp2_mean`, `h1_std`, etc.) and baseline comparisons.
3. `get_model_provenance`: Frozen model metadata, champion package SHA-256, and promotion receipt.
4. `get_system_health`: Dependency health status, scoring queue latency, and data quality indicators.

> **Data Minimization & Security Invariants:**
> - Raw telemetry arrays/parquet rows, database connection strings, and local filesystem paths are **strictly excluded**.
> - Every observation claim must cite valid evidence IDs from the gathered bundle (`evidence-<24 hex>`). Any invented or un-grounded citation immediately triggers discard and fallback.
> - Secret isolation: `RCA_OPENAI_API_KEY` is loaded strictly in `OpenAiRcaGenerator.from_env()`, never committed, and scrubbed from all logging, repr, and metrics.
> - Mandatory non-causal disclaimer: Every report embeds *"Anomaly evidence does not prove a mechanical root cause."*

### API Endpoints
- `POST /v1/alerts/{alert_id}/rca`: Generates or retrieves cached RCA report for an alert. If credentials are missing or the provider fails, gracefully returns HTTP 200 with `status: "UNAVAILABLE"` containing all gathered evidence so operator triage is never blocked.
- `GET /v1/alerts/{alert_id}`: Retrieves alert details, associated evidence, timeline events, and attached RCA report if previously generated.

### Operator Console UI
The React operator console includes an interactive RCA panel in the alert detail drawer:
- **Generate RCA** button with real-time loading states.
- Status badges for `COMPLETE` and `UNAVAILABLE` states.
- Grounded observations linked to clickable evidence citation pills.
- Explicit non-causal uncertainty disclaimer and recommended operational next checks.

### RCA Certification Gate
Run the cryptographic Phase 9 RCA certification gate:
```powershell
.\scripts\run_phase9_live_gate.ps1
```
The gate verifies the RCA contract in-process (allowlisted projection tools,
closed-world citation enforcement, graceful provider fallback, and secret
scrubbing) and publishes `evidence_level: IN_PROCESS` reports;
`provider_mode` records whether `RCA_OPENAI_API_KEY` is configured for the
operational RCA endpoint. Generates self-hashed reports at:
- `artifacts/certification/<git-sha>/phase-9-rca-fallback.json` (or `phase-9-rca-openai.json` when `RCA_OPENAI_API_KEY` is set)
- `artifacts/certification/<git-sha>/phase-9-rca-fallback.md`

## Release Certification & Portfolio Demo

### End-to-End Live Demonstration
Execute the full live platform portfolio demonstration:
```powershell
.\scripts\run_portfolio_demo.ps1
```

### Exact-SHA Release Certification
Certify complete release packaging against committed git HEAD:
```bash
python -m industrial_reliability.release_certification --artifact-dir artifacts/certification/<git-sha> --git-sha <git-sha>
```

## License

MIT — see [LICENSE](LICENSE).


