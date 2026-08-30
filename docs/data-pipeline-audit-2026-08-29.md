# Data Pipeline and ML Data Readiness Audit

**Audit date:** 2026-08-29

**Exact checkout:** `2d054c65db8ce63ff6aebbf48d472c5c0586b0fc` (`main`, clean at audit start)

**Scope:** source data, ingestion/replay, Kafka, PostgreSQL, transformations, ML data/evaluation, lineage, governance, monitoring, CI, and release evidence

**Method:** read-only source/configuration review plus local collection and focused tests; no holdout rerun, model retuning, deployment, or remote-CI claim

## Executive verdict

**Production data-pipeline audit: 40/100 — BLOCKED.**

The offline research pipeline has strong foundations for a portfolio project: it freezes the MetroPT-3 source identity, rejects malformed data, records artifacts, preserves the correct `NOT FEASIBLE` model result, and has good unit coverage. The production path is not yet trustworthy, however. The database-backed alert consumer loses the anomaly streak needed to open an alert, a different Parquet file can be relabeled with approved hashes, the Compose replay container points at a path the process never reads, and MLflow can assign the `champion` alias to an unreproduced or `RESEARCH_ONLY` candidate.

This score measures **production data readiness**, not model quality. The truthful negative model result is a strength, not a deduction.

### Weighted score

| Area | Score | Reason |
|---|---:|---|
| Source identity and offline contracts | 13/15 | Frozen UCI identity, checksum, schema, row count, duplicate and ordering rules |
| Ingestion, replay, and streaming | 4/15 | Sound schemas and Kafka primitives, but deployed replay is broken, identity is unauthenticated, and START recovery is not durable |
| Storage and transactional integrity | 6/15 | Good SQL constraints/outbox, but the persisted consumer loses pre-alert state and cannot satisfy the current alert policy |
| Transformations and feature data | 6/15 | Causal design and gap resets are good; one calibration window overlaps train and manifests are trusted |
| ML data and evaluation | 5/15 | Train/calibration fitting is disciplined and the current holdout is contained; calibration isolation and promotion governance are not safe |
| Governance and lineage | 2/15 | Attribution exists, but the runtime trust chain and published certification provenance are not reliable |
| Monitoring and operational proof | 4/10 | Useful metrics/dashboards; consumer lag is unwired, no alert rules, and no complete live data-path certification |

## Actual pipeline traced

| Stage | Implemented flow | Audit status |
|---|---|---|
| Source | UCI MetroPT-3 ZIP → frozen contract | Strong offline source identity |
| Preparation | ZIP/CSV validation → normalized `telemetry.parquet` + manifest | Strong at creation; downstream verification missing |
| Feature build | Prepared Parquet → causal 5-minute bins → 30-minute feature windows | Strong causal design; one train-to-calibration boundary overlap and trusted manifest claims |
| ML evaluation | Train → calibration → locked holdout → explicit feasibility gate | Strong methodology; result is correctly `NOT FEASIBLE` |
| Replay | Parquet → replay commands/status → Kafka telemetry | Container path is broken; actual file hash is never authenticated |
| Online scoring | Kafka telemetry → online features → scoring API → Kafka decisions | Message validation is good; worker replaces event provenance with package provenance |
| Persistence/operations | Decisions → alert state/outbox → PostgreSQL → console/RCA | Transaction model is good, but pre-alert streak state is lost and the current policy cannot open an alert |

## Findings

### P0 — The PostgreSQL-backed consumer cannot open an alert under the committed policy

The committed policy requires two consecutive anomaly decisions (`artifacts/research-candidate/alert-policy.json:9`). For every score, `AlertConsumer` reloads state from PostgreSQL, transitions it, and writes the result (`src/industrial_reliability/alert_consumer.py:93-120`). When no alert row exists, `load_alert_state` returns a fresh empty state (`src/industrial_reliability/persistence.py:190-205`). The first anomaly correctly emits no event below the persistence threshold (`src/industrial_reliability/alert_state.py:152-174`), so `record_decision_transition` stores only the decision and does not persist the updated streak state (`src/industrial_reliability/persistence.py:240-273`). The second anomaly therefore starts again at streak one.

**Impact:** two or more consecutive anomalies produce no `OPENED` event, outbox row, operator alert, or RCA, even though the locked policy is satisfied. This breaks the central data-to-action path.

**Minimum correction:** persist the complete `AlertState` for every committed decision, including pre-alert anomaly/normal streaks and contributing decision IDs, in the same transaction as the decision. Alternatively, reconstruct the streak deterministically from persisted decisions; do not keep it only in process memory.

**Required check:** with real PostgreSQL, two consecutive anomalous decisions under the committed policy must create exactly one alert/event/outbox record, survive process restart between decisions, and remain idempotent on redelivery.

### P0 — Runtime data lineage can assert a false dataset identity

The replay API obtains `source_dataset_sha256` and `contract_sha256` from the scoring package, not from the replay source (`src/industrial_reliability/api.py:324-335`). `ReplaySource` checks only that a Parquet file exists and then reads it (`src/industrial_reliability/replay.py:184-186`, `198-212`); it never hashes the file or verifies its preparation manifest. It copies the command's claimed hashes into every telemetry event (`src/industrial_reliability/replay.py:233-238`). The worker then initializes its feature builder with hashes from its own model package rather than the decoded event (`src/industrial_reliability/worker.py:366-372`).

**Impact:** a wrong, stale, or tampered Parquet file can be processed and emitted as if it were the approved MetroPT-3 snapshot. Feature vectors, scores, alerts, and downstream evidence inherit a plausible but unauthenticated lineage label. The hashes are metadata, not proof.

**Minimum correction:** add one shared verifier that checks the prepared manifest self-hash, hashes the actual Parquet bytes, checks the frozen contract hash, and returns the verified identity. Use that identity in replay events. At the worker boundary, require event hashes to equal the scoring package contract/dataset hashes; quarantine mismatches instead of replacing them.

**Required check:** a modified Parquet byte or mismatched manifest must prevent replay before the first Kafka telemetry message; a mismatched telemetry identity must be quarantined and never scored.

### P0 — MLflow `champion` promotion bypasses feasibility and reproduction

`ChampionManifest` intentionally permits both a feasible `CHAMPION` and a `NOT_FEASIBLE`/`RESEARCH_ONLY` package (`src/industrial_reliability/package_champion.py:48-81`). `import_candidate` accepts either and tags it simply as `candidate` (`src/industrial_reliability/ml_lifecycle.py:174-186`, `217-228`). `promote_candidate` checks only `lifecycle_state == "candidate"` (`src/industrial_reliability/ml_lifecycle.py:442-451`), does not require a reproduction run or PASS gate, does not compare the run SHA with `expected_source_git_sha`, and sets the registry `champion` alias before optional package inspection (`src/industrial_reliability/ml_lifecycle.py:453-474`). The receipt timestamp is also hard-coded (`src/industrial_reliability/ml_lifecycle.py:488`).

`evaluate_phase7_gate` compares dataset, contract, feature-schema, and package hashes, but not the candidate/reproduction Git SHA, alert-policy hash, or receipt Git SHA even though those fields are collected (`src/industrial_reliability/phase7_gate.py:85-109`). `run_phase7_gate` consumes an already-existing promotion receipt, so it audits after the alias can already have been assigned (`src/industrial_reliability/phase7_gate.py:166-205`).

**Impact:** the registry can call an unreproduced research-only package `champion`, contradicting the repository's truthful negative-result contract. Runtime loading still rejects `RESEARCH_ONLY` by default, but the registry and promotion receipt can make a false governance claim.

Model logging failures are also swallowed while import still returns a model URI (`src/industrial_reliability/ml_lifecycle.py:269-286`). Promotion mutates the alias before writing the receipt (`src/industrial_reliability/ml_lifecycle.py:458-492`), while receipt writing refuses an existing destination (`src/industrial_reliability/ml_provenance.py:222-230`); a failed receipt write can therefore leave registry state changed with no receipt or rollback target.

**Minimum correction:** make promotion require a verified Phase 7 PASS artifact tied to the same run/package, exact requested Git SHA equality, `package_role=CHAMPION`, `evaluation_verdict=FEASIBLE`, and `operational_status=PRODUCTION_CANDIDATE`. Verify the logged model is present/READY. Perform all checks before mutation and either write a pending receipt first or compensate alias/version changes on failure. Record the previous alias/version and current UTC time.

**Required check:** a `RESEARCH_ONLY` package, missing reproduction, Git mismatch, alert-policy mismatch, or FAIL gate must create no model version, no alias, and no receipt.

### P1 — One calibration window contains train-period samples

Phase 1B assigns a bin's split using only its `bin_end` (`src/industrial_reliability/phase1b_features.py:59-68`, `170-187`). A five-minute bin ending exactly at a split boundary is assigned to the later split even though its samples cover the preceding interval. The six-bin window is then labeled from that split, with `window_start` computed as the first bin end minus one stride (`src/industrial_reliability/phase1b_features.py:119-145`). Direct inspection of the current local feature artifact found exactly one crossing window: the first calibration window starts `2020-02-21 23:55` while calibration begins at `2020-02-22 00:00`. The same check found zero crossing holdout windows; the first holdout window is `2020-03-01 04:00` to `04:30`. Existing tests check continuity but not full-window containment (`tests/test_phase1b_features.py:40-59`).

**Impact:** calibration is not strictly independent from training, so one threshold-selection window reuses five minutes of train-period data. The published holdout artifact is contained, so this audit found no direct train/calibration sample leakage into its holdout windows. Any regenerated evaluation should still be versioned rather than silently replacing the viewed result.

**Minimum correction:** classify/retain a bin only when its entire sample interval lies within one split, and emit a window only when `split.start <= window_start` and `window_end <= split.end`. Add boundary tests first.

**Required check:** no train, calibration, or holdout window may contain a timestamp outside its declared split. Preserve the existing metrics as historical evidence and publish any corrected rerun as a new version.

### P0 — Synthetic gates can be relabeled as release-grade evidence

Phase 8 states that scoring, Kafka, and metrics are in-process doubles (`src/industrial_reliability/phase8_live_gate.py:100-105`) but rejects only the literal `LIVE`; callers may label the same drill `INTEGRATION` (`src/industrial_reliability/phase8_live_gate.py:111-157`). Phase 9 selects `LIVE_OPENAI` from API-key presence alone (`src/industrial_reliability/phase9_live_gate.py:52-60`), while its checks can run with doubles and synthetic evidence. Release validation accepts report-declared `INTEGRATION` or `LIVE` plus schema/hash/check fields (`src/industrial_reliability/release_certification.py:154-184`) rather than authenticating contacted dependencies.

**Impact:** synthetic data-path/provider checks can satisfy mandatory release evidence without Kafka, PostgreSQL, scoring API, or a provider call.

**Minimum correction:** gate code must derive evidence level from observed dependency receipts, not a caller string or key presence. Record endpoint/provider identity, request/response or broker/database proof, exact SHA, and semantic assertions. Keep in-process doubles permanently labeled `IN_PROCESS`.

**Required check:** no command-line argument or dummy key may upgrade synthetic evidence to `INTEGRATION`/`LIVE`; release certification must fail without authentic dependency receipts.

### P1 — The Compose replay producer cannot find its mounted data

Compose mounts `./data/processed/phase1b` at `/runtime/data` and sets `REPLAY_PARQUET_PATH=/runtime/data/metropt3/telemetry.parquet` (`compose.yaml:70-80`). The service command supplies no `--parquet`. The CLI defines only a hard-coded default `data/processed/phase1b/metropt3/telemetry.parquet` and never reads `REPLAY_PARQUET_PATH` (`src/industrial_reliability/replay_service.py:372-383`, `408-410`). The image working directory is `/app` (`Dockerfile:2`), so the resolved default is not the mounted file.

**Impact:** the documented Compose pipeline fails at its first data hop with `FileNotFoundError`.

**Minimum correction:** either add `--parquet /runtime/data/metropt3/telemetry.parquet` to the Compose command or make the existing CLI default read `REPLAY_PARQUET_PATH`. One configuration path is enough.

**Required check:** a Compose configuration test must prove that the process argument/default resolves to the mounted file.

### P1 — Replay START is acknowledged before the session has durable recovery state

The replay consumer handles START by creating an in-memory background task (`src/industrial_reliability/replay_service.py:173-208`). The outer loop then commits the command offset immediately after `handle_command_record` returns (`src/industrial_reliability/replay_service.py:132-140`). Session/controller state exists only on the process object, and although `ReplaySource` supports `start_sequence` and `resume_from_timestamp`, the service invokes it without either (`src/industrial_reliability/replay.py:189-204`; `src/industrial_reliability/replay_service.py:260-300`).

**Impact:** a crash after the command commit but before `COMPLETED` abandons the replay session. Restart neither redelivers START nor resumes the last Parquet coordinate; downstream data can be silently incomplete.

**Minimum correction:** persist the accepted command and replay checkpoint before committing its Kafka offset. On restart, resume from the last published sequence/timestamp with deterministic IDs, or deliberately replay from the start and prove downstream deduplication.

**Required check:** crash after N telemetry events, restart, and prove exactly one logical completed stream with no missing decisions/alerts.

### P1 — Offline stages carry hashes without verifying the artifacts they describe

The preparation stage computes a Parquet hash and manifest self-hash. The feature stage then reads `manifest.json` and `telemetry.parquet` directly without verifying either hash (`src/industrial_reliability/phase1b_features.py:224-236`), while copying the claimed manifest hash into its own manifest (`src/industrial_reliability/phase1b_features.py:270-276`). The benchmark similarly reads both manifests and the features Parquet without checking the feature output hash or either manifest self-hash (`src/industrial_reliability/phase1b_benchmark.py:174-192`). Reproduction reads the supplied features file without verifying it against the package/source manifests (`src/industrial_reliability/ml_lifecycle.py:290-322`).

**Impact:** artifacts can change between stages while later reports still carry the original hashes. Reproducibility and tamper evidence stop at artifact creation.

**Minimum correction:** reuse one canonical manifest verifier at every consumer boundary. Do not add a new framework.

**Required check:** tampering separately with prepared Parquet, prepared manifest, feature Parquet, or feature manifest must fail at the next stage.

### P1 — Published release evidence is stale and overclaims runtime certification

The checked-in certification uses an all-zero Git SHA while declaring `is_certified: true` (`docs/results/release-certification.json:3-5`, `23`) and says the replay/streaming/alert pipeline is fully functional and certified (`docs/results/release-certification.json:27`; `docs/results/release-certification.md:15`). It predates the current exact HEAD and cannot authenticate it. Current certification code has stricter evidence-level checks, but the published artifact was not regenerated under those rules.

**Impact:** readers can mistake an older self-hashed report for exact-SHA runtime proof even though the deployed replay path currently fails and no complete live path was verified in this audit.

**Minimum correction:** regenerate only after the blocking fixes and a real dependency-backed run. Require nonzero exact Git SHA, pushed-commit provenance, semantic evidence, and explicit `INTEGRATION`, `LIVE`, and `RELEASE` labels.

### P1 — CI does not exercise a complete production data path

The quality job runs `pytest -m "not slow and not integration"`; the integration job runs only `pytest -m "integration"` (`.github/workflows/ci.yml:32`, `87-91`). Current collection selects only **7 of 460** tests for the integration job. `tests/integration/test_console_stream_persistence.py` is a real PostgreSQL test but has no integration marker (`tests/integration/test_console_stream_persistence.py:16-44`), so it is deselected from the integration job and skipped in the dependency-free quality job. The Kafka online-worker integration test uses an in-process scoring client rather than the HTTP/Compose service (`tests/integration/test_online_worker.py:70-96`).

**Impact:** green CI would not prove Parquet → replay container → Kafka → HTTP scoring → alert/outbox → PostgreSQL → console persistence at one exact SHA.

**Minimum correction:** mark the missing real-dependency test and add one narrow Compose/live test for the full critical path. Keep component tests; do not duplicate their assertions.

### P2 — Database lifecycle and recovery are incomplete

Fresh PostgreSQL volumes receive the three SQL files through `/docker-entrypoint-initdb.d` (`compose.yaml:10-12`), and the schema itself has good relational constraints (`db/migrations/001_alert_lifecycle.sql:3-62`; `002_console_stream.sql:1-12`; `003_rca_reports.sql:1-13`). There is no repeatable migration/version table or upgrade command for an existing volume. The runbook's manual commands name two files that do not exist (`docs/RUNBOOK.md:22-26`). No backup, restore drill, retention policy, archival, or deletion procedure was found.

**Impact:** schema upgrades can drift across persistent environments, and operational data has no tested recovery or lifecycle policy.

**Minimum correction:** add the smallest repeatable ordered migration runner with a schema-version table, correct the two runbook filenames, document retention, and leave one restore drill artifact.

### P2 — Data monitoring has dashboards but incomplete or unbound signals and no automated alarms

The code defines `irp_kafka_consumer_lag` (`src/industrial_reliability/metrics.py:107-110`) and Grafana displays it (`ops/grafana/dashboards/system.json:212`), but no runtime caller invokes `set_consumer_lag`; the method exists only in `metrics.py:69-70`. PSI is calculated only when a drift reference is loaded, but Compose neither mounts nor configures `DRIFT_REFERENCE_PATH` (`src/industrial_reliability/worker.py:468-477`; `compose.yaml:85-97`). Runtime also loads the reference without binding it to the active package manifest even though the loader supports that validation (`src/industrial_reliability/drift.py:196-208`); no-overlap can yield PSI `0.0` (`src/industrial_reliability/drift.py:85-97`). Quarantine, duplicate, segment-break, and coverage metrics are otherwise useful. No Prometheus alert rules or notification route was found under `ops/`.

**Impact:** lag can remain meaningless and shipped PSI can be absent or falsely healthy for the wrong reference; the runbook's conditions require a human watching dashboards.

**Minimum correction:** calculate lag from assigned partitions/high watermarks, mount a manifest-bound drift reference, fail closed on zero feature overlap, and add a small rules file for nonzero quarantine, sustained lag, coverage loss, and PSI threshold.

### P2 — Invalid score records are committed away without durable quarantine evidence

Malformed score decoding returns `QUARANTINED` after logging only (`src/industrial_reliability/alert_consumer.py:93-100`). The alert-service loop commits every outcome except `SESSION_FAILED`, so the invalid record is not redelivered, while no quarantine topic or PostgreSQL audit row is written (`src/industrial_reliability/alert_service.py:157-169`). Existing tests assert only the enum outcome.

**Impact:** malformed score inputs are permanently discarded and cannot be audited or replayed.

**Minimum correction:** publish the original payload hash/topic/partition/offset and bounded error to the existing quarantine contract before committing the score offset.

### P2 — The data contract documents units but does not enforce physical plausibility or time semantics

The data card documents pressure, temperature, and current units (`docs/DATA_CARD.md:18-35`). The executable Phase 1B contract freezes columns and split dates but no units, physical ranges, timezone, or freshness SLA (`src/industrial_reliability/phase1b_contracts.py:26-55`). Preparation rejects non-finite analog values and non-binary digital values but accepts any finite analog magnitude (`src/industrial_reliability/phase1b_data.py:106-118`).

**Impact:** unit swaps or impossible sensor values can enter the validated dataset and be interpreted as real anomalies.

**Minimum correction:** freeze units and conservative physical plausibility ranges in the existing contract. Reject clear sensor sentinels; quarantine uncertain extremes instead of silently clipping them.

## What is already strong

- **Source identity:** DOI, license, URL, archive checksum, member name, row count, and exact columns are frozen (`src/industrial_reliability/phase1b_contracts.py:70-96`). ZIP traversal and wrong-source failures are explicit (`src/industrial_reliability/phase1b_data.py:217-247`).
- **Data-quality behavior:** non-finite analogs, non-binary states, conflicting duplicates, non-monotonic timestamps, and row-count changes fail closed (`src/industrial_reliability/phase1b_data.py:81-145`). Identical duplicates are explicitly counted rather than hidden.
- **Leakage-control intent:** train, calibration, and holdout ranges are temporal; causal windows do not interpolate across gaps (`docs/DATA_CARD.md:39-49`). Model fitting is train-only and threshold fitting is calibration-only. The current holdout windows are contained, but the one train-to-calibration overlap must be fixed before claiming strict partition isolation.
- **Truthful model outcome:** the published result is `NOT FEASIBLE` with `selected_model: null` (`docs/results/phase-1b-metrics.json:5-6`). Research packages are labeled `RESEARCH_ONLY`, and scoring/worker startup rejects them unless explicitly enabled (`src/industrial_reliability/worker.py:101-108`).
- **Runtime schemas:** frozen Pydantic messages reject extra fields, malformed hashes, unequal feature vectors, and non-finite values (`src/industrial_reliability/runtime_messages.py:59-96`, `119-141`).
- **Kafka and state integrity:** idempotent producers, manual consumer commits, quarantine records, session barriers, relational uniqueness, and the transactional alert outbox are solid foundations (`src/industrial_reliability/replay_service.py:71-85`, `135-140`; `src/industrial_reliability/worker.py:323-338`; `db/migrations/001_alert_lifecycle.sql:15-62`).
- **Operational visibility:** dashboards cover accepted/quarantined/duplicate traffic, segment breaks, coverage, dependency readiness, and PSI (`ops/grafana/dashboards/data-quality.json`; `model-machine.json`; `system.json`).

## Capability matrix against the proposed Data spine

| Layer | Current maturity | Portfolio interpretation |
|---|---|---|
| 1. Data Source | Strong | Real, licensed, hash-pinned sensor dataset; no live sensor/API/CDC source |
| 2. Data Ingestion | Partial | Batch preparation and Kafka replay exist; deployed replay path and identity verification block production |
| 3. Data Storage | Partial | Local raw/validated files, PostgreSQL, and volumes exist; no durable object store/warehouse or recovery lifecycle |
| 4. Data Modeling | Moderate | Good normalized operational schema; no analytical fact/dimension or SCD model, which is optional here |
| 5. Data Quality | Moderate | Excellent structural/time/duplicate checks; missing physical range, unit, timezone, freshness, and durable invalid-score quarantine |
| 6. Data Transformation | Moderate-strong | Causal feature engineering and gap segmentation; split-boundary containment and boundary hashes are unsafe |
| 7. Data for ML | Moderate | Train/calibration methodology, current holdout containment, and negative-result honesty are strong; one calibration window overlaps train and promotion governance is unsafe |
| 8. Data for LLM | Out of scope | RCA consumes structured evidence; this repo is not a document/RAG corpus pipeline |
| 9. Data Evaluation | Weak-moderate | Frozen holdout intent and benchmarks exist; calibration overlap and relabelable synthetic evidence block certification |
| 10. Data Governance | Weak | License/attribution and hashes exist; lineage authentication, evidence authenticity, retention, recovery, and access policy are incomplete |
| 11. Data Monitoring | Moderate | Quality/drift dashboards exist; lag is unwired and no automated alerting |

## Evidence classification

| Evidence | Result | Classification |
|---|---|---|
| Resumed full local suite at the same exact SHA | 450 passed, 1 PostgreSQL test skipped, 9 deselected; 86.79% coverage | `UNIT` / `IN_PROCESS`; not live certification |
| Local artifact identity | Source ZIP, prepared telemetry Parquet, and feature Parquet each match the SHA-256 declared by their current contract/manifest | Local integrity check; downstream consumers still do not enforce it |
| Split containment on current feature artifact | Train: 0 crossing windows; calibration: 1; holdout: 0 | Local artifact inspection; confirms calibration overlap but not holdout leakage |
| Integration collection | 7/460 tests selected | Test inventory only |
| Compose render | Valid configuration; confirms replay env/mount mismatch | Static deployment configuration evidence |
| PostgreSQL availability in this audit | Unavailable in the resumed local run | No current local PostgreSQL integration result |
| Kafka/MLflow/full Compose stack | Not started in this audit | No `LIVE` evidence |
| Remote CI / deployed environment | Not checked | No remote exact-SHA or production claim |

## Prioritized remediation roadmap

### Gate A — restore data identity and truthful promotion

1. Persist pre-alert streak state transactionally so the committed two-decision policy can open an alert across calls/restarts.
2. Add split-containment tests and fix bin/window assignment; preserve the viewed metrics and version any corrected rerun.
3. Reuse one manifest/artifact verifier at preparation → features → benchmark → reproduction → replay boundaries.
4. Make replay hash the actual Parquet source and make the worker reject event/package identity mismatches.
5. Make promotion consume a verified Phase 7 PASS artifact and enforce feasible production-package semantics before registry mutation.
6. Prevent caller-controlled evidence relabeling in Phase 8/9/release gates.
7. Fix the replay path by using the existing environment variable or an explicit Compose argument.

**Exit:** two decisions open one durable alert across restart; every window is fully inside its split; all tamper tests fail closed; research-only promotion produces no registry mutation; synthetic evidence cannot certify; Compose replay emits the first verified event.

### Gate B — earn integration evidence

1. Correct the console-persistence marker and classify tests by actual dependency level.
2. Add one full-path test through real Kafka, HTTP scoring, multi-decision alert/outbox, PostgreSQL, and console persistence.
3. Regenerate certification only for the exact pushed SHA, with explicit evidence levels and dependency identities.

**Exit:** exact-SHA CI and a local dependency-backed run both prove the critical path; no simulated component is labeled `LIVE`.

### Gate C — data operations

1. Add repeatable schema-versioned migrations and fix runbook filenames.
2. Define retention for Kafka, telemetry-derived events, predictions, evidence, and RCA reports.
3. Perform and record one PostgreSQL backup/restore drill.
4. Wire real consumer lag and add four small Prometheus alert rules.

**Exit:** an existing volume upgrades safely, restore meets a documented RPO/RTO, and an injected lag/quarantine condition produces an alert.

### Gate D — portfolio depth, only after A-C

1. Freeze units, physical ranges, timezone, and freshness in the existing contract.
2. Publish a compact data-quality profile by split and sensor: nulls, duplicates, gaps, range violations, and drift baseline.
3. Add a lineage diagram showing source archive → prepared Parquet → feature snapshot → model package → replay/session → decision/alert.
4. Add warehouse/star-schema or Spark only if a real analytical or scale requirement appears; neither is needed to fix current correctness.

## Re-audit done criteria

- Actual replay bytes, manifest, event envelope, feature vector, model package, and receipt agree on one verified identity.
- The committed persistence policy opens exactly one durable alert after two consecutive anomalies, including across restart.
- Every train/calibration/holdout window is wholly contained in its declared split; existing viewed metrics are not silently replaced.
- No `RESEARCH_ONLY` or `NOT_FEASIBLE` package can acquire `champion` under any API/CLI path.
- Synthetic checks cannot be relabeled `INTEGRATION` or `LIVE` by arguments, environment values, or dummy credentials.
- Fresh and existing database volumes have a tested migration path; backup/restore and retention are documented and exercised.
- The full data path passes with real dependencies at the exact pushed SHA.
- Consumer lag, quarantine, coverage, and PSI have live values and alert rules.
- Published certification names the exact SHA and honestly distinguishes `UNIT`, `IN_PROCESS`, `INTEGRATION`, `LIVE`, and `RELEASE` evidence.

## Audit self-evaluation

| Axis | Score | Evidence / remaining limitation |
|---|---:|---|
| Accuracy | 4/5 | Findings were cross-checked against exact source lines, Compose rendering, and tests; no live stack was run, so live behavior is not claimed |
| Completeness | 5/5 | Covers the requested end-to-end Data spine, ML data, storage, governance, monitoring, evidence, and roadmap |
| Clarity | 4/5 | Defect-first structure and stage matrix are explicit; the report is necessarily long because the user requested a full audit |
| Actionability | 5/5 | Every blocking finding includes a minimum correction and a runnable acceptance condition |
| Conciseness | 4/5 | Repetition is limited, but detailed evidence and the capability matrix add length |

**Overall:** 4.4/5. No axis is 3 or below. The main confidence ceiling is the deliberately absent live dependency run.

**Critical output-quality issues:** none.

**Self-check:** the user should agree because every production claim is tied to exact local evidence and missing live/remote validation is disclosed rather than inferred.

**Self-evaluation verdict:** deliver as-is; refresh the evidence after Gates A-C rather than expanding this report speculatively.
