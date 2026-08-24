# Phase 3 Telemetry Contract and Kafka Replay Certification Report

**Status:** Certified  
**Date:** 2026-08-24  
**Git Base Commit:** `fe86216`  
**Kafka Version:** `apache/kafka:4.0.0` (KRaft Mode, Localhost-only)  

---

## 1. Executive Summary

Phase 3 implements deterministic, versioned streaming replay of the normalized MetroPT-3 telemetry dataset through Apache Kafka. Replay is driven by explicit Kafka control commands (`START`, `PAUSE`, `RESUME`, `STOP`) and enforces temporal invariance: varying replay speeds (`1x`, `100x`, `1000x`) alters only wall-clock pacing and never modifies source timestamps, event sequences, sensor values, or deterministic message identifiers.

Delivery semantics are explicitly **at-least-once**. Downstream idempotence is guaranteed via domain-separated **UUIDv5** deterministic identifiers derived from `(namespace, kind, replay_session_id, identity)`.

---

## 2. Evidence & Invariance Certification

### 2.1 Bounded Holdout Replay Summary

| Metric | Measured Value | Requirement / Specification |
| :--- | :--- | :--- |
| **Bounded Range** | `2020-03-01T04:00:00` to `2020-03-01T04:02:00` | Inside Phase 1B Holdout (`2020-03-01T00:00:00` to `2020-09-01T04:00:00`) |
| **Event Count** | 12 rows | Exact match across speeds |
| **Speed Multipliers** | `1x`, `100x`, `1000x` | Speeds 1, 100, 1000 supported |
| **Logical Stream SHA-256 (1x)** | `06b5d3be6a2996ce89746cc79239741ecb1670fe2419fdcc3d934f928284ea68` | Matches bit-for-bit |
| **Logical Stream SHA-256 (100x)** | `06b5d3be6a2996ce89746cc79239741ecb1670fe2419fdcc3d934f928284ea68` | Matches bit-for-bit |
| **Logical Stream SHA-256 (1000x)**| `06b5d3be6a2996ce89746cc79239741ecb1670fe2419fdcc3d934f928284ea68` | Matches bit-for-bit |
| **Streams Identical** | `True` | Zero divergence across speeds |

### 2.2 Replay State Machine & Lifecycle

- **Transitions Enforced:**
  - `CREATED` $\rightarrow$ `START` $\rightarrow$ `RUNNING`
  - `RUNNING` $\rightarrow$ `PAUSE` $\rightarrow$ `PAUSED`
  - `PAUSED` $\rightarrow$ `RESUME` $\rightarrow$ `RUNNING`
  - `RUNNING` / `PAUSED` $\rightarrow$ `STOP` $\rightarrow$ `STOPPED`
  - Stream Exhaustion $\rightarrow$ `COMPLETED`
- **Concurrency Protection:** A second `START` received while a session is active is rejected immediately with `REPLAY_ALREADY_ACTIVE` and publishes status `state="FAILED"`.
- **Quarantine Handling:** Unparseable payloads or invalid schemas emit a metadata-only `QuarantineRecordV1` to `irp.quarantine.v1` containing SHA-256 hashes and partition/offset coordinates without leaking raw payload bytes.

---

## 3. Kafka Topology & Contracts

| Topic Name | Message Schema | Keying Strategy |
| :--- | :--- | :--- |
| `irp.replay.commands.v1` | `ReplayCommandV1` | `command_id` |
| `irp.replay.status.v1` | `ReplayStatusV1` | `replay_session_id` |
| `irp.telemetry.v1` | `TelemetryEventV1` | `machine_id` |
| `irp.features.v1` | `FeatureVectorV1` | `window_id` (Phase 4) |
| `irp.scores.v1` | `ScoreDecisionV1` | `decision_id` (Phase 4) |
| `irp.quarantine.v1` | `QuarantineRecordV1` | `payload_sha256` |

---

## 4. Operational Boundaries & Limitations

1. **At-Least-Once Delivery**: Network partitions or consumer restarts may replay messages. Downstream consumers must utilize the deterministic `message_id` or `(replay_session_id, sequence)` for deduplication.
2. **Local Isolation**: Kafka is configured in KRaft single-node mode, binding strictly to `127.0.0.1:29092`. No external or unsecured network ports are opened.
3. **Parquet Source of Truth**: The telemetry source remains raw Parquet; raw sensor data is never duplicated into relational persistence.
