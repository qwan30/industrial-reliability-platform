# Architecture Decision Record: Airflow NOT ADOPTED (Phase 7A)

**Status:** `NOT_ADOPTED`  
**Date:** 2026-08-24 / 2026-08-25  
**Deciders:** Lead Architect, Pragmatist, Skeptic, Critic  
**Technical Scope:** ML Workflow Orchestration & Scheduled Execution

---

## Context & Problem Statement

The Industrial Reliability Platform requires reproducible ML training, candidate reproduction, model artifact packaging, and explicit champion promotion. We evaluated whether introducing Apache Airflow into the architecture provides net operational or functional benefit.

---

## Decision: NOT ADOPTED

We have decided **NOT** to adopt Apache Airflow in the Industrial Reliability Platform architecture.

### Key Rationale & Evidence:
1. **Zero Recurring / Scheduled Workflows:** The platform operates strictly with 0 approved recurring workflows and 0 scheduled batch tasks.
2. **Explicit Human-Gated Promotion:** Model candidate promotion is an explicit, human-authorized CLI command (`python -m industrial_reliability.ml_lifecycle promote ...`) that verifies cryptographic checksums before assigning the `champion` alias. It is never autonomous or cron-triggered.
3. **MLflow Sufficiency:** MLflow 3.x with PostgreSQL backend store provides complete parameter tracking, artifact management, and model registry aliases without requiring an external DAG scheduler.
4. **Operational Bloat Prevention (Ponytail Principle):** Introducing Apache Airflow would require:
   - Dedicated webserver, scheduler, triggerer, and worker containers;
   - An independent Celery/LocalExecutor metadata database;
   - DAG directory maintenance and serialization overhead;
   - Significant memory consumption ($\sim 1.5$–$2$ GB RSS) on local operator workstations.
5. **No Speculative Automation:** Introducing scheduling infrastructure before recurring workloads exist violates the principle of evidence-based architectural evolution.

---

## Reconsideration Trigger

This decision is bound to the exact roadmap spec SHA and Phase 7 reproducibility gate. Airflow will only be reconsidered if:
1. An approved, recurring offline retraining or batch scoring workflow is formally specified and approved through a design review;
2. Measured orchestration complexity (e.g. cross-DAG dependencies, distributed dynamic scheduling) exceeds what can be handled by standard job runners or lightweight task queues.
