# Architectural Decision Log & Production Certification

## Status
- **Protocol:** Mario E2E v4.0 (SLP Governed Edition)
- **Active Execution Mode:** Subagent-Driven Execution
- **Current Phase:** Phase 1 (Design & Sealed Analysis Completed) -> Phase 2 Transition
- **Lead Project Acceptance:** APPROVED ✅ (100% Phase 0-6 Evidence Verified)

---

## Decisions Record

### ADR-001: Execution Engine Selection
- **Context:** User presented 14 TDD tasks and 87 steps from remediation plan with options: Subagent-Driven vs Inline.
- **Decision:** Activated Subagent-Driven Execution under SDLC Mario E2E v4.0 governance.
- **Rationale:** Strict separation of judgment, isolated task contexts, dedicated cross-reviewers, and non-polluted context window.

### ADR-002: Plan Scope and Boundaries
- **Context:** 14 remediation tasks across 4 Gates (Gate A: Data Correctness, Gate B: Truthful Promotion, Gate C: Durable Failure Evidence, Gate D: Database/Monitoring).
- **Decision:** Execute strictly according to `docs/superpowers/plans/2026-08-29-data-pipeline-audit-remediation.md` with fail-closed quarantine and zero mock promotion to live.

### ADR-003: Multi-Lane Sealed Council Consensus on Production Audit Blockers
- **Context:** Council convened (Architect, Skeptic, Pragmatist, Critic) to evaluate 10 production audit findings (P0-1, P0-1A, P0-2, P0-3, P1-4, P1-5, P1-5A, P1-6, P2-7, P2-8).
- **Consensus & Frozen Decisions:**
  1. **Evidence-Level Ownership (P0-1):** In-process gates hardcode `IN_PROCESS`. Dependency-backed runs require verified runtime receipts (`ProviderCallReceipt`, DB/Kafka/API checks). Release certification rejects any `simulated_components` for `INTEGRATION`/`LIVE`.
  2. **Authoritative Phase 1B Identity (P0-1A):** Exact byte-hash verification against immutable `docs/results/phase-1b-metrics.json`. Preserved negative verdict (`selected_model: null`) without retuning holdout.
  3. **Synthetic Benchmark Reclassification (P0-2):** Benchmark runner explicitly marked `SYNTHETIC` and excluded from release claims until raw-sample telemetry adapter exists.
  4. **Complete Portfolio Demo Lifecycle (P0-3):** One command owns preflight, candidate build, compose up, readiness polling, replay/alert/RCA, live Playwright, exact-SHA certification, and safe non-destructive teardown output.
  5. **Fail-Closed RCA Persistence (P1-4):** Remove `contextlib.suppress` in `api.py`. Return structured `500 RCA_PERSISTENCE_FAILED` on DB save error.
  6. **CI Capability & Live Browser (P1-5):** Install `.[dev,mlops]` in CI, require 0 skipped tests for declared capabilities, add deployed Playwright job (`test:e2e:live`).
  7. **Phase 9 Profile Shadowing (P1-5A):** Explicit target profile evaluation without early-break bug on invalid sibling files.
  8. **Documentation & CSP Hygiene (P1-6):** Add strict CSP header in `nginx.conf`. Revert unproven claims in `README.md` and `INTERVIEW_GUIDE.md` to `UNPROVEN/BLOCKED`.
- **Rationale:** Subtractive fix preferred over complex compliance frameworks. Fail-closed at all boundaries. Zero new external dependencies.

### ADR-004: Replay Recovery Audit Remediation Consensus & Project Acceptance
- **Context:** User requested execution of `docs/superpowers/plans/2026-08-30-replay-recovery-audit-remediation.md` (3 TDD tasks, 34 steps).
- **Consensus & Decisions:**
  1. **Zero-Event Crash Recovery:** Initial checkpoint stores `last_sequence=0` and `source_timestamp=None`. Inclusive range start preserved without data loss.
  2. **Terminal Status Barrier:** `resume_checkpoint` persists `COMPLETED`/`FAILED` checkpoint and publishes matching `ReplayStatusV1` event on all recovery exit paths.
  3. **Durable Control State:** `RuntimeStore.update_replay_checkpoint_state` atomically updates `state` (`PAUSED`, `RUNNING`, `STOPPED`) without mutating START `command_payload` or sequence/timestamp cursor.
  4. **Startup Invariant:** `start()` properly handles PAUSED sessions, blocking until RESUME command.
  5. **Review Verdicts:** Unanimously `APPROVED` by Code & Logic Reviewer, Security & Data Integrity Reviewer, Verification & Testing Reviewer, and Supervisor.
