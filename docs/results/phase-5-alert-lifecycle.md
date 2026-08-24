# Phase 5: Alert Lifecycle & Persistence Certification

**Date:** 2026-08-24  
**Pipeline:** Industrial Reliability Platform  
**Target:** Phase 5 Alert Lifecycle & Persistence  
**Status:** Certified & Feasible

---

## 1. Upstream Provenance Chain

```
Phase 1B Validation (149e164748522fe6dfa844a8de70b29ee1259122962e036ff6a563c1120047d8)
     │
     ▼
Phase 2 Champion Package & Scoring API (champion-statistical-v1)
     │
     ▼
Phase 3 Telemetry Contract & Kafka Replay (stream_identical: True)
     │
     ▼
Phase 4 Online Feature & Scoring Worker (exact parity at 1e-12)
     │
     ▼
Phase 5 Alert Lifecycle & Persistence (locked calibration policy + atomic PostgreSQL outbox)
```

- **Source Dataset SHA-256**: `aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a`
- **Contract SHA-256**: `149e164748522fe6dfa844a8de70b29ee1259122962e036ff6a563c1120047d8`
- **Champion Model Version**: `champion-statistical-v1`

---

## 2. Alert Policy Calibration & Locking

- **Calibration Data Source**: Hashed Phase 1B champion scores filtered strictly to `split == "calibration"`.
- **Predeclared Candidate Grid**:
  - `persistence_decisions` $\in \{1, 2, 3\}$
  - `cooldown_decisions` $\in \{1, 2, 3, 6\}$
  - `merge_gap_seconds` $\in \{0, 300, 900\}$
- **Calibration Criteria**: False episodes per day $\le 1.0$ and time in alert $\le 5\%$.
- **Temporal Isolation**: Holdout observations are strictly excluded; policy is locked with immutable SHA-256 before replay.

---

## 3. State Machine & Lifecycle Transitions

| Current State | Input Decision | Policy Condition | Emitted Action | Next State |
| :--- | :--- | :--- | :--- | :--- |
| **NORMAL** | Anomaly | Streak $\ge$ Persistence (no merge) | `OPENED` | **OPEN** |
| **NORMAL** | Anomaly | Streak $\ge$ Persistence (within merge gap) | `REOPENED` | **OPEN** |
| **OPEN** | Anomaly | Any subsequent anomaly | `UPDATED` | **OPEN** |
| **OPEN** | Normal | Streak $\ge$ Cooldown | `RESOLVED` | **NORMAL** |
| **Duplicate** | Exact Decision ID | Repeated replay | None (no-op) | Unchanged |

---

## 4. Atomic PostgreSQL Persistence & Transactional Outbox

1. **Transactional Integrity**: `record_decision_transition` writes score decision, alert state transition, evidence snapshot, and alert outbox record within a single ACID transaction.
2. **Idempotence**: SQL primary keys and unique constraints (`ON CONFLICT DO NOTHING`) ensure repeated deliveries produce zero duplicate records.
3. **Outbox Dispatcher**: Asynchronous dispatcher polls unpublished outbox rows, transmits `AlertEventV1` to `irp.alerts.v1`, and marks rows published upon delivery acknowledgement.
4. **Read Surface**: FastAPI endpoints expose `GET /v1/replays/{id}`, `GET /v1/replays/{id}/alerts`, and `GET /v1/alerts/{id}` with full correlation traceability `replay_session_id -> window_id -> decision_id -> alert_id`.
