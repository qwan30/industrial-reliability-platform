# Workspace Protocol & Governance

**Framework:** SDLC Mario E2E v4.0 (SLP Governed Edition)
**Base Plan:** `docs/superpowers/plans/2026-08-29-data-pipeline-audit-remediation.md`
**Audited Baseline Commit:** `2d054c65db8ce63ff6aebbf48d472c5c0586b0fc`
**Target Environment:** Python 3.12, FastAPI, Pydantic v2, PyArrow, aiokafka, PostgreSQL 17/psycopg 3, MLflow 3, Prometheus/Grafana, Docker Compose, pytest

---

## 1. SLP Governance Topology
- **Human Owner:** Product intent, budget limits, irreversible trade-offs, production deploy/merge authority.
- **Lead (Project Authority):** Problem framing, task decomposition, dependency orchestration, Project Acceptance.
- **Peer (Bounded Outcome):** Bounded implementation & verification. Subagents dispatch per task.
- **Supervisor (Governance & Quality):** Observes execution, enforces anti-pattern triggers (S1–S9), detects context drift.

---

## 2. Hard Invariants & Technical Constraints
1. **Separation of Judgment:** Author cannot review own code. Reviews must run against a frozen Stable Candidate.
2. **Anti-Minted APIs:** Never fabricate mock contracts or APIs to force tests green.
3. **Fail Closed:** Telemetry with mismatched contract/dataset hashes must be quarantined.
4. **Promotion Truthfulness:** `RESEARCH_CANDIDATE + NOT_FEASIBLE + RESEARCH_ONLY` must never acquire MLflow `champion` alias.
5. **Coverage & Quality:** Minimum 80% branch coverage with strict Red-Green-Refactor TDD.
6. **Immutability:** Preserves existing data files, versioning artifacts under `phase1c`.

---

## 3. Subagent Dispatch & Model Routing Matrix
- **Mechanical Tasks (1-2 files, explicit specs):** Standard/Fast model.
- **Integration Tasks (Replay, Kafka, Postgres, MLflow):** Standard/Pro model.
- **Reviewers (Spec, Security, Code Quality):** Independent subagents with neutral briefs.
- **Adversarial Santa Method:** Generator vs Evaluator convergence loop.
