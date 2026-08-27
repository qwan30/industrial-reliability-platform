# Industrial Reliability Platform — Staff Engineer Interview & Architecture Guide

This document is a technical walkthrough of the Industrial Reliability Platform, designed for technical deep-dives, architectural reviews, and staff-level systems interviews.

---

## 1. Executive Summary & Core Philosophy

The Industrial Reliability Platform is an **evidence-led, fail-closed industrial time-series intelligence platform**.

### Core Tenets:
1. **Evidence-Led Negative Research:** When statistical and machine learning models failed to clear predeclared operational feasibility bars on the frozen MetroPT compressor holdout dataset, the system recorded `selected_model: null` and `NOT FEASIBLE`. It explicitly refuses to claim a production champion where none exists.
2. **Deterministic Contract Envelopes:** All streaming telemetry, feature vectors, score decisions, and alert transitions use immutable JSON message contracts validated by SHA-256 schema hashes.
3. **Closed-World Grounded RCA:** Root-Cause Analysis (RCA) operates on allowlisted projection tools with cryptographic citation verification. It never receives raw telemetry rows and never invents un-grounded claims.
4. **Fail-Closed Release Certification:** Certification reports require exact 40-character Git SHA binding, SHA-256 self-hashes, and gate-level evidence (`LIVE` / `INTEGRATION`). Tampering with any field immediately invalidates certification.

---

## 2. End-to-End System Architecture

```text
                                 +-------------------------+
                                 |  MetroPT Sensor Replay  |
                                 +-------------------------+
                                              |
                                              v (irp.telemetry.v1)
                                      +---------------+
                                      | Apache Kafka  |
                                      +---------------+
                                        /           \
                                       v             v
+------------------+         +------------------+   +-------------------+
| Prometheus (9090)| <-------| Streaming Worker |   |  Replay Producer  |
+------------------+         +------------------+   +-------------------+
        ^                              |
        |                      (Scoring Request)
        |                              v
        |                    +--------------------+
        |                    | FastAPI Scoring API| <--- Research Candidate
        |                    +--------------------+      (Autoencoder / Baseline)
        |                              |
        |                              v (irp.scores.v1)
        |                    +--------------------+
        +------------------- |   Alert Service    |
                             +--------------------+
                                       |
                                       +---> [PostgreSQL: alerts, events, evidence, outbox]
                                       |
                                       v (irp.alerts.v1 / outbox)
                             +--------------------+
                             |  Operator Console  | (React / Vite on :5173)
                             +--------------------+
                                       |
                                       v (POST /v1/alerts/{id}/rca)
                             +--------------------+
                             | Grounded LLM RCA   | (Allowlisted 4-tool projection)
                             +--------------------+
```

---

## 3. Key Subsystems & Design Choices

### A. Temporal Segmentation & Sliding-Window Feature Engineering
- **File:** [`src/industrial_reliability/features.py`](../src/industrial_reliability/features.py)
- **Problem:** Real-world sensor telemetry exhibits timestamp jitter, missing seconds, and clock resets. Naive rolling windows introduce temporal distortion.
- **Solution:** Stateful segmentation breaks windows whenever inter-observation delta exceeds 5 seconds. Windows require $\ge 90\%$ uniform coverage across 6 temporal sub-bins before feature extraction.

### B. Fault Isolation & Taxonomy
- **File:** [`src/industrial_reliability/fault_report.py`](../src/industrial_reliability/fault_report.py)
- **Taxonomy:**
  1. **Service Outages:** Scoring API 503/timeout $\rightarrow$ worker retries with exponential backoff and buffer preservation; 0 telemetry dropped.
  2. **Ingestion Data Faults:** Corrupted schema or negative timestamps $\rightarrow$ isolated to quarantine topic; 0 downstream scoring corruption.
  3. **Machine Faults:** Authentic sensor shift $\rightarrow$ stateful alert policy transitions (`OPENED` $\rightarrow$ `UPDATED` $\rightarrow$ `RESOLVED`).

### C. State Machine & Persisted Outbox Pattern
- **Files:** [`src/industrial_reliability/alert_state.py`](../src/industrial_reliability/alert_state.py), [`src/industrial_reliability/persistence.py`](../src/industrial_reliability/persistence.py)
- **Invariant:** Alert transitions are calculated pure-functionally (`transition(state, decision, policy)`), written transactionally alongside evidence snapshots and outbox rows in PostgreSQL, and only published after database commit.

### D. Grounded RCA with Closed-World Citations
- **Files:** [`src/industrial_reliability/rca_openai.py`](../src/industrial_reliability/rca_openai.py), [`src/industrial_reliability/rca_evidence.py`](../src/industrial_reliability/rca_evidence.py)
- **Projection Tools:** `get_alert`, `get_score_evidence`, `get_model_provenance`, `get_system_health`.
- **Enforcement:** Observations citing unknown evidence IDs are rejected. Fallback mode returns structured evidence summary with `status="UNAVAILABLE"` when API keys are omitted or providers fail.

---

## 4. Authoritative Evidence & Phase Results

| Phase | Description | Status / Verdict | Authoritative Evidence File |
|---|---|---|---|
| **Phase 1** | Offline ML Feasibility | **NOT FEASIBLE** (`selected_model: null`) | [`docs/results/phase-1-offline-ml-feasibility.md`](results/phase-1-offline-ml-feasibility.md) |
| **Phase 1B** | Benchmark on MetroPT-3 | **NOT FEASIBLE** | [`docs/results/phase-1b-metrics.json`](results/phase-1b-metrics.json) |
| **Phase 7A** | Airflow Architectural Evaluation | **NOT ADOPTED** (Kafka/Service preferred) | [`docs/decisions/2026-08-24-airflow-not-adopted.md`](decisions/2026-08-24-airflow-not-adopted.md) |
| **Phase 8** | Fault Isolation Drills | **PASS** (`IN_PROCESS` default; `INTEGRATION`/`LIVE` with live services) | `artifacts/certification/$sha/phase-8-live-fault-drills.json` |
| **Phase 9** | Grounded RCA Gate | **PASS** (`FALLBACK_ONLY` default; `LIVE` with verified provider) | `artifacts/certification/$sha/phase-9-rca-fallback.json` |
| **Release** | Exact-SHA Release Certification | **NEGATIVE_RESEARCH_RELEASE** (`is_certified: true`) | `artifacts/certification/$sha/release-certification.json` |

---

## 5. Frequently Asked Interview Questions

### Q1: Why is Phase 1 marked NOT FEASIBLE, and why is there no production champion model?
**Answer:** In industrial reliability, releasing a model that does not meet strict false alarm and detection lead-time thresholds carries severe operational costs. On the frozen MetroPT test partition, candidate models (Autoencoder, Isolation Forest, Mahalanobis) exhibited excessive false discovery rates. The platform enforces negative research honesty by locking `selected_model: null` and permitting runtime scoring exclusively via an explicit research candidate flag (`ALLOW_RESEARCH_CANDIDATE=true`).

### Q2: How does the platform prevent cascading failures when external dependencies fail?
**Answer:** The streaming worker treats external dependencies (Scoring API, PostgreSQL, Kafka) as transient failure domains. When Scoring API is down, telemetry remains queued in Kafka without dropped records. When OpenAI is unavailable, RCA falls back instantly to deterministic evidence summaries (`status: UNAVAILABLE`) so operator triage is never blocked.

### Q3: How does the operator console ensure zero styling leaks without external CSS libraries?
**Answer:** The console utilizes an explicit token-based inline styling architecture (`#1e293b` background, `#334155` border, `#f8fafc` text, `#38bdf8` citations). This eliminates production CSS runtime dependencies, guarantees consistent dark-mode operator visibility, and complies with strict CSP headers.

### Q4: How is release certification tamper-proof?
**Answer:** The certification engine hashes all input artifacts and embeds a SHA-256 self-hash over canonical JSON representations. Any modification to drill results, Git SHA, evidence levels, or verdict strings breaks the cryptographic signature and causes `ReleaseCertificationValidator` to fail closed with `verdict="INVALID"`.
