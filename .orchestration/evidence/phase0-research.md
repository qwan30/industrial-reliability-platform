# Phase 0 Research & Security Scout Report: Industrial Reliability Platform

**Framework:** SDLC Mario E2E v4.0 (SLP Governed Edition)  
**Target Repository:** `industrial-reliability-platform` (FastAPI, Python 3.12, PyArrow, Kafka, PostgreSQL, Vite/React, Playwright)  
**Audited Baseline SHA:** `2d054c65db8ce63ff6aebbf48d472c5c0586b0fc`  
**Date:** 2026-08-30  

---

## 1. Executive Summary & Audit Baseline

A comprehensive static, dynamic, architectural, and security audit of the repository against `docs/superpowers/specs/2026-08-29-project-wide-production-audit.md` and `docs/superpowers/plans/2026-08-29-data-pipeline-audit-remediation.md` confirms that while the codebase possesses strong test coverage (>86%), strict Pydantic v2 schemas, and clean localhost port isolation, it currently fails production and release certification standards across 10 discrete audit findings (**P0-1, P0-1A, P0-2, P0-3, P1-4, P1-5, P1-5A, P1-6, P2-7, P2-8**).

### Core Scientific Invariant
The historical finding on MetroPT-3 remains permanently truthful and unchanged: **Phase 1B is `NOT FEASIBLE` with `selected_model: null`**. No remediation step authorizes re-running, tuning, or modifying the frozen holdout partition.

---

## 2. Project-Wide Audit Findings & Codebase Verification

| Defect ID | Severity | File Location | Root Cause & Verified Codebase State | Required Remediation Contract |
|---|---|---|---|---|
| **P0-1** | `BLOCKER` (P0) | `src/industrial_reliability/phase8_live_gate.py:111-164`<br>`src/industrial_reliability/phase9_live_gate.py:55-60, 167-174`<br>`src/industrial_reliability/release_certification.py:22, 154-186` | **Self-promoted double evidence:**<br>• Phase 8 executes in-process mock doubles (lines 103-104), but accepts `--evidence-level INTEGRATION`.<br>• Phase 9 marks `LIVE_OPENAI` and `evidence_level: LIVE` upon non-empty key presence, but checks only SDK parsing and mocks without live provider API calls or persisted alert POST/GET round trips.<br>• `release_certification.py` validates `evidence_level in {"INTEGRATION", "LIVE"}` without verifying dependency receipts or checking that `simulated_components` is empty. | 1. In-process drill gates must hardcode `evidence_level: "IN_PROCESS"` and reject user overrides.<br>2. Live/integration evidence must require runtime interaction receipts with real Postgres, Kafka, and OpenAI endpoints.<br>3. `release_certification.py` must reject artifacts with `simulated_components` when evaluating `INTEGRATION`/`LIVE`. |
| **P0-1A** | `BLOCKER` (P0) | `src/industrial_reliability/release_certification.py:288-345` | **Authoritative artifact identity is forgeable:**<br>• Validator only checks string length (64-char hex) and `verdict == "NOT FEASIBLE"`.<br>• An arbitrary synthetic JSON with fabricated `run_id: "fabricated"` was accepted and yielded `is_certified: true`. | Phase 1B certification input must be byte-hash verified against committed authoritative `docs/results/phase-1b-metrics.json`, and its contract/dataset hashes must match immutable references. |
| **P0-2** | `BLOCKER` (P0) | `src/industrial_reliability/replay_benchmark.py:171-249` | **Public benchmark fabricates measurements:**<br>• `--range-start`, `--range-end`, `--speed`, and `--restart-repetition` are CLI flags that are ignored in execution.<br>• `main()` hardcodes synthetic samples (`source_events=3744`, `p50_latency_ms=4.1`, `peak_rss_bytes=84_000_000`) and placeholder SHA hashes (`"1"*64`, `"2"*64`, etc.). | Benchmark runner must be classified as `SYNTHETIC` and excluded from release claims until backed by real streaming worker samples (Kafka lag, Prometheus metrics, process RSS, injected recovery). |
| **P0-3** | `BLOCKER` (P0) | `scripts/run_portfolio_demo.ps1:1-108`<br>`tests/test_portfolio_demo_scripts.py:123-132` | **Incomplete portfolio demo lifecycle:**<br>• `run_portfolio_demo.ps1` accepts `[switch]$SkipDocker` but never uses it.<br>• Never runs `docker compose up -d --build`, never polls readiness, never runs live Playwright tests (`npm run test:e2e:live`), and never provides safe teardown (`docker compose down`).<br>• `test_portfolio_demo_scripts.py` only tests string presence of URLs (`http://127.0.0.1:5173`), not lifecycle execution. | Complete the end-to-end lifecycle script: preflight, research package build, `docker compose up`, service readiness healthcheck polling, replay/alert/RCA execution, live browser test execution, exact-SHA certification, and non-destructive teardown instructions. |
| **P1-4** | `CRITICAL` (P1) | `src/industrial_reliability/api.py:483-486`<br>`tests/test_rca_api.py:126-168` | **Swallowed RCA persistence failure:**<br>• `POST /v1/alerts/{alert_id}/rca` executes `with contextlib.suppress(Exception): report = store.save_complete_rca(report)` and returns HTTP `200 COMPLETE` even when Postgres write fails. | Remove `contextlib.suppress(Exception)`. If persistence fails, log server-side without secret leakage and return a structured 5xx error (e.g. `RCA_PERSISTENCE_FAILED`), preventing non-durable responses. |
| **P1-5** | `CRITICAL` (P1) | `.github/workflows/ci.yml:35-91`<br>`apps/operator-console/package.json:12-13` | **CI skips MLflow & live browser:**<br>• `quality` job runs `npm run test:e2e` (hardcoded to `--project=mocked`).<br>• `integration` job installs `.[dev]` without `.[mlops]`, causing 3 MLflow tests to skip while passing CI. | Install `.[dev,mlops]` in CI integration job (enforce zero skipped tests for required capabilities), and add an explicit deployed/live browser test job running `test:e2e:live` against live containers. |
| **P1-5A** | `CRITICAL` (P1) | `src/industrial_reliability/release_certification.py:40-48, 373-392` | **Phase 9 profile shadowing:**<br>• `_P9_EVIDENCE_SPECS` iterates OpenAI before Fallback and breaks immediately if the file exists.<br>• An invalid `phase-9-rca-openai.json` causes early break, shadowing a valid sibling `phase-9-rca-fallback.json` and failing certification. | Explicitly select the target Phase 9 profile or evaluate candidate profiles without early break on invalid files. Reject ambiguous sibling profile conflicts. |
| **P1-6** | `CRITICAL` (P1) | `apps/operator-console/nginx.conf:1-33`<br>`docs/INTERVIEW_GUIDE.md:89-112`<br>`README.md:98-176`<br>`docs/results/release-certification.json` | **Unearned documentation & CSP claims:**<br>• `INTERVIEW_GUIDE.md` claims strict CSP compliance, but `nginx.conf` contains no `Content-Security-Policy` header.<br>• `INTERVIEW_GUIDE.md` & `README.md` claim Phase 8/9 PASS and `is_certified: true` pointing to ungenerated artifact paths.<br>• `docs/results/release-certification.json` contains all-zero SHA (`000...000`) claiming "fully functional and certified". | Add explicit CSP header in `nginx.conf`. Update documentation and status tables to report `UNPROVEN/BLOCKED` until fresh exact-SHA evidence is produced by dependency-backed runs. |
| **P2-7** | `MAJOR` (P2) | `compose.yaml:5,22,47,126,141,149,165`<br>`src/industrial_reliability/api.py:192-551` | **Network boundary & unauthenticated API:**<br>• API has no auth, rate limiting, or TLS.<br>• Acceptable ONLY because all Compose published ports are strictly bound to `127.0.0.1`. | Maintain strict `127.0.0.1` binding for local demo. Require auth, TLS, and rate limits if exposure moves beyond localhost. |
| **P2-8** | `MINOR` (P2) | `src/industrial_reliability/release_certification.py:248-442`<br>`src/industrial_reliability/replay_benchmark.py:171-250` | **Standards debt in certification path:**<br>• `ReleaseCertificationValidator.evaluate` (~195 lines) and `replay_benchmark.main` (~80 lines) violate the `<50 lines` modularity guideline. | Refactor monolithic evaluation methods into focused sub-evaluators during remediation. |

---

## 3. Comprehensive Security Scan Summary

- **Secrets:** Clean. Mock keys used strictly in isolated tests; `.env` gitignored; no hardcoded API keys or cloud tokens in production paths.
- **Input Validation:** Clean. Pydantic v2 frozen models with strict bounds, length constraints, and UUID validation.
- **SQL Injection:** Clean. Parameterized queries via psycopg 3 `%s` tuples; table/column allowlist validation for dynamic query helper.
- **RCE / Code Execution:** Clean. `subprocess.run` uses argument arrays with `shell=False`. `np.load` enforces `allow_pickle=False`. `joblib.load` enforces SHA-256 hash checks.
- **Trust Boundary:** Localhost-only (`127.0.0.1`).

---

## 4. Technical Constraints for Remediation

1. Python `>=3.12,<3.13`. No unapproved new heavy platform dependencies.
2. Maintain `Phase 1B: NOT FEASIBLE` historical truth.
3. Producer-owned evidence levels (`IN_PROCESS`, `INTEGRATION`, `LIVE`) verified by runtime receipts.
4. Fail-closed persistence in RCA API (`500 RCA_PERSISTENCE_FAILED` on DB failure).
5. Comprehensive exact-SHA release validation and live browser verification.
