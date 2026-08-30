# PR Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose the monolithic audit remediation changes into a dependency-ordered series of 6 focused, reviewable, and independently testable Pull Requests targeting `main`.

**Architecture:** Each PR isolates a cohesive architectural domain with strict contract boundaries, independent test coverage, and automated CI validation. The PRs build upon each other sequentially or can be managed via stacked feature branches based on `main` base commit `2d054c6`.

**Tech Stack:** Git, GitHub CLI (`gh`), Python 3.12, Pytest, Mypy, Ruff, Docker Compose, PostgreSQL 17, Apache Kafka 4.0, MLflow.

## User Review Required

> [!IMPORTANT]
> - PR #20 was previously merged into `main` to preserve the verified audit remediation state.
> - To break the work down into smaller PRs for upstream reviewers / clean git history, we will create 6 clean feature branches branching from `2d054c6` (the base commit before the monolithic remediation) or stacked sequentially.
> - Each PR will be created with its own dedicated test verification and CI run.

## PR Decomposition Matrix

| PR # | Branch Name | Title | Primary Domain | Core Files |
| :---: | :--- | :--- | :--- | :--- |
| **PR-1** | `fix/db-migrations-and-restore-drill` | `feat(db): repeatable migrations, recovery drill, and data retention policy` | Database & Storage | `migrations.py`, `004_alert_runtime_state.sql`, `test_postgres_restore.*`, `DATA_RETENTION.md`, `compose.yaml` |
| **PR-2** | `fix/sensor-contracts-and-artifact-integrity` | `fix(contracts): physical plausibility envelopes and tri-hash parquet identity` | Contracts & Data Integrity | `phase1b_contracts.py`, `phase1b_data.py`, `artifact_integrity.py`, `runtime_messages.py`, `DATA_CARD.md` |
| **PR-3** | `fix/champion-package-v2-and-features` | `feat(ml): champion package v2 schema, causal features, and phase 1c pipeline` | Feature Pipeline & Packaging | `phase1b_features.py`, `phase1b_benchmark.py`, `package_champion.py`, `package_research_candidate.py`, `champion.py`, `build_research_candidate.ps1` |
| **PR-4** | `fix/replay-recovery-and-control-persistence` | `fix(replay): lossless zero-event crash recovery, control persistence, and terminal status` | Telemetry Replay Subsystem | `replay.py`, `replay_service.py`, `persistence.py` (checkpoints), `compose.yaml` |
| **PR-5** | `fix/ml-lifecycle-attestation-and-safe-loading` | `fix(mlops): safe model deserialization and pre-promotion run tag attestation` | ML Lifecycle & Governance | `ml_lifecycle.py`, `phase7_gate.py`, `phase8_live_gate.py`, `phase9_live_gate.py` |
| **PR-6** | `fix/drift-monitoring-alerts-and-release-certification` | `fix(monitoring): alert state recovery, drift binding, prometheus alerts, and certification` | State, Monitoring & Release | `persistence.py` (state reconstruction), `alert_consumer.py`, `worker.py`, `drift.py`, `release_certification.py`, `alerts.yml`, `ci.yml` |

---

## Proposed Changes & Tasks

### Task 1: PR-1 — Repeatable Migrations, Recovery Drill & Data Retention
- **Branch:** `fix/db-migrations-and-restore-drill` (Base: `2d054c6`)
- **Key Deliverables:**
  - `src/industrial_reliability/migrations.py`
  - `db/migrations/004_alert_runtime_state.sql`
  - `scripts/test_postgres_restore.ps1`, `scripts/test_postgres_restore.sh`
  - `docs/DATA_RETENTION.md`
  - `compose.yaml` (migration service & health checks)
  - `tests/test_migrations.py`

### Task 2: PR-2 — Physical Plausibility Envelopes & Tri-Hash Parquet Identity
- **Branch:** `fix/sensor-contracts-and-artifact-integrity`
- **Key Deliverables:**
  - `src/industrial_reliability/phase1b_contracts.py` (`AnalogSignalContract`, `validate_analog_value`, `PHASE1C`)
  - `src/industrial_reliability/phase1b_data.py` (zero-clipping validation)
  - `src/industrial_reliability/artifact_integrity.py` (`verify_prepared_parquet`)
  - `src/industrial_reliability/runtime_messages.py`
  - `docs/DATA_CARD.md`
  - `tests/test_phase1b_contracts.py`, `tests/test_phase1b_data.py`, `tests/test_artifact_integrity.py`, `tests/test_runtime_messages.py`

### Task 3: PR-3 — Champion Package v2, Causal Features & Phase 1C Pipeline
- **Branch:** `fix/champion-package-v2-and-features`
- **Key Deliverables:**
  - `src/industrial_reliability/phase1b_features.py`
  - `src/industrial_reliability/phase1b_benchmark.py`
  - `src/industrial_reliability/package_champion.py` (`champion-package-v2`, `prepared_output_sha256`, non-loading `--verify-package`)
  - `src/industrial_reliability/package_research_candidate.py`
  - `src/industrial_reliability/champion.py`
  - `scripts/build_research_candidate.ps1`
  - `docs/results/phase-1c-metrics.json`, `docs/results/phase-1c-metropt3-validation.md`
  - `tests/test_phase1b_features.py`, `tests/test_phase1b_benchmark.py`, `tests/test_package_champion.py`, `tests/test_champion.py`, `tests/test_portfolio_demo_scripts.py`

### Task 4: PR-4 — Lossless Replay Recovery, Control Persistence & Terminal Status
- **Branch:** `fix/replay-recovery-and-control-persistence`
- **Key Deliverables:**
  - `src/industrial_reliability/replay.py` (range-start recovery)
  - `src/industrial_reliability/replay_service.py` (crash recovery, terminal status, PAUSE/RESUME/STOP)
  - `src/industrial_reliability/persistence.py` (durable checkpoint mutations)
  - `compose.yaml` (bind `REPLAY_PACKAGE_MANIFEST`)
  - `tests/test_replay.py`, `tests/test_replay_service.py`, `tests/integration/test_kafka_replay.py`

### Task 5: PR-5 — Safe Model Deserialization & Pre-Promotion Attestation
- **Branch:** `fix/ml-lifecycle-attestation-and-safe-loading`
- **Key Deliverables:**
  - `src/industrial_reliability/ml_lifecycle.py` (verify child artifacts before `joblib.load`, log PyFunc under run, pre-promotion 6-hash validation)
  - `src/industrial_reliability/phase7_gate.py`, `phase8_live_gate.py`, `phase9_live_gate.py`
  - `tests/test_ml_lifecycle.py`, `tests/test_phase7_gate.py`, `tests/integration/test_mlflow_candidate.py`, `tests/integration/test_mlflow_promotion.py`

### Task 6: PR-6 — Alert State Recovery, Drift Binding, Prometheus Alerts & CI Hardening
- **Branch:** `fix/drift-monitoring-alerts-and-release-certification`
- **Key Deliverables:**
  - `src/industrial_reliability/persistence.py` (`_reconstruct_alert_state`, lazy state migration)
  - `src/industrial_reliability/alert_consumer.py`, `alert_service.py`
  - `src/industrial_reliability/drift.py` (feature sequence & hash verification)
  - `src/industrial_reliability/worker.py` (consumer lag metric, drift reference binding)
  - `ops/prometheus/alerts.yml`, `ops/prometheus/prometheus.yml`, `compose.yaml`
  - `src/industrial_reliability/release_certification.py` (fail-closed on malformed receipts)
  - `.github/workflows/ci.yml` (`dev,mlops` dependencies)
  - `README.md`, `docs/RUNBOOK.md`
  - Full test suites: `tests/integration/test_data_path.py`, `tests/integration/test_alert_persistence.py`, `tests/test_drift.py`, `tests/test_worker.py`, `tests/test_prometheus_alerts.py`, `tests/test_release_certification.py`

---

## Verification Plan

### Automated Tests
- Every PR will run its isolated unit tests and full suite:
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/ -v
  .\.venv\Scripts\python.exe -m mypy src
  .\.venv\Scripts\python.exe -m ruff check .
  .\.venv\Scripts\python.exe -m ruff format --check .
  ```
- GitHub Actions CI must pass 100% green (`quality`, `integration`, `PR Agent`) for every single PR.
