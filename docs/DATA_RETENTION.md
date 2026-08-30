# Data Retention Policy

## 1. Overview & Policy State

- **Policy State:** `RETAIN_UNTIL_MANUAL_APPROVAL`
- **Scope:** Raw telemetry datasets, prepared parquet partitions, model weights/manifests, PostgreSQL transactional tables, and Kafka replay event streams.

Under the `RETAIN_UNTIL_MANUAL_APPROVAL` policy state, no automated truncation, pruning, or background vacuum-deletion is permitted on operational or audit tables without explicit, signed manual administrator approval.

---

## 2. Retention Invariants by Tier

### Tier 1: Raw Datasets & Prepared Artifacts
- Raw UCI MetroPT-3 archives and prepared Parquet datasets (`data/processed/phase1b/metropt3/`) are strictly immutable.
- Checksums (SHA-256) are calculated and validated at all offline and online boundaries via `src/industrial_reliability/artifact_integrity.py`.
- Files in this tier are never deleted automatically.

### Tier 2: Model Artifacts & MLflow Registry
- Champion and candidate model binaries, configuration manifests, and evaluation summaries stored under `artifacts/` and `mlflow-artifacts` are retained indefinitely.
- Manifest hashes must match cryptographic records before any inference service consumes them.

### Tier 3: PostgreSQL Runtime & Audit Store
- All transactional tables (`replay_sessions`, `score_decisions`, `alerts`, `alert_events`, `evidence_snapshots`, `alert_outbox`, `console_events`, `rca_reports`, `alert_runtime_states`, `replay_checkpoints`, `schema_migrations`) remain on persistent Docker volumes (`postgres-data`).
- Schema migrations tracked in `schema_migrations` are append-only and immutable.

### Tier 4: Kafka Broker Streams
- Kafka event logs (`irp.telemetry.v1`, `irp.decisions.v1`, `irp.alerts.v1`, `irp.console.v1`) remain persisted to `kafka-data` volumes for historical replay auditability.

---

## 3. Safe Pruning & Archival Safeguards

Any future deletion or archival process must satisfy the following mandatory safeguards:
1. **Dry-Run Capability:** Must support a non-destructive preview indicating exact row counts and storage bytes targeted.
2. **Explicit Date Bounds:** Must require explicit UTC `range_start` and `range_end` parameters; wildcards or unbounded queries are prohibited.
3. **Pre-Deletion Backup Verification:** An automated PostgreSQL dump/restore verification drill (via `scripts/test_postgres_restore.ps1` / `scripts/test_postgres_restore.sh`) must execute and pass before deletion begins.
4. **Durable Audit Receipt:** A signed cryptographic record detailing the scope, operator identity, timestamp, and row count differences must be permanently emitted to the audit log.
