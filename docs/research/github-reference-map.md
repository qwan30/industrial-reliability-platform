# GitHub Reference Map

## Purpose and decision

[Project source] The master specification treats reference repositories as influences rather than a source-copying plan and requires this project to own its data contract, feature definitions, temporal split, leakage controls, threshold and alert policies, evaluation, API contracts, integration, and documentation (`docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md:1490-1617`, Sections 31-32).

[Inference] The resulting decision is:

- Use `metroguard-ml` intensively in Phase 1 to learn and independently reproduce a defensible experimental methodology.
- Keep `iot-streaming-pipeline` and most of `mlops-zoomcamp` outside Phase 1. They are later-phase reading and backlog inputs, not dependencies or templates.
- Do not copy source, configuration, prose, dashboards, artifacts, data extracts, or workflow files from any reference. No inspected repository item qualifies for direct `REUSE LIBRARY/API`; use the upstream libraries through their own public APIs when the relevant project phase arrives.

## Evidence conventions and inspection boundary

- `[Reference repository]` means a claim observed in one of the three local reference worktrees at the recorded commit.
- `[Project source]` means a claim or requirement from the current master specification.
- `[Inference]` means a recommendation derived from those sources.
- `[Unknown/unsupported]` means the local files do not establish the claim.

[Reference repository] Inspection was read-only and limited to these three local repositories. No web lookup, fetch, pull, checkout, dependency installation, or workload execution was performed. Source citations below are repository-relative and refer to the exact commit recorded for that repository.

## Phase 1 scope gate

[Project source] Phase 1 must answer whether abnormal periods around known MetroPT events can be detected with leakage-safe evaluation. Its build list is dataset acquisition, schema inspection, temporal splitting, feature extraction, a robust statistical baseline, Isolation Forest, a simple PyTorch autoencoder, and event-level evaluation. Its exit criteria are a reproducible benchmark, no random time-series split, documented limitations, and measured metrics (`docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md:1735-1763`, Section 35, Phase 1).

[Inference] Therefore Phase 1 may borrow only methodological questions and test ideas from MetroGuard. It must not add Kafka, Spark, TimescaleDB, Grafana, a production FastAPI service, Airflow, MLflow infrastructure, cloud deployment, OpenVINO, or an LLM/RCA service. The streaming repository and Zoomcamp should produce no Phase 1 code, configuration, dependency, service, or acceptance criterion.

[Project source] This gate is also required by the principles “ML before infrastructure,” “simple baseline first,” and “temporal correctness over impressive accuracy” (`docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md:2067-2087`, Section 41), and by the next-session instruction to resolve only the exact Phase 1 dataset, features, split, models, threshold, metrics, leakage tests, and streaming-readiness criteria (`docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md:2322-2355`, Section 48).

## 1. `metroguard-ml`

### Provenance and licensing

[Reference repository]

| Field | Observed value |
|---|---|
| Repository | `metroguard-ml` |
| Local origin | `https://github.com/firathdr/metroguard-ml.git` |
| Exact local commit | `bd5e87fc3299f58e0125f399a938a0dea57c4874` |
| Branch/worktree | `main`, tracking `origin/main`; `git status --short --branch` showed `## main...origin/main` and no changed or untracked entries |
| Code license | MIT; `LICENSE:1-20` grants use/modification/distribution subject to retaining the copyright and permission notice, and `pyproject.toml:5-13` identifies the package and license |
| Data/material license | The repository states that MetroPT-3 and `data/demo/replay.csv` are CC BY 4.0 and require attribution (`DATA_CARD.md:3-13`; `data/README.md:1-23`) |

[Inference] MIT permits adaptation but does not remove attribution/notice duties for copied substantial portions. The safest and most portfolio-defensible route is independent implementation with an influence citation. Do not copy the committed replay extract or generated artifacts: they are not needed, and the repository itself identifies separate data licensing.

### Item map

All source observations in this subsection are at commit `bd5e87fc3299f58e0125f399a938a0dea57c4874`.

| Important item | Problem it solves and reusable design idea | Primary classification | Phase and exact master-spec mapping | Caveat / what must not be copied |
|---|---|---|---|---|
| `DATA_CARD.md`; `data/README.md`; `configs/default.yaml:6-24`; `src/metroguard/data.py:20-106`; `src/metroguard/schema.py:9-89` | [Reference repository] Pins a source URL and checksum, records a DOI, normalizes the actual schema, measures cadence/coverage, preserves warnings, and documents incident provenance and dataset limitations. The reusable idea is to make dataset understanding and provenance executable rather than leaving it in a notebook. | **LEARN METHODOLOGY** | [Project source] Phase 1; Sections 8.1 (primary dataset), 18 (data quality), 35 Phase 1, 36 (download/checksum/version), 37 data tests, and 48 items 1-3. | [Inference] Do not copy the MetroPT-3 DOI, SHA-256, column aliases, sensor list, cadence, event table, or February/September boundaries. This project targets a separately selected MetroPT release and must verify its own official files and meanings. |
| `src/metroguard/features.py:19-66`; `tests/test_schema_features.py:32-47` | [Reference repository] Builds right-closed causal bins, separates analog statistics from digital state behavior, calculates coverage, and explicitly prevents coverage from becoming a predictive feature. A test demonstrates that future values are not backfilled. | **ADAPT PATTERN** | [Project source] Phase 1; Section 10 Step 3, Sections 14 and 18, Section 35 Phase 1, Section 37 leakage tests, and Section 48 items 5 and 11. | [Inference] Re-derive every feature from this project's data card and operating question. Do not copy five-minute bins, expected sample counts, the two pressure-difference features, or the exact feature names/statistics. |
| `src/metroguard/windows.py:14-81`; `configs/default.yaml:13-24`; `tests/test_windows_models.py:21-43` | [Reference repository] Constructs only consecutive, high-coverage causal windows and assigns a window to a split only when the whole window is inside that split. Purged chronological boundaries prevent a sequence from crossing train/calibration/test partitions. | **ADAPT PATTERN** | [Project source] Phase 1; Section 14 (train/calibration/holdout roles), Section 35 Phase 1, Section 37 leakage tests, Section 47 open questions 4-5, and Section 48 items 4 and 11. | [Inference] Keep the invariant, not the dates or dimensions. The exact split boundaries, purge duration, window size, normal-period definition, and gap policy must be justified from the selected dataset. |
| `src/metroguard/models.py:19-208`; `configs/default.yaml:26-33`; `tests/test_windows_models.py:45-82` | [Reference repository] Implements a simple-to-complex comparator ladder, fits scaling on train data, normalizes scores robustly, and checks deterministic scoring and autoencoder output/contribution shapes. | **LEARN METHODOLOGY** | [Project source] Phase 1; Sections 11-12, Section 35 Phase 1, Section 41 Principles 2, 6, and 7, and Section 48 items 6-8. | [Inference] Do not copy the 300-tree forest, PCA comparator, TCN architecture, bottleneck, optimizer settings, seed as a substitute for reproducibility, or committed weights. The master spec currently calls for a simple first autoencoder and leaves dense-versus-temporal architecture open. |
| `src/metroguard/pipeline.py:292-369`; `src/metroguard/alerts.py:19-107`; `configs/default.yaml:35-43`; `tests/test_alerts_metrics.py:11-21` | [Reference repository] Separates raw model score, calibration-only normalization/threshold selection, causal smoothing, persistence, episode merging, cooldown, and final operational alert state. | **ADAPT PATTERN** | [Project source] Phase 1 owns threshold calibration (Sections 14 and 48 item 9); full operational policy belongs to Section 16 and Phase 4 in Section 35. | [Inference] In Phase 1, implement only enough episode logic to evaluate the detector. Do not adopt `q=0.995`, EWMA `0.2`, 3-of-4, 30-minute merge, six-hour cooldown, or 24-to-2-hour warning windows without project-specific calibration. |
| `src/metroguard/metrics.py:12-142`; `reports/metrics.json`; `reports/event_results.csv`; `reports/horizon_sensitivity.csv`; `MODEL_CARD.md:29-45` | [Reference repository] Evaluates alert episodes against named events, reports event recall as an absolute count, measures lead time, false alarms per normal exposure day, time in alert, PR-AUC, and horizon sensitivity, and distinguishes signal contributions from causal explanations. | **LEARN METHODOLOGY** | [Project source] Phase 1; Section 15, Section 35 Phase 1, Section 41 measured-claims rule, Section 46 decisions 9-10, and Section 48 item 10. | [Inference] Do not copy the four hard-coded MetroPT-3 incidents (`src/metroguard/metrics.py:19-24`), the early/late window, published metric values, plots, or prose. Independently define event association, normal exposure, overlapping-event behavior, uncertainty, and acceptance thresholds. |
| `src/metroguard/pipeline.py:392-470`; `src/metroguard/artifacts.py:23-66`; `DATA_CARD.md`; `MODEL_CARD.md`; `README.md:125-144` | [Reference repository] Bundles schema/model/threshold metadata, records Git and dataset provenance, generates reports, and keeps notebooks thin while package code holds executable logic. | **ADAPT PATTERN** | [Project source] Phase 1 reproducibility and limitations; Section 23 and Phase 5 later add MLflow; Section 32 requires owned documentation and benchmark methodology; Phase 9 adds cards and portfolio artifacts. | [Inference] In Phase 1, a small manifest plus data/model notes is sufficient. Do not copy serialized `joblib`/PyTorch artifacts, generated reports, dashboard assets, or the 477-line pipeline. Do not load reference `joblib` files: `joblib.load` deserializes executable Python objects (`src/metroguard/artifacts.py:43-47`). |
| `src/metroguard/api.py:26-210`; `docker-compose.yml`; `docker/`; `src/metroguard/dashboard.py` | [Reference repository] Demonstrates bounded historical scoring, strict request fields, artifact availability checks, data-quality output, contributors, and explicit research/root-cause warnings. | **IGNORE FOR NOW** | [Project source] Section 20 and Phase 2 (serving), Section 24 and Phase 6 (monitoring/dashboard), not Phase 1. | [Inference] Do not copy the request/response schema, 75-minute requirement, endpoint names, service topology, Streamlit dashboard, or Docker setup. This project's API must be designed after its own feature/artifact contracts exist. |
| `tests/`; `.github/workflows/ci.yml:9-46`; `pyproject.toml:52-77` | [Reference repository] Supplies small data, leakage, metric, API, determinism, typing, linting, build, coverage, and container checks. | **ADAPT PATTERN** | [Project source] Section 37 and Phase 1 exit criteria; later Phase 2 adds API integration tests. | [Inference] Write tests from this project's invariants rather than copying fixtures/assertions. Also do not reproduce the coverage blind spot: the reference excludes `src/metroguard/pipeline.py` from coverage (`pyproject.toml:57-63`) even though that module coordinates fitting, calibration, evaluation, and artifact generation. |

### Evidence-backed anti-patterns to avoid

- [Reference repository] Dataset-specific facts are embedded in executable constants: MetroPT-3 sensors in `src/metroguard/schema.py:9-49`, calendar splits in `configs/default.yaml:18-24`, and incidents in `src/metroguard/metrics.py:19-24`. [Inference] Copying these would create false confidence rather than adapting methodology to MetroPT 2022.
- [Reference repository] `_candidate_episodes` treats a gap greater than five minutes as a new episode (`src/metroguard/alerts.py:28-42`) while bin duration is separately configurable. [Inference] The project should express episode adjacency in its own policy contract instead of inheriting this hidden coupling.
- [Reference repository] The central training/evaluation pipeline is 477 lines and is omitted from coverage (`src/metroguard/pipeline.py`; `pyproject.toml:57-63`). [Inference] Keep Phase 1 orchestration thin and directly test split, fit-only-on-train, calibration-only thresholding, and holdout-once invariants.
- [Reference repository] Release `joblib` and PyTorch artifacts are committed under `artifacts/release/`, and the loader uses `joblib.load` (`src/metroguard/artifacts.py:43-47`). [Inference] Do not execute or deserialize reference artifacts; train and serialize this project's own artifacts with explicit provenance.
- [Reference repository] The model card correctly admits one APU, four events, uncertain generalization, and non-causal explanations (`MODEL_CARD.md:47-54`). [Inference] Do not turn its reported metrics into targets or claims for this project.

### MetroGuard Phase 1 extraction checklist

[Inference] Extract questions, not answers:

1. What exact official data artifact and checksum are canonical?
2. What does each selected signal mean, what cadence/gaps exist, and which events are authoritative?
3. Which operations are causal at prediction time?
4. How are whole windows purged and assigned chronologically?
5. Which transformations fit only on train, which decisions use calibration, and what is locked before holdout?
6. How are episodes associated with events, false alarms, exposure time, and lead time?
7. What simple baseline must a forest or autoencoder beat?
8. Which automated test fails if any future data leaks backward?

## 2. `iot-streaming-pipeline`

### Provenance and licensing

[Reference repository]

| Field | Observed value |
|---|---|
| Repository | `iot-streaming-pipeline` |
| Local origin | `https://github.com/krishna8399/iot-streaming-pipeline.git` |
| Exact local commit | `92271eb49c27c7938c02ec0333869e8ef0f6f715` |
| Branch/worktree | `main`, tracking `origin/main`; `git status --short --branch` showed `## main...origin/main` and no changed or untracked entries |
| License | No tracked `LICENSE`, `LICENCE`, `COPYING`, or `NOTICE` file and no package license metadata was present. `README.md:226-228` says the academic portfolio project is “All rights reserved.” |

[Inference] Treat the repository as concept-only reading. Do not copy code, Compose fragments, SQL, JSON dashboards, diagrams, or prose. Any similar implementation must be written independently from this project's requirements and official upstream documentation.

### Item map

All source observations in this subsection are at commit `92271eb49c27c7938c02ec0333869e8ef0f6f715`.

| Important item | Problem it solves and reusable design idea | Primary classification | Phase and exact master-spec mapping | Caveat / what must not be copied |
|---|---|---|---|---|
| `producer/config.py:14-95`; `producer/producer.py:46-81,157-211` | [Reference repository] Shows environment-driven producer settings, boundary validation, stable sensor keys, delivery callbacks, retry/backoff, and a DLQ payload for malformed input. | **ADAPT PATTERN** | [Project source] Phase 3; Sections 18, 19.2-19.3, and 38 streaming errors. | [Inference] Implement independently because no reuse license is granted. Replace temperature/humidity/pressure bounds and message fields with the owned MetroPT stream contract; define delivery and DLQ semantics explicitly. |
| `producer/producer.py:83-152`; `.env.example:24-28` | [Reference repository] Replays the CSV forever, fabricates humidity and pressure, and randomly injects anomalies at a configurable default rate. | **DO NOT COPY** | [Project source] Conflicts with Section 8.2 (synthetic telemetry is not headline evidence), Section 19.2 (chronological deterministic replay preserving timestamps), and Section 42 differentiation. | [Inference] The project must replay finite, selected real historical intervals deterministically. Synthetic records belong only in tests/fixtures and must be visibly marked. |
| `spark/streaming_job.py:76-138,175-212,223-250` | [Reference repository] Parses an explicit Kafka schema, derives event time, applies validation, uses a watermark, performs tumbling-window aggregation, and separates raw and aggregate streaming queries. | **LEARN METHODOLOGY** | [Project source] Phase 3; Section 19.4 and Section 10 Steps 2-3. | [Inference] Do not copy the schema, five/ten-minute choices, filters, JDBC callbacks, or code. The future Spark path must reproduce the already-approved offline feature contract and define late-data behavior from measured replay characteristics. |
| `db/init.sql:4-82`; `api/main.py:180-267`; `api/models.py:13-80` | [Reference repository] Demonstrates raw/aggregate time-series tables, indexes, a hypertable/continuous aggregate, parameterized queries, and history relative to the newest stored event rather than wall clock—useful for historical replay. | **IGNORE FOR NOW** | [Project source] Storage in Section 17, serving in Section 20/Phase 2, persistence in Phase 3, and monitoring in Phase 6. | [Inference] Do not select TimescaleDB, tables, retention, indexes, API fields, or query windows during Phase 1. Design them only after the telemetry, feature, model, and alert contracts are owned. |
| `docker-compose.yml`; `grafana/provisioning/`; `docs/architecture_diagram.png`; `README.md:126-212` | [Reference repository] Assembles nine local services with health-based startup, named volumes, Kafka UI, TimescaleDB, Grafana provisioning, producer, Spark, and API. | **IGNORE FOR NOW** | [Project source] Phase 3 and Phase 6; Section 33 architecture; Section 40 rejects custom production clusters; Section 41 says every tool needs a reason. | [Inference] Do not import the nine-container topology, ports, dashboard JSON, latest image tags, credentials pattern, or architecture diagram into Phase 1. Add one later-phase service at a time against a proven requirement. |

### Evidence-backed anti-patterns to avoid

- [Reference repository] The producer enriches real temperature rows with simulated signals and random anomalies (`producer/producer.py:101-152`). [Inference] This would undermine the project's real-telemetry ML claims and distort event evaluation.
- [Reference repository] Replay loops indefinitely over unchanged historical timestamps (`producer/producer.py:83-98`), raw storage has no event uniqueness constraint (`db/init.sql:7-15`), aggregate storage has a `(sensor_id, window_start)` primary key (`db/init.sql:31-45`), and Spark appends JDBC batches (`spark/streaming_job.py:141-170`). [Inference] A copied design risks duplicate raw facts and aggregate write failures; the project must define replay IDs, idempotency, and reset/resume behavior.
- [Reference repository] Spark checkpoints live under `/tmp/spark-checkpoints` (`spark/streaming_job.py:63,223-247`), the streaming service has no checkpoint volume in `docker-compose.yml:136-164`, and Kafka reading sets `failOnDataLoss` to false (`spark/streaming_job.py:99-108`). [Inference] Do not claim durable restart or complete evidence without persistent checkpoints and explicit data-loss policy.
- [Reference repository] Spark quality checks silently filter invalid parsed rows (`spark/streaming_job.py:126-138`); the Spark module never writes the configured DLQ topic. [Inference] The project must make rejected-message disposition observable and testable rather than equating filtering with governance.
- [Reference repository] Compose uses mutable `latest` tags for TimescaleDB, Grafana, and Kafka UI (`docker-compose.yml:169-223`), exposes multiple host ports, and uses a single plaintext local broker. [Inference] These are local-demo choices, not reproducible or production-security patterns.
- [Reference repository] No tests or CI workflow are present in the tracked tree. [Inference] Do not inherit its reliability claims without contract, replay, idempotency, late-data, and restart tests.

## 3. `mlops-zoomcamp`

### Provenance and licensing

[Reference repository]

| Field | Observed value |
|---|---|
| Repository | `mlops-zoomcamp` |
| Local origin | `https://github.com/DataTalksClub/mlops-zoomcamp.git` |
| Exact local commit | `3ba475fa5e2066ef566d6e452b5a76e1ecf7df41` |
| Branch/worktree | `main`, tracking `origin/main`; `git status --short --branch` showed `## main...origin/main` and no changed or untracked entries |
| License | [Unknown/unsupported] No tracked `LICENSE`, `LICENCE`, `COPYING`, or `NOTICE` file was present. The inspected `06-best-practices/code/pyproject.toml:1-19` contains only lint/format configuration and no package/license metadata; the root README has no license section. |

[Inference] No local explicit reuse grant was established. Treat code, notebooks, diagrams, prose, workflows, and infrastructure as study material only; do not copy them. Independently implement applicable practices and consult current official tool documentation when each later phase begins.

### Item map

All source observations in this subsection are at commit `3ba475fa5e2066ef566d6e452b5a76e1ecf7df41`.

| Important item | Problem it solves and reusable design idea | Primary classification | Phase and exact master-spec mapping | Caveat / what must not be copied |
|---|---|---|---|---|
| `02-experiment-tracking/` and `02-experiment-tracking/README.md`, Sections 2.1-2.7 | [Reference repository] Teaches experiment tracking, model management, registry concepts, and limitations. It explicitly notes that MLflow APIs and registry stages changed (`02-experiment-tracking/README.md:1-65`). | **LEARN METHODOLOGY** | [Project source] Section 23 and Phase 5; not required for Phase 1. | [Inference] In Phase 1, record a minimal local manifest. Do not add MLflow infrastructure, copy notebooks, or use stage-based registry examples. Verify the current official MLflow API only when Phase 5 starts. |
| `03-orchestration/README.md:1-58` and `03-orchestration/code/` | [Reference repository] Explains the progression from notebook to script to parameterized, backfillable orchestration and presents multiple tool choices. | **IGNORE FOR NOW** | [Project source] Section 22 explicitly says Airflow is unnecessary in Phase 1; Phase 5 introduces the DAG. | [Inference] Do not import Prefect, Mage, Airflow, Docker services, or course flow code now. First make one local Phase 1 command reproducible; orchestrate it later without changing its semantics. |
| `04-deployment/README.md:1-63`; `04-deployment/web-service/`; `04-deployment/streaming/`; `04-deployment/batch/` | [Reference repository] Compares web-service, streaming, and batch deployment shapes and connects model artifacts to scoring services. | **LEARN METHODOLOGY** | [Project source] Phase 2/FastAPI in Section 20, Phase 3 streaming in Section 19, and offline lifecycle in Section 21. | [Inference] Do not copy NYC taxi schemas, Flask handlers, AWS Kinesis/Lambda code, model binaries, Pipfiles, credentials examples, or deployment commands. Select deployment form from this project's scoring and replay contracts. |
| `05-monitoring/README.md:1-77,93-155`; `05-monitoring/post-evidently-0.7/`; `05-monitoring/docker-compose.yml` | [Reference repository] Demonstrates reference-data preparation, metric calculation, dashboarding, data quality, and ad-hoc debugging, while preserving separate examples for Evidently before and after 0.7. | **LEARN METHODOLOGY** | [Project source] Sections 24-25 and Phase 6; not Phase 1 infrastructure. | [Inference] Do not copy taxi metrics, dashboards, Compose, or unpinned post-0.7 requirements. Later define system, data, and model monitoring from this project's failure modes and pin a verified compatible tool version. |
| `06-best-practices/README.md:1-49`; `06-best-practices/code/tests/`; `06-best-practices/code/integration-test/`; `06-best-practices/code/Makefile` | [Reference repository] Teaches unit tests, integration tests, local cloud emulation, linting/formatting, pre-commit, and repeatable commands. | **LEARN METHODOLOGY** | [Project source] Section 37 applies immediately; Phase 2 adds API integration and later phases add deployment tests. | [Inference] Apply the testing layers to owned Phase 1 invariants, but do not copy course tests, data blobs, model artifacts, shell scripts, or Make targets. Use the project's native Windows/Python workflow unless a Makefile solves a demonstrated need. |
| `.github/workflows/ci-tests.yml`; `.github/workflows/cd-deploy.yml`; `06-best-practices/code/infrastructure/` | [Reference repository] Shows a course-scale AWS CI/CD and Terraform path for Kinesis/Lambda/S3/ECR. | **DO NOT COPY** | [Project source] Later deployment/CI only; Section 40 excludes multi-cloud/Kubernetes-style expansion, and Section 41 requires measured need. | [Inference] Besides being domain/cloud-specific, the checked-in CI points to misspelled `integraton-test` (`.github/workflows/ci-tests.yml:43-46`, while the tracked directory is `06-best-practices/code/integration-test/`), CD auto-applies Terraform, tags images `latest`, and selects the most recently modified S3 key (`.github/workflows/cd-deploy.yml:25-76`). Design a project-specific pipeline from current actions and immutable artifact identities. |
| `cohorts/2022/` through `cohorts/2025/`; `research/`; course images and homework solutions | [Reference repository] Preserve historical course variants, exercises, community notes, and solved examples. | **IGNORE FOR NOW** | [Project source] No direct Phase 1 deliverable; the master spec already chooses the project direction and tools by phase. | [Inference] Searching multiple cohorts for a pasteable solution invites version drift and accidental copying. Consult only the current module concept relevant to an active later-phase decision. |

### Evidence-backed anti-patterns to avoid

- [Reference repository] The root describes a nine-week educational course spanning experimentation through monitoring (`README.md:43-49,85-132`), not a cohesive production template. [Inference] Do not transplant its full syllabus into the architecture or backlog.
- [Reference repository] Tool drift is explicit: MLflow methods/stages changed (`02-experiment-tracking/README.md:1-65`), monitoring preserves pre/post Evidently 0.7 trees, and `05-monitoring/post-evidently-0.7/requirements.txt:1-13` is unpinned. [Inference] Do not rely on tutorial code without current official-doc verification and compatibility pins.
- [Reference repository] CI uses old checkout/setup actions and a nonexistent working directory (`.github/workflows/ci-tests.yml:18-44`). [Inference] Copying workflow YAML would import a demonstrably broken path and stale dependencies.
- [Reference repository] CD runs `terraform apply -auto-approve`, uses mutable `latest`, old `set-output` syntax, and discovers a model by the latest S3 object (`.github/workflows/cd-deploy.yml:25-76`). [Inference] This breaks exact provenance and controlled promotion; use immutable commit/model/data identities and explicit gates.
- [Reference repository] Deployment and infrastructure examples are tied to taxi duration, AWS Kinesis/Lambda, and course-owned model artifacts (`04-deployment/README.md`, Sections 4.1-4.6; `06-best-practices/README.md:55-139`). [Inference] They solve different contracts and should not determine this project's service or cloud design.

## Cross-reference to the master specification

[Project source]

| Master-spec section | Reference input that is useful | Decision for this project |
|---|---|---|
| Section 8 Dataset Strategy; Section 18 Data Quality; Section 36 Data Modes | MetroGuard data card, checksum, cadence/coverage, schema validation | [Inference] Reproduce the discipline with the exact selected MetroPT 2022 artifact; own all data facts and fixtures. |
| Sections 10 and 14; Phase 1; Section 37 leakage tests | MetroGuard causal bins, consecutive windows, purged chronological split | [Inference] Adapt invariants only; decide exact windows/splits from this dataset before implementation. |
| Sections 11-13 ML ladder | MetroGuard robust baseline, Isolation Forest, autoencoder comparison | [Inference] Learn the comparator structure; implement the simplest project-specific models and report whichever wins. |
| Sections 15-16 evaluation and alert policy | MetroGuard episode metrics, calibration-only threshold, persistence/merge separation | [Inference] Own event association, exposure, uncertainty, threshold, and alert semantics. Defer full alert operations to Phase 4. |
| Section 20 and Phase 2 serving | MetroGuard bounded scoring; Zoomcamp deployment forms; IoT history API | [Inference] Design the API only after Phase 1 freezes the feature/artifact boundary. |
| Section 19 and Phase 3 streaming | IoT producer/Kafka/Spark event-time architecture | [Inference] Independently implement deterministic finite replay and online/offline feature parity; do not import its synthetic data or topology. |
| Sections 22-23 and Phase 5 MLOps | Zoomcamp orchestration and MLflow modules | [Inference] Study later; Phase 1 needs only a small reproducible command and manifest. |
| Sections 24-25 and Phase 6 monitoring | IoT Grafana/Timescale shape; Zoomcamp Evidently/Grafana methodology | [Inference] Define monitoring from owned system/data/model failure modes after the online path exists. |
| Section 37 testing | MetroGuard leakage/data tests; Zoomcamp testing layers | [Inference] Adapt test categories immediately, but write every fixture and assertion from project contracts. |
| Sections 31-32 reuse policy | All three repositories | [Inference] Cite influence, use upstream libraries, write independent code/contracts/integration, and retain no copied artifacts. |

## What this project must own independently

The following are not delegable to a reference repository.

| Owned decision/artifact | Required independent work |
|---|---|
| Dataset understanding | [Project source] Select the exact canonical MetroPT version/file, verify checksum and source/version, document row meaning, signal meanings/units, cadence, gaps, duplicates, missingness, operating regimes, maintenance/failure annotations, and dataset license. [Inference] MetroPT-3 facts from MetroGuard are hypotheses at most, never substitutions. |
| Data and stream contracts | [Project source] Define canonical field names/types/units, timestamps/time zone, asset identity, schema evolution, quality disposition, event ID/replay ID/idempotency, and raw-to-feature provenance. |
| Feature definitions | [Project source] Specify causal analog/digital features, window alignment/closure, coverage, gap handling, feature order/version, offline/online parity, and explanations. [Inference] Every feature needs domain and prediction-time justification. |
| Temporal split | [Project source] Choose train/calibration/test dates from actual event chronology and operating regimes, purge overlapping windows, and freeze holdout before model/threshold decisions. |
| Leakage controls | [Project source] Fit scalers/baselines/models on train only; use calibration only for threshold/policy/model selection; prohibit future interpolation, backfill, centered windows, and random row splits; make these executable tests (`docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md:1939-1949`). |
| Model evaluation | [Project source] Define event matching, early/late windows, normal exposure, event recall/count uncertainty, lead time, false alarms/day, PR-AUC, time in alert, sensitivity analyses, comparator cost, and holdout-once reporting. |
| Threshold policy | [Project source] Define score normalization, calibration objective, quantile or alternative, stability checks, and locked threshold provenance. [Inference] A reference quantile is not evidence for this dataset. |
| Alert policy | [Project source] Separately define persistence, merging, cooldown, severity, reset/resume, missing-data behavior, and traceability. Phase 1 should evaluate episodes without prematurely building the Phase 4 service. |
| Model/artifact contract | [Project source] Version feature schema, preprocessing, model weights, threshold, training data identity, code revision, parameters, metrics, limitations, and safe loading expectations. |
| API contracts | [Project source] Own `/v1/score` semantics, request/response validation, units, timestamps, feature/raw-input choice, model provenance, error behavior, health/readiness, idempotency, and alert/history schemas. Do not inherit a reference endpoint shape. |
| Replay and streaming semantics | [Project source] Preserve source event time, support deterministic speed-up, define ordering/late data, finite ranges, duplicates, checkpointing, reset, DLQ, delivery guarantees, and feature parity. |
| Experiment and promotion policy | [Project source] Define data/feature/model lineage, candidate/champion criteria, immutable identities, approval gates, rollback, and measured evidence before Phase 5 tooling. |
| Monitoring and RCA evidence | [Project source] Distinguish service, data, and model health; define alert evidence and deterministic RCA tool contracts. The LLM must never become the anomaly detector or invent mechanical cause. |
| Documentation and attribution | [Project source] Write independent data/model cards, architecture, rationale, limitations, benchmark method, and README. [Inference] Acknowledge conceptual influence from MetroGuard, the IoT pipeline, and MLOps Zoomcamp without incorporating their text or assets. |

## Licensing and copied-code risk register

| Repository | Risk | Required control |
|---|---|---|
| `metroguard-ml` | [Reference repository] MIT code requires preservation of notice for copies/substantial portions; its data extract is separately described as CC BY 4.0. | [Inference] Prefer independent implementation. If any code is ever intentionally reused, identify the exact lines, retain MIT notice, document modifications, and separately satisfy data attribution. This map authorizes no such reuse. |
| `iot-streaming-pipeline` | [Reference repository] No permissive license file; README says all rights reserved. | [Inference] No copying of code/config/SQL/dashboard/diagram/prose. Concepts only, independently implemented. |
| `mlops-zoomcamp` | [Unknown/unsupported] No local explicit license grant was found. | [Inference] No copying of code/notebooks/workflows/diagrams/prose. Learn concepts, then use official library/tool documentation and independent project code. |
| All three | [Inference] Similar filenames, schemas, constants, comments, tests, or workflow structure can still create provenance ambiguity even when an algorithmic idea is generic. | [Inference] Keep a clean-room habit: derive requirements from the master spec/data, write new interfaces/tests first, cite influences, and avoid side-by-side transliteration. |

## Final recommendation

[Inference] For Phase 1, open MetroGuard only as a methodological checklist and independently answer the project's unresolved questions. Leave the IoT and Zoomcamp repositories untouched until their mapped phases. This is the smallest route that preserves the master spec's core portfolio value: real data understanding, leakage-safe evaluation, and defensible engineering decisions rather than assembled third-party code.

[Unknown/unsupported] This review establishes local source content and licensing evidence at the three recorded commits only. It does not establish current upstream state, legal advice, runtime correctness, benchmark validity, dependency security, or whether remote CI is green, because browsing and workload execution were explicitly out of scope.
