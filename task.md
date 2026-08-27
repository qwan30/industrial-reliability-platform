# Multi-Agent SDLC Task Plan: Interview Readiness Hardening Remediation (Mario E2E v3.1)

## Phase 0: Web-First Research & Scan
- [x] Analyze 4 Critical, 6 Important, 2 Minor review findings
- [x] Inspect existing code implementations, test suites, and review report
- [x] Map exact files, dependencies, and root causes

## Phase 1: Design, Plan & Schedule
- [x] Formulate remediation architecture and fail-closed validation rules
- [x] Review by Council / Architect / Planner / Domain Experts
- [x] Complete Design Reviewer validation
- [x] User instruction strictly followed (100% findings addressed, zero extras)

## Phase 2: Sandbox & Workspace
- [x] Active working branch: `fix/interview-readiness-hardening`
- [x] Isolated verification environment ready

## Phase 3: TDD Execution (Supervised by Reviewer Sub-Agents)
- [x] Task 1 (C1 & C2): Fix Phase 8 & Phase 9 Evidence Truthfulness (default to `IN_PROCESS`, prevent simulated mock promotion to `LIVE`)
- [x] Task 2 (C3 & I6): Fix Release Certification Semantic Validation & Non-Destructive Output (verify non-empty drills/checks, required checks per mode, immutable Phase 1B models matrix, default output to `<artifact_dir>/release-certification.json`)
- [x] Task 3 (C4 & I5): Harden Preflight & Portfolio Demo Runner Lifecycle (update port topology to 5173/29092/8000/5432/9090/3001/5000, add Docker/data/package checks, assert `$LASTEXITCODE -eq 0`, copy Phase 1B metrics, verify `is_certified -eq $true`)
- [x] Task 4 (I1): Harden Replay Benchmark Raw Samples & Workload Execution (frozen workload config, raw sample dataclass, deterministic percentiles, aggregations, self-hash)
- [x] Task 5 (I2 & I3): Fix Integration CI Kafka Service & Playwright Dual-Project Separation (Kafka container in CI, fail-closed `REQUIRE_INTEGRATION_SERVICES`, distinct mocked/live Playwright projects)
- [x] Task 6 (I4, M1, M2): Align Documentation Claims & Whitespace Linting (truthful evidence claims, repo-relative paths, clean whitespace across all files)

## Phase 4: Adversarial Review & Debugging Control
- [x] Santa Method Adversarial Review & Quality Verification
- [x] CodeHealth & Linting Checks (`ruff check .`, `ruff format --check .`, `git diff --check`)
- [x] Static Type Checking Gate (`mypy src` passed across all 54 source files)
- [x] Bug-Hunter Triage & Test Stability Gate

## Phase 5: QA/QC, Playwright E2E & Production Audit
- [x] Frontend Unit & Component Tests (45/45 passed in Vitest)
- [x] Operator Console Production Build (`tsc && vite build` passed)
- [x] Python Unit Test Suite (447 passed, 4 skipped, 86.34% coverage > 80% threshold)
- [x] Python Distribution Build (`python -m build` passed, sdist & wheel generated)

## Phase 6: CI/CD Verification Loop & Release Certification
- [x] Local Test Suite Execution (Unit, Ruff, Mypy, Vitest, Vite Build, Package Build)
- [x] Fail-Closed Verification before completion
- [x] Final Production Certification Verdict Report Ready
