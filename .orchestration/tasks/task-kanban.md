# SDLC Mario E2E Task Kanban

**Governing Plan:** `docs/superpowers/plans/2026-08-29-data-pipeline-audit-remediation.md`

## 📊 Summary
- **Total Tasks:** 14
- **Pending:** 0
- **In Progress:** 0
- **Under Review:** 0
- **Completed:** 14

---

## 📋 Task List

### Gate A: Data Correctness & Identity (COMPLETED ✅)
- [x] **TASK-001**: Persist pre-alert state transactionally (`db/migrations/004_alert_runtime_state.sql`, `persistence.py`) - Commit: `b27f4ea`
- [x] **TASK-002**: Add one shared artifact-integrity verifier (`src/industrial_reliability/artifact_integrity.py`) - Commit: `002a073`
- [x] **TASK-003**: Enforce integrity at offline boundaries (`phase1b_features.py`, `phase1b_benchmark.py`, `ml_lifecycle.py`, `package_champion.py`) - Commit: `95c2e3f`
- [x] **TASK-004**: Bind replay and worker identity to verified source bytes (`replay.py`, `replay_service.py`, `worker.py`, `compose.yaml`) - Commit: `67d80f6`
- [x] **TASK-005**: Persist replay checkpoints before committing START (`persistence.py`, `replay_service.py`, `compose.yaml`) - Commit: `4401446`
- [x] **TASK-006**: Enforce full-window split containment (`phase1b_features.py`, `phase1b_data.py`) - Commit: `557a1f4`

### Gate B: Truthful ML Promotion & Certification (COMPLETED ✅)
- [x] **TASK-007**: Turn Phase 7 into a pre-promotion attestation (`phase7_gate.py`, `ml_lifecycle.py`) - Commit: `ad2e33f`
- [x] **TASK-008**: Make evidence levels non-user-controlled (`phase8_live_gate.py`, `phase9_live_gate.py`, `release_certification.py`) - Commit: `66be78a`

### Gate C: Durable Failure Evidence & Integration Proof (COMPLETED ✅)
- [x] **TASK-009**: Quarantine malformed scores before offset commit (`alert_consumer.py`, `alert_service.py`) - Commit: `1a27219`
- [x] **TASK-010**: Add one dependency-backed critical-path test (`tests/integration/test_data_path.py`) - Commit: `ae63f00`

### Gate D: Database, Monitoring & Data Contract Operations (COMPLETED ✅)
- [x] **TASK-011**: Add repeatable migrations and a recovery drill (`src/industrial_reliability/migrations.py`, `scripts/test_postgres_restore.ps1`, `docs/DATA_RETENTION.md`) - Commit: `6a6b5a1`
- [x] **TASK-012**: Wire lag, drift identity, and Prometheus alerts (`ops/prometheus/alerts.yml`, `worker.py`, `alert_service.py`) - Commit: `9f97f87`
- [x] **TASK-013**: Version units, plausibility envelopes, and time semantics (`phase1b_contracts.py`, `runtime_messages.py`, `docs/DATA_CARD.md`) - Commit: `d20931d`
- [x] **TASK-014**: Publish versioned evidence and truthful docs (`docs/results/`, `docs/RUNBOOK.md`, `README.md`, `.github/workflows/ci.yml`) - Commit: `fa4f17b`
