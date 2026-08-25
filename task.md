# SDLC Mario E2E v3.1: Evidence-Led Production AI Remediation Board

**Project:** Industrial Reliability Intelligence Platform  
**Target:** Negative-Research Production AI Remediation & Exact-SHA Certification  
**Plan:** `docs/superpowers/plans/2026-08-25-evidence-led-production-ai-remediation.md`  
**Execution Mode:** Subagent-Driven Squad Orchestration (SDLC Mario E2E + Subagent-Driven Development)  
**Status:** In Progress — Phase 0: Research, Codebase Scan & Bounty Hunt

---

## Team & Agent Squad Roster

| Role / Agent Name | Type | Assigned Domain | Responsibilities |
|---|---|---|---|
| **Lead Conductor / Orchestrator** | Conductor | System Orchestration | Flow management, gate control, progress ledger, task dispatching |
| **Research Subagent** | Specialist | External & OSS Research | Web search, best practices, reference patterns (`search-first`, `research-ops`) |
| **Security Bounty Hunter** | Specialist | Security Audit | API key leakage prevention, prompt injection, path traversal, data minimization |
| **Architect & Planner** | Specialist | Design & Architecture | System boundaries, role gating, exact-SHA certification structure |
| **Council of Experts** | Multi-Voice | Decision Review | 4-Voice debate (Architect, Skeptic, Pragmatist, Critic) |
| **Design Reviewer** | Specialist | Spec & Plan Approval | Independent review and formal sign-off of Phase 1 design |
| **TDD Coder Subagent** | Executor | Implementation | Red-Green-Refactor, writing failing tests first, minimal implementation |
| **Logic Reviewer** | Reviewer 1 | Correctness & Contract | Interface compliance, schema validity, edge-case coverage |
| **Security Reviewer** | Reviewer 2 | Security & Privacy | No raw keys, secret scrubbing, fail-closed boundaries |
| **Performance Reviewer** | Reviewer 3 | Concurrency & Stability | Async I/O, resource cleanup, process lifecycle, Kafka pump stability |
| **Santa Method Reviewer B** | Adversarial 1 | Citation & Evidence Grounding | Strict verification of RCA citations and non-causal claims |
| **Santa Method Reviewer C** | Adversarial 2 | Secret Scrubbing & Data Minimization | Verification of zero secret leakage in logs, reports, and payloads |
| **QA/QC Tester Subagent** | Specialist | Acceptance & Verification | End-to-end user journey validation, report verification, test cases |
| **E2E Playwright Runner** | Specialist | UI Automation | Real browser click/input execution against operator console |
| **CI/CD Build Error Resolver**| Specialist | Build & Integration | CI verification loop, targeted error log extraction, final release check |

---

## SDLC Mario E2E Phase Tracking

### Phase 0: Web-First Research, Codebase Scan & Bounty Hunt
- [x] Tool availability preflight & context budget check (`context-budget`)
- [x] Research Kafka command/status bridging in FastAPI + AIOKafka (`search-first`, `research-ops`)
- [x] Codebase scan: audit `ml_lifecycle.py`, `package_champion.py`, `persistence.py`, `api.py`, `worker.py` (`codebase-onboarding`, `repo-scan`)
- [x] Security bounty hunt: API key leak prevention, secret revocation verification, SQLi/SSRF/path traversal check (`security-bounty-hunter`)

### Phase 1: Design, Plan & Schedule Review
- [x] Product feasibility & diagnostic validation (`product-lens`)
- [x] 4-Voice Council debate (`council`: Architect, Skeptic, Pragmatist, Critic)
- [x] 8-Task TDD Kanban scheduling & boundary definition (`team-agent-orchestration`, `production-scheduling`)
- [x] Independent Design Reviewer sign-off (`design-reviewer`)

### Phase 2: Sandbox Workspace Setup
- [x] Worktree isolation check (`using-git-worktrees`: active branch `feat/phase-9-grounded-rca`)
- [x] Baseline test & coverage verification (372 passed, 87.38% branch coverage)

### Phase 3: Parallel Subagent-Driven TDD Execution (3 Reviewers + 1 Orchestrator)
- [x] **Task 1:** Restore CI and freeze evidence vocabulary (`src/industrial_reliability/ml_lifecycle.py`, `fault_report.py`, `phase9_gate.py`) - Commit `3ad6c40`
- [x] **Task 2:** Build and gate a research-only scoring package (`src/industrial_reliability/package_research_candidate.py`, `champion.py`, `package_champion.py`, `worker.py`, `api.py`, `scripts/build_research_candidate.ps1`) - Commit `f6086d0`
- [x] **Task 3:** Wire replay commands and console events to real Kafka (`src/industrial_reliability/runtime_kafka.py`, `api.py`, `persistence.py`, `tests/test_runtime_kafka.py`) - Commit `5d66a49`
- [x] **Task 4:** Run alert lifecycle and outbox as a real service (`src/industrial_reliability/alert_service.py`, `alert_policy.py`, `db/migrations/003_rca_reports.sql`, `compose.yaml`) - Commit `734abc8`
- [x] **Task 5:** Replace Phase 8 mock certification with three live fault drills (`src/industrial_reliability/phase8_live_gate.py`, `scripts/run_phase8_live_fault_drills.ps1`, `tests/test_phase8_live_gate.py`) - Commit `8763206`
- [x] **Task 6:** Separate Phase 9 fallback evidence from live OpenAI evidence (`src/industrial_reliability/phase9_live_gate.py`, `scripts/run_phase9_live_gate.ps1`, `tests/test_phase9_live_gate.py`) - Commit `9deec5a`
- [x] **Task 7:** Make release certification exact-SHA and fail closed (`src/industrial_reliability/release_certification.py`, `package_release.py`, `tests/test_release_certification.py`) - Commit `cd8c0d9`
- [x] **Task 8:** Align portfolio demo, documentation, and Business Review deck (`README.md`, `docs/RUNBOOK.md`, `docs/MODEL_CARD.md`, `docs/ARCHITECTURE_DIAGRAMS.md`, `scripts/run_portfolio_demo.ps1`, `apps/operator-console/e2e/operator-console.live.spec.ts`) - Commit `a597388`

### Phase 4: Dual Adversarial Verification (Santa Method + CodeHealth + 2 Extra Reviewers)
- [x] Santa Reviewer A (Security, Fail-Closed & Cryptographic Lineage) - PASSED
- [x] Santa Reviewer B (Citation Integrity & Evidence Grounding) - PASSED
- [x] Santa Reviewer C (Architecture & Localhost Safety) - PASSED
- [x] CodeHealth MCP & Regression Audit - PASSED
- [x] Extra Reviewer D (Graceful Degradation & Exact-SHA Certification) - PASSED
- [x] Extra Reviewer E (Playwright E2E & Local Stack Compatibility) - PASSED
- [x] Convergence Gate: All 5 reviewers pass -> `NICE`

### Phase 5: QA/QC Testing & Production Audit
- [x] QA/QC Tester evaluation on all 8 deliverables
- [x] Playwright E2E live UI verification test suite
- [x] Production audit (`production-audit`) & Canary verification (`canary-watch`)
- [x] Token usage & cost tracking summary (`cost-tracking`)

### Phase 6: CI/CD Verification Loop & Final Release Certification
- [x] Full local gate verification (Ruff clean, Mypy strict clean, Pytest 406/406 passing, formatting clean)
- [x] Git commit history check & exact-SHA verification (`e45474a`)
- [x] Final certification sign-off

---

## Post-Review Defect Remediation Loop (`orch-fix-defect`)

- [x] **Defect 1 [P1]:** Replace fabricated Phase 8 live drills with real execution and metric measurement (`src/industrial_reliability/phase8_live_gate.py`, `tests/test_phase8_live_gate.py`) - PASSED
- [x] **Defect 2 [P1]:** Preserve holdout isolation in alert policy selection (`src/industrial_reliability/alert_policy.py`, `tests/test_alert_policy.py`) - PASSED
- [x] **Defect 3 [P1]:** Reject replay commands (HTTP 503) when Kafka producer is unavailable & add Kafka to Compose scoring-api (`src/industrial_reliability/api.py`, `compose.yaml`, `tests/test_api.py`) - PASSED
- [x] **Defect 4 [P1]:** Verify policy self-hash before controlling alert decisions (`src/industrial_reliability/alert_policy.py`, `src/industrial_reliability/alert_service.py`, `tests/test_alert_service.py`) - PASSED
- [x] **Defect 5 [P2]:** Do not commit partition offsets on `SESSION_FAILED` score decisions (`src/industrial_reliability/alert_service.py`, `tests/test_alert_service.py`) - PASSED
