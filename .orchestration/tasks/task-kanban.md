# 📋 Task Kanban Board — Code & Replay Audit Remediation

## 📊 Summary
- **Total Tasks:** 10
- **Pending:** 1
- **In Progress:** 0
- **Under Review:** 0
- **Completed:** 9

---

## 📋 Task List

### Replay Recovery Subsystem (Task 1)
- [x] **TASK-001 (Replay Subplan)**: Execute replay recovery subplan (Lossless zero-event crash recovery, terminal status, durable PAUSE/RESUME/STOP) (`replay_service.py`, `persistence.py`, `test_replay_service.py`, `test_kafka_replay.py`) - Commits: `a63e589`, `2c35e1e`, `f3edbf4`

### Data, Contract & Package Identity (Tasks 2–4)
- [x] **TASK-002**: Separate immutable Phase 1B identity from executable Phase 1C (`phase1b_contracts.py`, `phase1b_data.py`, `phase1b_features.py`, `phase1b_benchmark.py`, `replay.py`, `compose.yaml`) - Commit: `f25affb`
- [x] **TASK-003**: Version champion package schema to `champion-package-v2` (`package_champion.py`, `package_research_candidate.py`, `champion.py`, `scripts/build_research_candidate.ps1`) - Commit: `1855c5e`
- [x] **TASK-004**: Anchor prepared Parquet verification to caller-supplied identity (`artifact_integrity.py`, `replay.py`, `replay_service.py`, `compose.yaml`) - Commit: `babc398`

### Reproducible ML Lifecycle & Promotion (Tasks 5–6)
- [x] **TASK-005**: Verify child artifacts before `joblib.load` and log PyFunc under candidate run (`ml_lifecycle.py`) - Commit: `cc11a33`
- [x] **TASK-006**: Validate mutable candidate run tags against pre-promotion attestation (`ml_lifecycle.py`) - Commit: `763ee22`

### State Resilience & Monitoring (Tasks 7–8)
- [x] **TASK-007**: Backfill and lazily persist missing alert runtime state (`persistence.py`) - Commit: `083e361`
- [x] **TASK-008**: Bind worker drift reference and active feature names to scoring package (`drift.py`, `worker.py`, `metrics.py`) - Commit: `e6c1a93`

### Certification & Repository Verification (Tasks 9–10)
- [x] **TASK-009**: Close residual audit defects (certification dependency receipts, CI workflow, trailing whitespace) (`release_certification.py`, `.github/workflows/ci.yml`, `docs/results/`) - Commit: `cb1e20e`
- [ ] **TASK-010**: Full repository verification, documentation proof, and portfolio demo execution
