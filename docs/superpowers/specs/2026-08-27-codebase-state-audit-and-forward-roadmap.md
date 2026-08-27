# Codebase State Audit & Forward Roadmap

**Status:** Revised implementation roadmap; remediation not yet executed
**Date:** 2026-08-27
**Original audit anchor:** git HEAD `72c5209af69ad411d7f9013f798c0fe3c5dc35da` on `feat/phase-9-grounded-rca`.
**Roadmap revision anchor:** latest `main` at `300a13679be64457745676a36d0135093affde4b`, after PR #16 merged and the `main` CI run passed; implementation branch `fix/interview-readiness-hardening`.
**Provenance:** The original audit used four read-only analyst passes over source, documentation, delivery infrastructure, and verification. This revision rechecked the claims against current code, local quality gates, published artifacts, Compose wiring, and current PR/CI state. It converts the snapshot into an evidence-gated implementation roadmap for interview readiness.
**Supersedes nothing; complements:** `docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md` (original intent) and `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md` (the pivot contract). This document records *what the codebase actually is* after Phases 1–11 executed, and the recommended forward direction.

---

# 1. Problem Statement

The platform's knowledge of its own state is scattered across sixteen plan documents, twenty result artifacts, two design specs, one remediation board (`task.md`), and a growing README. A maintainer (or reviewer, or future agent session) cannot answer "what exists today, what has been proven, what is half-wired, and what should be done next" without re-reading everything. Worst of all, the few prose claims that outrun the committed evidence (production-readiness phrasing, unexercised champion flows, LIVE-provider descriptions) sit undiscovered between dozens of accurate ones.

# 2. Solution

One consolidated, evidence-anchored state-of-the-codebase specification that:

1. inventories every capability layer (ML engine, runtime data flow, ML lifecycle, delivery infrastructure, verification fabric) with module-level precision;
2. reproduces the phase-by-phase verdict ledger with measured numbers and their committed evidence paths;
3. classifies all known gaps into five named classes with concrete reproduction points;
4. defines a prioritized forward roadmap (Prongs 0–6) whose ordering respects the repository's own fail-closed, evidence-first ethos and makes Prongs 0–4 the interview-readiness gate.

# 3. The One-Paragraph Truth Statement

This is an evidence-led **negative-research case study**, not a working anomaly detector and not currently a valid certified release. Both offline ML attempts failed their pre-declared gates (Phase 1 on the local MetroPT extract: best model detected 1 of 3 events, PR-AUC 0.0349–0.1719; Phase 1B on the official UCI MetroPT-3 dataset: statistical caught 3 of 4 while Isolation Forest and Autoencoder reached 4 of 4 at the operationally unacceptable cost of 13.146 and 30.670 false episodes/day). The codebase preserves `selected_model: null`, requires explicit `RESEARCH_CANDIDATE` opt-in, and implements deterministic replay, online/offline parity, provenance, alerting, grounded-RCA, observability, and an operator console. Those are substantial engineering assets, but deployed end-to-end availability, real fault recovery, live-provider RCA, measured runtime capacity, and release certification remain unproven. The current release validator can return `is_certified: true` when Phase 8 and Phase 9 evidence is rejected, so all release-certification claims are blocked until Prong 0 closes.

---

# 4. Platform Inventory

## 4.1 Source package map (54 modules in `src/industrial_reliability`, grouped by layer)

| Layer | Modules | Role |
|---|---|---|
| Wire / spine | `runtime_messages.py`, `runtime_ids.py`, `kafka_io.py` | Seven versioned Kafka topics; frozen Pydantic messages with `extra="forbid"` validators (coverage ≥24 obs across exactly 6 increasing bins; closed-world citation enforcement baked into `RcaReportV1`); UUIDv5 deterministic identity under a fixed namespace; canonical-JSON codec rejecting NaN |
| Ingestion / replay | `replay.py`, `replay_service.py` | pyarrow time-range filtered parquet source; strict-increasing timestamp validation; FSM replay controller with pace ∈ {1,100,1000}; async command consumer with idempotent producers; same CLI doubles as the Phase-3 determinism certifier |
| Featurization | `online_features.py`, `causal_features.py`, `features.py`, `phase1b_features.py` | Pure-math causal features shared online/offline for exact parity; online bin edges reuse the offline `_compute_bin_end` derivation from `phase1b_features.py`; 300 s strides / 6-bin lookback; segment closure on sequence_gap, conflicting_duplicate, timestamp_regression, invalid_bin, split_boundary |
| Scoring runtime | `worker.py`, `scoring_client.py`, `champion.py`, `models.py`, `autoencoder.py` | StreamingWorker with terminal-status barrier, manual offsets, quarantine topic; permanent-vs-retryable HTTP status classification; champion scorer over tamper-evident package; optional PSI drift gauge |
| Serving API | `api.py`, `alert_service.py`, `alert_policy.py`, `alert_state.py`, `alert_consumer.py`, `console_stream.py`, `replay_service persistence via psycopg` | FastAPI `/v1/score`, replay lifecycle + SSE stream, alert detail list/get, RCA generate-or-cache, model provenance endpoint, healthz/readyz; 409/422 fail-closed contract behavior |
| Grounded RCA | `rca_evidence.py`, `rca_openai.py`, `rca_gate_checks.py` | 4-tool allowlist projection (get_alert, get_score_evidence, get_model_provenance, get_system_health); OpenAI SDK structured outputs; closed-world citation discard+fallback; secret scrubbing (`__repr__` omits client; env restore verbatim) |
| ML lifecycle | `ml_lifecycle.py`, `ml_provenance.py`, `package_champion.py`, `package_release.py`, `package_research_candidate.py`, `phase7_gate.py` | MLflow 3.x import-candidate/reproduce/promote commands; immutable promotion receipts; ≤1e-9 threshold delta and ≤1e-6 score delta reproduction gates |
| Certification gates | `phase5_gate.py`, `phase6_gate.py`, `phase8_live_gate.py`, `phase9_gate.py`, `phase9_live_gate.py`, `phase10a_gate.py`, `phase10b_gate.py`, `release_certification.py`, `report_hashes.py` | Self-hashed reports bound to exact git SHA + expected schema + verdict field + evidence level (UNIT rejected where gate demands IN_PROCESS/LIVE) |
| Offline study engine | `data.py`, `benchmark.py`, `evaluation.py`, `contracts.py`, `phase1b_*` family, `drift.py`, `decision_gate.py`, `metrics.py` | Leakage-excluded benchmark stack (LPS+GPS banned); frozen Phase-1/1B contracts; bounded-label Prometheus metric vocabulary |

## 4.2 Runtime data flow (end-to-end)

```text
telemetry.parquet ──ReplayService(Kafka irp.telemetry.v1)──► OnlineFeatureBuilder(300s/6-bin)
        │                                                        │ FeatureVectorV1 + CoverageEvidenceV1
        ▼                                                        ▼
replay status topic ◄──FSM(pace 1/100/1000)────StreamingWorker ──ScoringClient──► Scoring API (/v1/score)
   (terminal-status barrier; quarantine on malformed/poison)                        │ decision
        ▼                                                                           ▼
Console SSE ◄──────── console_stream/alert_service ── PostgreSQL alert store ◄── decision policy
        │                                                                           │
        └── AlertPanel/RcaPanel ◄── POST /v1/alerts/{id}/rca ── rca_openai(4-tool allowlist) ◄─┘
```

Determinism properties certified along this path: logical-stream SHA-256 equality across replay speeds; feature-window equality vs offline at abs=1e-12; golden-case HTTP parity at abs=1e-9.

## 4.3 Delivery infrastructure

**Operator console** (`apps/operator-console`): React 18.3 + Vite 5.2 + TypeScript 5.4, deliberately minimal (no router, no state manager, hand-rolled SVG charts). SSE client `useReplayStream.ts` with typed `snapshot/score/telemetry/alert/status/resync_required` handlers and reconnect backoff; panels `ReplayControls`, `LiveCharts`, `AlertPanel` (drawer with evidence table), `RcaPanel` (generate/status badges/citation chips/disclaimer); REST client mirrors all backend routes including the SSE endpoint. Vitest at 80% thresholds (lines/functions/branches/statements) — 8 suites; Playwright has both a mocked spec and a live-backend spec (gated on a reachable `:8000/readyz`).

**Observability** (`ops/`, `metrics.py`): bounded-label metric vocabulary (14 metric families: dependency readiness, consumer lag, segment breaks, window coverage, score latency histogram, PSI drift, alert actions…); Prometheus scrape config; Grafana provisioned dashboards.

**Deployment topology** (`compose.yaml`, `Dockerfile`): pinned hashed runtime requirements (`requirements-runtime.txt` via `--require-hashes --only-binary :all:`), non-root UID 65532 on `python:3.12.10-slim-bookworm`; healthchecked compose graph for scoring-api, worker, replay service, PostgreSQL, Kafka, MLflow (localhost-only), Prometheus (3001), Grafana; research-candidate mode pinned via `SCORING_PACKAGE_DIR` + env flag.

**CI/CD** (`.github/workflows/`): ruff check+format → mypy strict → pytest `-m "not slow"` with coverage gate → pip check → python build → frontend vitest + tsc/vite build; PR-Agent AI review (currently DeepSeek V4 models); SonarCloud automatic analysis.

## 4.4 Verification fabric

Test guarantees by category, with representative artifacts:

- **Golden parity:** `tests/test_champion.py`, `tests/integration/test_scoring_api.py` (every packaged golden case over HTTP, abs=1e-9), `tests/test_online_features.py` (zip-strict + assert_allclose abs=1e-12), `tests/test_phase7_gate.py`.
- **Freeze guards:** `tests/test_contracts.py` (10,773,588 rows, paper event counts, holdout-once policy, LPS/GPS leakage exclusion), `tests/test_phase1b_contracts.py`, `tests/test_phase1b_published_results.py` (published metrics JSON schema freeze).
- **Wire/API contracts:** `tests/test_runtime_messages.py` round-trips; permanent-status non-retry classification; envelope-shape tests per endpoint.
- **Provenance/immutability:** canonical JSON NaN rejection, self-hash fixed-point property, fail-closed git-SHA resolution (`tests/test_report_hashes.py`), and partial release-evidence validation (`tests/test_release_certification.py`); the missing aggregate fail-closed assertion is Prong 0.
- **Anti-surface governance:** `tests/test_no_airflow_surfaces.py` asserts absence in deps/compose/dirs AND existence of the not-adopted ADR.
- **Gate status at audit time:** pytest 431 passed / 6 skipped (Docker-dependent integration), mypy strict clean across 54 files, coverage 87.02% (gate ≥80%), ruff clean. Declared local quality commands match CI's set.

## 4.5 Interview portfolio strength and claim matrix

| Capability | Defensible evidence | Interview claim boundary |
|---|---|---|
| Memory-bounded data engineering | Full streaming validation of 10,773,588 rows / 1.65 GB; Arrow batch processing; Parquet segmentation; official MetroPT-3 normalization to 1,516,948 rows | Claim large local time-series processing, not distributed Big Data or Spark-scale throughput |
| Leakage-safe ML evaluation | Chronological train/calibration/holdout, full-lookback purge, no interpolation, leakage-sensitive predictors excluded, evaluate-once holdout policy | Claim scientific and operational evaluation discipline, not a successful production model |
| Reproducible model ladder | Statistical detector, Isolation Forest, and deterministic CPU autoencoder with frozen parameters and artifact hashes | Claim reproducible training and model comparison, not a champion model or novel algorithm |
| Operational benchmark design | Event detection, lead time, false episodes/day, time in alert, and PR-AUC under a predeclared gate | Claim a decision-useful benchmark; do not claim benchmark superiority or breakthrough performance |
| Offline/online consistency | Online feature parity at absolute tolerance `1e-12`; scoring golden parity at `1e-9` | Claim local automated parity evidence; live deployed parity remains part of Prong 2 |
| Event-driven reliability design | Kafka at-least-once semantics, deterministic UUIDv5 identities, manual commits, quarantine, terminal-status barrier, PostgreSQL alert state and outbox | Claim implemented and unit-tested reliability patterns; do not claim availability or recovery SLOs yet |
| Grounded AI safety | Four-tool evidence allowlist, closed-world citations, secret scrubbing, evidence-preserving `UNAVAILABLE` fallback | Claim tested grounding contracts; do not claim a certified live OpenAI interaction yet |
| Engineering decision quality | Measured negative model decision; Airflow `NOT_ADOPTED`; Spark/OpenVINO stopped behind reconsideration gates | Claim evidence-led scope control rather than technology accumulation |
| Quality automation | 431 Python tests, 87.02% coverage, strict mypy/Ruff, 44 frontend tests, and green merged-`main` CI | Claim strong automated local/CI verification; dependency-backed and browser-live evidence remains incomplete |

### Claims prohibited until their gates close

- Successful predictive-maintenance model or production champion.
- Breakthrough anomaly-detection benchmark.
- Distributed Big Data processing.
- Proven high availability, recovery time, or production throughput.
- Fully deployed operator console or live-provider RCA.
- Exact-SHA certified platform release.

---

# 5. Phase Verdict Ledger (measured outcomes, Phase 0 → 11 + remediation board)

Measured metrics and historical verdict strings below are transcribed from committed artifacts. Readiness labels such as `LOCAL AUTOMATED EVIDENCE`, `NOT DEPLOYMENT-PROVEN`, and `BLOCKED` are the current revalidation of what those artifacts can honestly support.

| Phase | Goal | Measured verdict & key numbers | Evidence artifact |
|---|---|---|---|
| 0. Research grounding | Verify MetroPT domain claims row-by-row | `READY WITH OPEN QUESTIONS`; 405.9 s raw scan; canonical target 1,516,948 rows; DOI `10.24432/C5VW3R`; archive SHA-256 `aab991a9…1721a` | `docs/research/research-readiness-review.md`, `docs/research/metropt-dataset-profile.json`, `docs/data/metropt3-source-attribution.md` |
| 1. Offline feasibility (local extract) | ≥2-of-3 failure events on frozen holdout | **`NOT FEASIBLE`**, `selected_model: none`; statistical 1/3, PR-AUC 0.0349; IForest 1/3 (0.1210); AE 1/3 (0.1719); 12 documented limitations | `docs/results/phase-1-offline-ml-feasibility.md`, `phase-1-metrics.json` (contract `5d960b6e…`) |
| 1B. UCI MetroPT-3 fresh validation (single permitted attempt) | One-shot re-validation on fresh official dataset | **`NOT FEASIBLE`**, `selected_model: null`; statistical 3/4 (lead times 600–6000 s) with 5.707 false eps/day; IForest 4/4 but 13.146 false eps/day; AE 4/4 but 30.670 false eps/day; PR-AUC 0.05–0.38 | `docs/results/phase-1b-metropt3-fresh-validation.md`, `phase-1b-metrics.json` (contract `149e1647…047d8`) |
| Fork: evidence-gated roadmap | Stop vs continue honestly | Phases blocked for champion path; proceed as negative-research case study; `RESEARCH_CANDIDATE` gated by `ALLOW_RESEARCH_CANDIDATE=true`; evidence vocabulary locked to UNIT/INTEGRATION/LIVE; missing dependency must block, never downgrade | `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`, `plans/2026-08-24-post-phase-1-agent-board.md` |
| 2. Research package + scoring API | Tamper-evident deterministic scoring runtime | **LOCAL AUTOMATED EVIDENCE**; golden parity ≤1e-9; manifest-child SHA-256 chain verified before `joblib.load()`; HTTP 409/422 fail-closed; package remains `RESEARCH_CANDIDATE` | `docs/results/phase-2-model-package-scoring-api.md` |
| 3. Telemetry contract + Kafka replay | Deterministic replay contract | **LOCAL CONTRACT EVIDENCE**; logical-stream SHA-256 identical at 1×/100×/1000×; current Compose-backed replay not release-certified | `docs/results/phase-3-telemetry-contract-kafka-replay.md` |
| 4. Online feature/scoring worker | Online↔offline parity in streaming worker | **LOCAL AUTOMATED EVIDENCE**; window equality <1e-12; live dependency path remains a Prong-2 gate | `docs/results/phase-4-online-parity.md` |
| 5. Alert lifecycle persistence | Durable alert store + policy identity | **IMPLEMENTED / PARTIALLY INTEGRATED**; policy hash and outbox behavior are tested, but dependency-backed PostgreSQL evidence is not required successfully in the current default gate | `docs/results/phase-5-alert-lifecycle.md` |
| 6. Operator console | Operations UI over SSE | **IMPLEMENTED / NOT DEPLOYMENT-PROVEN**; component tests exist, but the Compose nginx hostname is wrong, styling is incomplete, and Playwright is absent from CI | `docs/results/phase-6-operator-console.md` |
| 7 (+7a). Reproducible ML lifecycle / Airflow decision | MLflow import-reproduce-promote / scheduler decision | Lifecycle commands shipped, tolerances ≤1e-9/≤1e-6 attested locally only (`artifacts/` git-ignored — no committed proof); Airflow **`NOT ADOPTED`** with quantified RSS rationale (~1.5–2 GB) and enforced anti-surface tests | README §Phase 7; `docs/decisions/2026-08-24-airflow-not-adopted.md`; `tests/test_no_airflow_surfaces.py` |
| 8. Observability & reliability (fault drills) | Prove observable fault distinctions | **`IN_PROCESS` EVIDENCE** published from a mocked-drill framework; no real dependency fault or recovery was exercised | `docs/results/phase-8-observability-reliability.{md,json}`; `scripts/run_phase8_live_fault_drills.ps1` |
| 9. Grounded RCA | LLM RCA restricted to gathered evidence | **`IN_PROCESS` EVIDENCE** published for UNAVAILABLE/fallback behavior including secret scrubbing and closed-world citations; no committed artifact shows a live `LIVE_OPENAI` provider response | `docs/results/phase-9-grounded-rca.{md,json}`; `scripts/run_phase9_live_gate.ps1` |
| 10a / 10b. Spark / OpenVINO decision gates | Adopt or stop platform optimization paths | Both **`N/A`** with reason code `PLATFORM_PATH_STOPPED` + pre-committed reconsideration triggers; capacity numbers in the benchmark tool are synthetic (see Gap class 3) | `docs/results/phase-10a-spark-decision.{md,json}`, `phase-10b-openvino-decision.{md,json}` |
| 11. Release certification | Exact-SHA portfolio packaging | **BLOCKED / NOT CURRENTLY CERTIFIED**; a historical `NEGATIVE_RESEARCH_RELEASE` artifact exists with an all-zero Git SHA, and current validation still sets `is_certified: true` when required Phase 8/9 evidence is rejected | `docs/results/release-certification.{md,json}`, `src/industrial_reliability/release_certification.py` |
| Remediation board (2026-08-25 → present) | Close bot-review findings on PR #15/#16 | PR #16 merged at `300a136`; its PR checks and the resulting `main` push CI completed successfully. The old GitHub Actions outage is no longer a blocker; the remaining blockers are the trust, deployment, and evidence gaps in §6 | `task.md`; PR #16; `main` CI run `32987326332` |

### Known claim-debt rows (prose ahead of evidence)

- README's opening "Production-oriented …platform" phrasing vs the committed negative-research profile.
- Phase-7 champion flow never exercised end-to-end with a legitimate champion (none can legitimately exist given `selected_model: null`).
- `portfolio_claims.py` fixtures use synthetic numbers (75% detection, 1800 s median lead) — safe structurally, misleading if quoted as measured.
- Live OpenAI RCA is structurally wired but only its fallback path has a committed in-process artifact.
- `MODEL_CARD.md` reports the Autoencoder as 3/4 events and 16.32 false episodes/day, while the authoritative Phase-1B metrics record 4/4 and 30.670 false episodes/day.
- Release certification reports a successful certification and an unconditional “runtime fully functional and certified” limitation even when Phase 8 and Phase 9 fail evidence validation.

---

# 6. Gap Analysis (five named classes)

## Class 1 — Cross-layer wiring ("works in dev ≠ works deployed")

1. **Console nginx proxy hostname:** the built console image resolves `/v1`, `/healthz`, `/readyz` against a hostname that does not exist in the compose network (dev mode works only because Vite proxies to `127.0.0.1:8000`). Every call from a *deployed* console fails DNS → 502. One alias away from fixed.
2. **RCA env vars never reach the container:** `.env.example` defines `RCA_OPENAI_API_KEY/_MODEL/TIMEOUT_SECONDS` and `rca_openai.from_env()` consumes them, but compose passes none into `scoring-api`'s environment — variable substitution alone is not container env. Deployed RCA will permanently produce evidence-only fallback reports regardless of any configured key.
3. **Prometheus never scrapes alert-service:** alert-service advertises `METRICS_PORT=9103` but `prometheus.yml` has no job for it.
4. **Alert metrics are dead code:** `irp_alerts_active` / `irp_alert_events_total` exist with tests and a Grafana panel; no production caller records them; AlertConsumer holds no metrics reference.
5. **Playwright e2e not in CI:** neither the mocked nor the live spec runs in `ci.yml`; the console Docker image (where gap #1 hides) is never built or tested there either.
6. **Orphaned preflight:** `deploy/preflight.py` is invoked by nothing (and checks outdated ports vs. compose's published 29092/3001); `run_portfolio_demo.ps1` assumes an already-running stack, never boots one, and doesn't export `ALLOW_RESEARCH_CANDIDATE`.
7. **Console cosmetics broken by missing dependency:** `RcaPanel.tsx` is styled exclusively with Tailwind utility classes while the app has no Tailwind config/dependency → unstyled output; plus fetched-but-unrendered `events`/`decisions` fields and stale failing-run artifacts committed under `test-results/`.

## Class 2 — Security surface

No authentication/authorization/rate limiting on `/v1/score`, replay control, RCA, SSE; no `pip-audit`/`bandit`/`trivy` in CI; model loading relies on unpickling `detector.joblib` protected only by SHA equality; local `.env` contains a live-format key adjacent to repo configs; Grafana admin password defaults to `admin`; compose credentials are inline (loopback-acceptable but undocumented).

## Class 3 — Internal tech debt

Legacy PHASE1 engine (~55 KB: `data.py`/`features.py`/`benchmark.py`) duplicates the PHASE1B lineage and invites divergence; `replay_benchmark.py` emits fabricated latency/throughput constants feeding Phase-10a capacity gates (dead ADOPTED branches should be measured-or-removed); per-call Postgres connections with an unused `psycopg_pool` import and hard-coded `champion-statistical-v1` model version in `record_replay_status`; machine-id fragmentation (`metropt-compressor-01` vs `metropt3` defaults) blocks multi-machine scale-out; drift PSI is observe-only (no threshold/alarm/retraining trigger; reference path silently skippable); worker session checkpoints absent for long replays; git-SHA resolution inconsistent (gates fail closed, some paths still fall back to `"0"*40`).

## Class 4 — Verification gaps

Release certification is the first verification blocker: invalid or missing required runtime evidence adds limitations but does not make the release invalid. All fault drills use Mock/AsyncMock — no real-compose chaos (broker kill, DB restart, network partition, clock skew); no per-commit performance-regression budget (hot-loop latency decay undetectable between phase gates); holdout/slow-marked tests are deselected in normal CI with no scheduled job; the hash system has no independent oracle vectors for canonical JSON edge cases; SonarCloud CPD is globally excluded (`sonar.cpd.exclusions=**/*`) and coverage report paths are not wired into Sonar; mypy scope excludes `scripts/`, `deploy/`, `db/migrations/`, and console backend wrappers; frontend has no accessibility or visual-regression testing.

## Class 5 — Claim debt

See §5 "Known claim-debt rows": README production-phrasing; unexercised champion lifecycle flow; synthetic portfolio fixtures; live-provider RCA described beyond its committed fallback evidence.

---

# 7. Forward Roadmap (prioritized prongs)

**Ordering principle:** restore trust → make one deployed path work → collect real operational evidence → package the interview story → harden only for the exposure being claimed → resume science on fresh evidence. Nothing here rewrites the permanent Phase 1/1B verdicts or permits retuning a viewed holdout.

## Prong 0 — Certification and claim integrity (blocking)

1. Make release certification fail closed when any evidence required by the chosen release profile is missing, invalid, failing, unreadable, unit-level, or bound to another Git SHA.
2. Remove the unconditional “runtime fully functional and certified” statement; generate limitations only from phases that actually passed.
3. Add regression tests asserting `is_certified: false` and a non-success verdict when Phase 8 or Phase 9 required evidence is rejected.
4. Regenerate certification only from fresh artifacts under `artifacts/certification/<git-sha>/`; never reuse the historical all-zero-SHA report.
5. Correct `MODEL_CARD.md` against `phase-1b-metrics.json` and align README/spec language with the evidence matrix in §4.5.

**Gate:** evaluating the committed stale result set must not produce a certified release; a new release can be certified only from an exact-SHA, self-consistent mandatory evidence set.

## Prong 1 — One-command deployed demo

1. Fix the operator-console nginx upstream from nonexistent `api` to `scoring-api`.
2. Pass optional `RCA_OPENAI_*` settings into `scoring-api` without embedding or logging secrets; the no-key path must remain a first-class fallback demo.
3. Add alert-service to Prometheus and connect alert-action/active-gauge metrics to real alert transitions.
4. Update `deploy/preflight.py` to the actual ports and prerequisites; make `run_portfolio_demo.ps1` preflight, build or verify the research package, set explicit research opt-in, start Compose, wait for readiness, run the bounded demo, and print teardown instructions.
5. Use the console's existing styling approach for `RcaPanel`; do not add Tailwind solely for one component.
6. Document local credentials and localhost-only security boundaries in `.env.example` and the runbook.

**Gate:** from a clean checkout with documented prerequisites, one command reaches healthy API, console, Kafka, PostgreSQL, Prometheus, Grafana, and MLflow services and completes the research-only replay/alert/RCA-fallback journey.

## Prong 2 — Real integration and recovery evidence

1. Run PostgreSQL and Kafka integration tests as required checks in a Compose-backed CI or explicitly invoked certification job; required dependency tests may not silently skip.
2. Run mocked Playwright tests in normal CI and the live-backend Playwright suite in the Compose-backed job; build and smoke-test the console image.
3. Replace in-process-only fault claims with real dependency drills for broker interruption, database interruption, malformed telemetry, and known-abnormal replay.
4. Record observed classification, recovery outcome, lost/duplicated messages, committed offsets, alert persistence, and evidence level. Missing prerequisites block the gate instead of downgrading it.

**Gate:** fresh exact-SHA `INTEGRATION` or `LIVE` artifacts prove the required dependency interactions and recovery behavior; no report may infer live evidence from mocks.

## Prong 3 — Measured runtime benchmark

1. Replace `replay_benchmark.py` constants with measurements from a frozen replay workload.
2. Record workload hash, source event count, valid windows, p50/p95 latency, throughput, consumer-lag peak and drain time, recovery duration, duplicate/quarantine counts, CPU time, and peak RSS.
3. Bind the report to the research package, contract, source dataset, environment, and exact Git SHA; retain raw timing samples needed to recompute aggregates.
4. Establish a regression budget only after the first truthful baseline exists.

**Gate:** every published capacity or latency number is recomputable from captured measurements; synthetic fixture values remain confined to tests.

## Prong 4 — Interview packaging

1. Lead with the evidence-gated negative result: a 4/4 detector can still be operationally unusable because 13.146–30.670 false episodes/day creates alert fatigue.
2. Demonstrate the 10.77M-row memory-bounded ingestion, leakage-safe temporal contract, deterministic training ladder, online/offline parity, event-driven runtime, and grounded-RCA fallback.
3. Publish one capability/evidence/limitation table and a ten-minute demo script with links to exact artifacts.
4. Keep “not proven” claims visible: no champion, no breakthrough benchmark, no distributed Big Data, no availability SLO, and no production release.

**Gate:** a reviewer can reproduce the demo and trace every spoken quantitative claim to a current artifact without reading the full repository history.

## Prong 5 — Security before non-local exposure

Keep the portfolio demo bound to localhost until token-based authorization, endpoint-specific rate limits, request-size limits, dependency/container scans, safer model-artifact loading, non-default credentials, and secret-history review are complete. This prong is not a blocker for an accurately described local interview demo; it is mandatory before any shared or internet-accessible deployment.

## Prong 6 — Science on fresh evidence (not an interview-readiness blocker)

Do not retune either viewed holdout. A future research cycle must pre-register a new hypothesis and use fresh evaluation evidence, such as a second industrial dataset or newly acquired incident windows. Candidate work may explore multi-scale causal features, physically constrained transformations, and lead-time-aware horizons, but the original feasibility ceiling remains ≤1 false episode/day and ≤5% time in alert. Spark/OpenVINO reconsideration remains dormant until measured workload or latency triggers fire.

## Opportunistic code health

Archive or absorb the legacy Phase-1 engine only when doing so reduces an active maintenance burden; unify Git-SHA resolution, use `psycopg_pool` only when measured connection overhead matters, make drift's observe-only boundary explicit, re-enable scoped SonarCloud duplication checks, and extend static checking where it protects the execution path. None of these should delay Prongs 0–4 unless directly required by their gate.

---

# 8. User Stories

1. As a returning maintainer, I want one document that states the platform's real capabilities and verdicts, so that I don't have to re-derive project state from sixteen plans each session.
2. As a future agent session, I want evidence paths beside every claim, so that I can re-verify numbers instead of trusting prose.
3. As a code reviewer of the implementation branch, I want each prong to end in a falsifiable gate, so that passing tests cannot conceal missing runtime evidence.
4. As the developer preparing for interviews, I want trust and one-command demoability completed before adding features, so that the strongest claims are reproducible under interview conditions.
5. As a demo operator, I want wiring defects named concretely (env passthrough, scrape jobs, proxy hostnames), so that "works as deployed" stops differing from "works in dev".
6. As a security reviewer, I want the security surface enumerated in one place, so that hardening work can be scoped into one sprint rather than discovered piecemeal.
7. As a recruiter/reviewer reading the portfolio, I want prose claims bounded by their evidence level, so that I can trust what the README says.
8. As an ML practitioner picking up this repo, I want the failed gates recorded as permanent context, so that I do not unknowingly retune against the viewed holdout.
9. As a contributor wanting to help, I want small-diff tasks identified inside larger prongs, so that I can pick up self-contained fixes without redesigning anything.
10. As anyone planning Phase-12+ work, I want technology reconsideration triggers kept explicit, so that parked decisions are revisited only on measured milestones.

---

# 9. Implementation Decisions

Decisions governing this document as an artifact of the repository:

1. **Placement & naming:** lives under the repo's existing specification directory following its `YYYY-MM-DD-slug.md` convention, alongside the two prior design specs; it is a *state-of-the-codebase audit spec*, distinct from phase plans.
2. **Evidence-anchor header:** the document preserves the original audit SHA and records the latest-main revision SHA separately, so historical findings are not confused with the implementation base.
3. **Verdicts are transcribed, not paraphrased:** every ledger row carries the committed verdict string plus key measurements; where a claim exists only locally (Phase 7 tolerances), that limitation is stated in-line rather than papered over.
4. **Path citations retained deliberately:** this deviates from the usual "no file paths in specs" guidance because for an audit the paths themselves ARE the durable content — they let any reader re-run verification against the artifacts. Trimmed hashes (`5d960b6e…`) intentionally remain partial to avoid asserting unverifiable full digests here.
5. **Five-class gap taxonomy** (wiring / security / tech-debt / verification / claims) is retained for diagnosis; execution priority is defined separately by Prongs 0–6 and their gates.
6. **Roadmap respects preserved verdicts:** no prong may retune against viewed holdout data or resurrect `NOT ADOPTED`/`PLATFORM_PATH_STOPPED` decisions outside their own reconsideration triggers (inherited from the post-phase-1 fork contract).
7. **Language:** English, matching every other spec/plan/result document in `docs/superpowers/`.
8. **No issue-tracker publication:** tracker vocabulary was never configured for this workspace and the request was explicitly a file; publishing stays possible later by copy-posting §6+§7 with the label vocabulary if `/setup-matt-pocock-skills` runs.

# 10. Verification Decisions

This revision changes documentation only, so it introduces no runtime tests. The roadmap it defines is accepted only through the following evidence:

- **Spec integrity:** no placeholders or stale outage statements; every quantitative claim resolves to an existing evidence artifact; all prohibited claims remain explicit.
- **Prong 0:** regression tests prove invalid/missing Phase 8 or Phase 9 evidence cannot produce `is_certified: true`; fresh certification is exact-SHA and self-consistent.
- **Prong 1:** Compose configuration validates, all required services become ready, and the one-command local demo completes from a clean checkout.
- **Prong 2:** required Kafka/PostgreSQL/browser checks pass without skip; fault evidence records real dependency interactions and recovery outcomes.
- **Prong 3:** benchmark aggregates are recomputable from captured samples and are bound to workload, package, environment, and Git SHA.
- **Prong 4:** the demo script and claim matrix reference only current artifacts and can be followed by a reviewer without hidden local setup.
- Existing `tests/test_phase1b_published_results.py` remains the pattern if stable documentation claims later become machine-enforced contracts.

# 11. Out of Scope

- Re-running either viewed ML holdout or changing the preserved Phase 1/1B metrics.
- Implementing any listed gap in this documentation-only revision; implementation proceeds on `fix/interview-readiness-hardening` after a reviewed execution plan.
- Re-litigating `NOT ADOPTED` / `N/A` technology decisions or the Phase 1/1B verdicts (both are permanent evidence per the fork contract).
- Publishing anything externally (blog/whitepaper/poster): interview packaging remains local until its gate passes.
- Non-local deployment before Prong 5 security controls pass.

# 12. Further Notes

- PR #16 is merged and the resulting `main` CI run is green; the historical GitHub Actions outage is resolved and removed from the execution critical path.
- Prong 0 now refers exclusively to certification and claim integrity. It is a real code-and-evidence blocker, not an external waiting state.
- The implementation branch is `fix/interview-readiness-hardening`; this spec revision is intentionally uncommitted pending review.
- If the team prefers Vietnamese narrative summaries alongside English artifacts, add them as separate briefing notes rather than translating this spec — bilingual sources of truth drift quickly.


