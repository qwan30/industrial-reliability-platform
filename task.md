# SDLC Mario E2E v3.1: Phase 9 Grounded RCA Execution Board

**Project:** Industrial Reliability Intelligence Platform  
**Target:** Phase 9 Grounded Root-Cause Analysis (RCA)  
**Plan:** `docs/superpowers/plans/2026-08-24-phase-9-grounded-rca.md`  
**Status:** In Progress — Phase 0: Research, Codebase Scan & Bounty Hunt

---

## SDLC Phase Tracking

- [/] **Phase 0: Web-First Research, Codebase Scan & Bounty Hunt**
  - [x] Tool availability preflight & context budget check (`context-budget`)
  - [ ] Research OpenAI SDK structured outputs (`responses.parse` / `chat.completions.parse`), citation schemas, and evidence minimization (`search-first`, `research-ops`)
  - [ ] Codebase onboarding on Phase 5 persistence, Phase 7 model provenance, and Phase 6 frontend (`codebase-onboarding`, `repo-scan`)
  - [ ] Security bounty hunt on API keys, data minimization, prompt injection, and path traversal (`security-bounty-hunter`)

- [ ] **Phase 1: Design, Plan & Schedule Review**
  - [ ] Product feasibility verification (`product-lens`)
  - [ ] 4-Voice Council debate & anti-anchoring synthesis (`council`: Architect, Skeptic, Pragmatist, Critic)
  - [ ] 5-Task TDD decomposition & scheduling (`plan-orchestrate`, `production-scheduling`)
  - [ ] Independent Design Reviewer approval (`design-reviewer`)

- [ ] **Phase 2: Sandbox Workspace Setup**
  - [ ] Branch creation & worktree verification (`using-git-worktrees`: branch `feat/phase-9-grounded-rca`)
  - [ ] Baseline test & coverage verification (314 passed, 86.72% coverage)

- [ ] **Phase 3: Parallel TDD Execution & 3-Reviewer Guard**
  - [ ] Task 1: Add citation-enforced RCA message contracts (`src/industrial_reliability/runtime_messages.py`, `tests/test_runtime_messages.py`)
  - [ ] Task 2: Gather a canonical bundle through four allowlisted evidence tools (`src/industrial_reliability/rca_evidence.py`, `tests/test_rca_evidence.py`)
  - [ ] Task 3: Call one provider and fail safely to evidence-only output (`pyproject.toml`, `.env.example`, `src/industrial_reliability/rca_openai.py`, `tests/test_rca_openai.py`)
  - [ ] Task 4: Persist idempotent reports and expose the alert RCA route (`db/migrations/003_rca_reports.sql`, `src/industrial_reliability/persistence.py`, `src/industrial_reliability/api.py`, `tests/integration/test_rca_persistence.py`, `tests/test_rca_api.py`)
  - [ ] Task 5: Add the operator RCA panel and certify complete/fallback paths (`apps/operator-console/...`, `src/industrial_reliability/phase9_gate.py`, `tests/test_phase9_gate.py`, `docs/results/phase-9-grounded-rca.*`)
  - [ ] 3-Reviewer Guard: Logic Reviewer, Security Reviewer, Performance Reviewer

- [ ] **Phase 4: Dual Adversarial Verification (Santa Method)**
  - [ ] Santa Reviewer B (Citation Integrity & Evidence Grounding Guard)
  - [ ] Santa Reviewer C (Secret Scrubbing & Data Minimization Guard)
  - [ ] Additional Reviewer D (Graceful Degradation & Schema Guard)
  - [ ] Additional Reviewer E (Gate Certification & Playwright E2E Guard)
  - [ ] Convergence Gate: All reviewers pass -> `NICE`

- [ ] **Phase 5: QA/QC Testing & Production Audit**
  - [ ] QA/QC Tester evaluation & complete/fallback paths verification
  - [ ] Frontend unit tests & Playwright real-click E2E verification
  - [ ] Local production audit (`production-audit`) & Canary check (`canary-watch`)
  - [ ] Token usage & cost tracking report (`cost-tracking`)

- [ ] **Phase 6: CI/CD Verification Loop & Release Certification**
  - [ ] Local verification gate (Ruff, Mypy strict, Pytest >= 80% branch coverage, pip check, python build)
  - [ ] Push to release branch & CI verification loop
  - [ ] Final certification & PR release readiness
