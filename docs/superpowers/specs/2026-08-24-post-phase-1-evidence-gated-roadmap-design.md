# Post-Phase-1 Evidence-Gated Roadmap Design

**Status:** Approved in chat for implementation planning  
**Date:** 2026-08-24  
**Supersedes:** The provisional Phase 2-9 ordering in `2026-08-23-industrial-reliability-intelligence-platform-design.md` where this document is more specific.

## 1. Objective and terminal state

Build a portfolio-grade, production-like industrial reliability platform that runs locally from a pinned, one-command stack and demonstrates a traceable path from historical telemetry replay through causal features, anomaly scoring, persisted alerts, grounded RCA, observability, and measured optimization decisions.

The project is complete when the exact-SHA release certification passes locally. Cloud hosting, high availability, disaster recovery, autoscaling, multi-tenancy, and public-network operation are explicit non-goals.

## 2. Phase 1 evidence and mandatory branch

Phase 1 completed on branch `phase1/offline-ml-feasibility` at `ba703a3aae130522b7628d5db4813c804d8d4213`. The published aggregate artifact reports:

- verdict `NOT FEASIBLE`;
- `selected_model: null`;
- statistical, Isolation Forest, and dense autoencoder each detected only one of three events;
- the statistical model exceeded the false-episode gate;
- no model met the predeclared event-detection gate.

This verdict is permanent evidence. No later phase may rewrite it, tune against its already-viewed holdout, or describe any Phase 1 model as production-ready.

The user selected one and only one fresh-validation attempt, Phase 1B. Phases 2-11 remain blocked unless Phase 1B produces a `FEASIBLE` verdict and a non-null champion manifest. If Phase 1B fails, the platform path stops and Phase 11 publishes a negative research release instead of a production-like demo.

## 3. Phase 1B fresh-validation contract

### 3.1 Source identity

Use the UCI MetroPT-3 dataset as a fresh external validation source:

- DOI: `10.24432/C5VW3R`;
- download URL: `https://archive.ics.uci.edu/static/public/791/metropt%2B3%2Bdataset.zip`;
- candidate archive SHA-256: `aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a`;
- expected normalized observations: `1,516,948`;
- locally recorded source license: CC BY 4.0.

Live UCI verification was attempted on 2026-08-24 but `browser-act` was unavailable without an API key. Therefore the runtime preflight must fail closed unless the URL, DOI, license, archive checksum, CSV member, schema, and row count match these literals. A mismatch requires a new design decision; implementation must not silently update the contract.

Raw data, derived features, scores, and model weights remain local and git-ignored. Committed artifacts are limited to code, tests, contracts, aggregate metrics, source attribution, and limitations.

### 3.2 Canonical schema and leakage controls

Canonical source columns are:

```text
timestamp,
tp2, tp3, h1, dv_pressure, reservoirs, oil_temperature, motor_current,
comp, dv_electric, towers, mpg, lps, pressure_switch, oil_level,
caudal_impulses
```

The seven pressure/temperature/current columns are analog. The eight state columns are digital. `lps` is preserved as evaluation evidence and excluded from every predictive transform, feature, fit, calibration, and score. Timestamp is provenance only. Train-constant predictive columns are removed using train data only.

Timestamps remain naive/unspecified. Duplicate timestamps are rejected unless byte-identical; conflicting duplicates fail validation. No backfill, forward fill, interpolation, centered windows, random split, or holdout-derived feature selection is allowed.

### 3.3 Time processing and partitions

Normalize the irregular approximately ten-second source into right-closed five-minute bins. A bin is valid only when it contains at least 24 observations, representing 80% of the nominal 30 observations. Do not synthesize missing readings.

Each decision uses six consecutive valid bins, giving a 30-minute causal lookback and five-minute stride. A window may not cross an invalid bin, timestamp regression, or split boundary. Analog and digital statistics retain the Phase 1 definitions: analog `last`, `mean`, population `std`, `min`, `max`, and `delta`; digital `last`, `active_ratio`, and `transition_count`.

Fixed partitions are:

- train `[2020-02-01 00:00:00, 2020-02-22 00:00:00)`;
- calibration `[2020-02-22 00:00:00, 2020-03-01 00:00:00)`;
- holdout `[2020-03-01 00:00:00, 2020-09-01 04:00:00)`.

Purge the full 30-minute lookback at each boundary. Fit every transform/model on train only and select every threshold on calibration only. Evaluate the locked ladder once on holdout.

### 3.4 Fresh event evidence

Preserve the four UCI consolidated incident annotations at minute precision:

| ID | Source start minute | Source end minute | Condition |
|---|---|---|---|
| `metropt3-1` | `2020-04-18 00:00` | `2020-04-18 23:59` | air leak / high stress |
| `metropt3-2` | `2020-05-29 23:30` | `2020-05-30 06:00` | air leak / high stress |
| `metropt3-3` | `2020-06-05 10:00` | `2020-06-07 14:30` | air leak / high stress |
| `metropt3-4` | `2020-07-15 14:30` | `2020-07-15 19:00` | air leak / high stress |

For arithmetic, normalize each source interval to `[source_start_minute, source_end_minute + 1 minute)`, while retaining both original minute literals in the contract manifest.

### 3.5 Model and gate policy

Reuse the Phase 1 model ladder and fixed settings rather than adding a model after seeing MetroPT-3 holdout:

1. robust statistical detector;
2. Isolation Forest with 200 trees, `max_samples="auto"`, `contamination="auto"`, seed 42, and one job;
3. dense PyTorch autoencoder `[input, 64, 16, 64, input]`, ReLU, MSE, Adam `0.001`, batch 256, 20 CPU epochs, seed 42, deterministic algorithms, and zero data-loader workers.

Each model threshold is the calibration 99.5th percentile with NumPy `method="higher"`. An anomaly is `score >= threshold`. Merge decisions into an episode only when adjacent decision timestamps differ by at most the five-minute stride.

An event is detected when the first anomalous decision is in `[event_start - 2 hours, normalized_event_end)` or its decision interval overlaps the normalized source interval. Report absolute detections, per-event first detection and lead time, false episodes per valid normal-exposure day, window PR-AUC, and time in alert.

Phase 1B is `FEASIBLE` only when one model satisfies all of:

- detects at least 3 of 4 events;
- no more than 1 false episode per valid normal-exposure day;
- no more than 5% time in alert.

Select the simplest passing model using statistical, Isolation Forest, then autoencoder preference. Do not retune after holdout. Do not copy reference-repository code, configuration, prose, artifacts, or metrics.

## 4. Runtime architecture

Use four operator-facing/runtime units:

1. React + Vite operator console;
2. FastAPI control and stateless scoring API;
3. Kafka replay producer;
4. Python streaming worker containing feature, score-decision, and alert consumer loops.

PostgreSQL stores replay sessions, score decisions, alert lifecycle state, and evidence snapshots. It does not duplicate the full raw dataset. Raw Parquet remains the telemetry source of truth. Prometheus scrapes every runtime process; Grafana presents system/data/model views. MLflow is mandatory for experiment and champion provenance.

Kafka uses at-least-once delivery. Deterministic identifiers plus PostgreSQL unique constraints provide idempotent retry; the project never claims exactly-once delivery.

### 4.1 Versioned messages

Every message includes `schema_version`, `message_id`, `replay_session_id`, `source_dataset_sha256`, `contract_sha256`, `source_timestamp`, and `emitted_at`.

- `ReplayCommandV1`: `command_id`, `action`, `speed`, `range_start`, `range_end`.
- `ReplayStatusV1`: `state`, `last_sequence`, `source_timestamp`, `error_code`.
- `TelemetryEventV1`: `machine_id`, `sequence`, and canonical sensor values.
- `FeatureVectorV1`: `window_start`, `window_end`, ordered feature names/values, and coverage evidence.
- `ScoreDecisionV1`: `decision_id`, `model_version`, score, threshold, anomaly flag, and evidence vector.
- `AlertEventV1`: `alert_id`, lifecycle action, first/last detection, and decision references.
- `EvidenceSnapshotV1`: alert, feature-deviation, data-quality, model, and system-health references.
- `RcaReportV1`: status, summary, observations, uncertainty, next checks, and evidence IDs.

`POST /v1/score` accepts only a versioned feature vector with `contract_sha256` and `model_version`. Feature/window construction belongs to the worker; the scoring API remains stateless.

## 5. Operator console boundary

The console is an operator demo surface, not an ML administration product. It provides:

- replay start, pause, resume, stop, speed, and bounded time-range controls;
- live downsampled telemetry and anomaly score via SSE;
- replay/session state and dependency health;
- alert list and alert details;
- persisted evidence, model/data provenance, and RCA output.

It excludes auth/RBAC, model promotion, policy editing, raw-data exploration, multi-tenancy, and public-network use. Services bind to localhost. Exposing the stack outside localhost requires a separate security design with authentication and TLS.

## 6. Reliability and verification contract

- Duplicate delivery is idempotent; invalid schema enters a quarantine topic with a reason.
- Gap or ordering violation closes the active segment; no data is invented.
- Contract/model mismatch fails closed and fails the replay session.
- Worker offsets are not committed until the corresponding durable or downstream action succeeds.
- Database or scoring outage is retried with a bounded policy; exhaustion marks the session failed.
- LLM outage never blocks scoring or alerting; the RCA status becomes `UNAVAILABLE` while evidence remains accessible.
- SSE reconnect uses an event cursor plus durable API snapshot.
- Correlation follows `replay_session_id -> window_id -> decision_id -> alert_id`.

Every implementation phase must provide contract tests, focused unit tests, integration evidence against real dependencies where applicable, at least 80% branch coverage, and exact commands for Ruff, formatting, mypy, pytest, pip check, and build. UI certification uses Playwright with real clicks. Synthetic CI evidence and private full-data evidence remain explicitly separate.

## 7. Evidence-gated phase sequence

| Phase | Deliverable | Exit gate |
|---|---|---|
| 1B | MetroPT-3 fresh validation | `FEASIBLE` plus non-null champion, or stop platform path |
| 2 | Champion package and scoring API | benchmark/package/API golden score and evidence parity |
| 3 | Telemetry contract and Kafka replay | deterministic ordered replay; speed preserves source time |
| 4 | Online feature/scoring worker | offline-online feature and score parity; retry idempotence |
| 5 | Alert lifecycle and PostgreSQL persistence | locked policy, traceable alert, restart recovery |
| 6 | React operator console | real-click replay-to-alert-to-evidence path |
| 7 | Reproducible ML lifecycle | online model traces to MLflow data/code/contract/metrics |
| 7A | Airflow decision gate | adopt only for measured scheduling/retry/resume value |
| 8 | Observability and reliability | fault drills distinguish service, data, and machine conditions |
| 9 | Grounded RCA | every factual claim references allowlisted evidence |
| 10A | Spark decision gate | adopt only with parity and measured net benefit |
| 10B | OpenVINO decision gate | applicable only to PyTorch champion; adopt only with parity and benefit |
| 11 | Release and portfolio certification | pinned one-command stack and exact-SHA evidence package |

MLflow is mandatory. Airflow, Spark, and OpenVINO require evidence-backed adoption decisions; `NOT ADOPTED` or `N/A` is a valid phase result. RCA uses one cloud provider configured only by environment variables and has an evidence-only fallback. Multi-provider support and local-model hosting are not in scope.

## 8. Definition of done

On a feasible path, Phases 2-9 and 11 must pass. Phases 7A, 10A, and 10B must publish decisions but need not adopt their technologies. The final release includes pinned local startup, a deterministic real-data demo scenario, real-click E2E evidence, service/data/model dashboards, data and model cards, a runbook, architecture diagrams, demo script or video, and CV claims generated only from measured artifacts.

On a second infeasible result, the implementation roadmap terminates. Phase 11 then publishes Phase 1 and 1B as a negative research portfolio with limitations; it must not claim a production anomaly detector.
