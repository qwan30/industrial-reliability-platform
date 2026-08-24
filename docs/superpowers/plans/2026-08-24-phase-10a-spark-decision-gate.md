# Phase 10A Spark Decision Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide `ADOPTED`, `NOT_ADOPTED`, or `N/A` for Spark from correctness, capacity, recovery, and resource evidence without making Spark a dependency before it is needed.

**Architecture:** A dependency-free benchmark first measures the existing Python worker against the Phase 4 contracts and a fixed 1000x replay workload. Passing baseline capacity ends the phase as `NOT_ADOPTED`, while a missing feasible platform makes the phase `N/A`; champion model family does not affect Spark applicability. Only a correct baseline that misses a capacity gate may open an isolated PySpark candidate, and Spark reaches the default Compose stack only after parity and net-benefit gates pass.

**Tech Stack:** Python 3.12 standard library, existing Kafka/PostgreSQL/FastAPI runtime, Docker Compose, optional isolated PySpark 4.0.1 with Java 17, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- The first executable gate reads Phase 1B and champion evidence. If Phase 1B is not `FEASIBLE` or the champion is null, publish `N/A` and do not install, import, download, configure, or mention Spark as part of the runtime.
- Do not add PySpark, Java, Spark images, Spark configuration, candidate topics, or Spark source files before the baseline need artifact says `EVALUATE_SPARK` for the exact Git/champion/contract/data hashes.
- The Python worker in `src/industrial_reliability/worker.py` is the baseline. Preserve `runtime_messages.py`, source-time semantics, gap segmentation, deterministic IDs, `POST /v1/score`, at-least-once delivery, offset ordering, quarantine behavior, and Phase 5 alert policy.
- A baseline correctness, identity, data-quality, or recovery failure is a defect in the current platform, not evidence for Spark. Stop and repair the owning earlier phase before resuming this gate.
- Spark can be adopted only when it matches feature/score/alert outputs and provides a predeclared measured capacity benefit large enough to offset its resource and operating complexity.
- Candidate artifacts, event captures, detailed timings, and Spark checkpoints remain git-ignored under `artifacts/phase10a/`. Committed results are allowlisted aggregates with exact hashes.
- Freeze every baseline/candidate run to source range `[2020-04-17T22:00:00, 2020-04-19T00:00:00)` at `1000x`, five repetitions, with repetition three restarting the feature/scoring worker. This covers the two-hour horizon and normalized end of incident `metropt3-1`; both engines consume the identical canonical workload manifest and hash.
- Do not add a generic stream-engine interface, runtime engine selector, dual-write mode, or unused Spark service. If adopted, the Compose worker is replaced directly; if not adopted, the Python worker remains untouched.
- Use `.\.venv\Scripts\python.exe` for baseline/project commands and `.\.venv-spark\Scripts\python.exe` only after the need gate permits candidate evaluation.
- Every implementation task uses RED-GREEN-REFACTOR, preserves at least 80% branch coverage for project code, and ends in one logical conventional commit.

---

### Task 1: Define immutable benchmark and optional-technology decision records

**Files:**
- Create: `src/industrial_reliability/decision_gate.py`
- Create: `src/industrial_reliability/replay_benchmark.py`
- Create: `tests/test_decision_gate.py`
- Create: `tests/test_replay_benchmark.py`

**Interfaces:**
- Consumes: Phase 3 replay control, Phase 4 feature/score topics and parity fixture, Phase 5 persisted decisions/alerts, Phase 8 metrics, and the current Compose container statistics.
- Produces: `DecisionStatus = Literal["ADOPTED", "NOT_ADOPTED", "N/A"]`, immutable `ReplayBenchmarkResultV1`, `OptionalTechnologyDecisionV1`, `canonical_sha256(payload) -> str`, `write_decision(decision, path) -> Path`, and CLI `.\.venv\Scripts\python.exe -m industrial_reliability.replay_benchmark`.
- `ReplayBenchmarkResultV1` fields are `implementation`, `git_sha`, `champion_sha256`, `contract_sha256`, `source_dataset_sha256`, `workload_sha256`, `repetitions`, `source_events`, `valid_windows`, `feature_digest`, `score_digest`, `alert_digest`, `duplicate_rows`, `quarantine_rows`, `p50_latency_ms`, `p95_latency_ms`, `throughput_events_per_second`, `max_consumer_lag`, `lag_drain_seconds`, `cpu_seconds_per_million_events`, `peak_rss_bytes`, and `restart_recovery_passed`.

- [ ] **Step 1: Write failing schema, canonical-hash, and invalid-number tests**

```python
def test_decision_is_canonical_and_self_hashed(tmp_path: Path) -> None:
    decision = decision_fixture(status="NOT_ADOPTED", reason_codes=("BASELINE_MEETS_CAPACITY",))
    first = write_decision(decision, tmp_path / "first.json")
    second = write_decision(decision, tmp_path / "second.json")
    assert first.read_bytes() == second.read_bytes()
    assert len(json.loads(first.read_text())["decision_sha256"]) == 64


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_benchmark_rejects_invalid_latency(value: float) -> None:
    with pytest.raises(ValueError, match="latency"):
        benchmark_fixture(p95_latency_ms=value)


def test_decision_rejects_adoption_without_candidate() -> None:
    with pytest.raises(ValueError, match="candidate evidence"):
        decision_fixture(status="ADOPTED", candidate=None)
```

- [ ] **Step 2: Run focused tests and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_decision_gate.py tests\test_replay_benchmark.py -q`

Expected: FAIL because both modules do not exist.

- [ ] **Step 3: Implement frozen records and canonical serialization**

```python
DecisionStatus = Literal["ADOPTED", "NOT_ADOPTED", "N/A"]


@dataclass(frozen=True)
class OptionalTechnologyDecisionV1:
    schema_version: str
    technology: str
    status: DecisionStatus
    git_sha: str
    champion_sha256: str | None
    contract_sha256: str | None
    source_dataset_sha256: str | None
    reason_codes: tuple[str, ...]
    baseline: ReplayBenchmarkResultV1 | None
    candidate: ReplayBenchmarkResultV1 | None
    parity_passed: bool | None
    benefit_passed: bool | None
    limitations: tuple[str, ...]
    decision_sha256: str = ""
```

Canonical JSON is UTF-8 with `sort_keys=True`, separators `(",", ":")`, and `allow_nan=False`. Require a 40-character Git SHA, 64-character artifact hashes, non-negative finite metrics, `technology="spark"`, `N/A` with no benchmark, `NOT_ADOPTED` with at least a baseline or infeasibility reason, and `ADOPTED` with both benchmarks plus true parity/benefit gates.

- [ ] **Step 4: Implement the existing-runtime benchmark reader**

The CLI starts an already-built bounded replay through Phase 6 control APIs, samples Phase 8 metrics and `docker stats`, waits for a terminal replay state, hashes ordered persisted `FeatureVectorV1`, `ScoreDecisionV1`, and alert canonical JSON, and repeats five times. It writes detailed samples only beneath the requested local output directory. It never imports an alternative engine.

Use `time.perf_counter_ns()` for duration and the existing message `emitted_at` stamps for end-to-end latency. Query durable row counts after completion; reject a session whose identity hashes differ from the champion.

- [ ] **Step 5: Run unit checks for metric aggregation and identity rejection**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_decision_gate.py tests\test_replay_benchmark.py -q
.\.venv\Scripts\python.exe -m ruff check src\industrial_reliability\decision_gate.py src\industrial_reliability\replay_benchmark.py tests\test_decision_gate.py tests\test_replay_benchmark.py
.\.venv\Scripts\python.exe -m mypy src\industrial_reliability\decision_gate.py src\industrial_reliability\replay_benchmark.py
```

Expected: PASS; shuffled durable records fail digest comparison rather than being silently sorted.

- [ ] **Step 6: Commit the reusable evidence records and baseline harness**

```powershell
git add src/industrial_reliability/decision_gate.py src/industrial_reliability/replay_benchmark.py tests/test_decision_gate.py tests/test_replay_benchmark.py
git commit -m "test: add streaming decision benchmark"
```

### Task 2: Run the applicability and baseline-need gate before Spark exists

**Files:**
- Create: `src/industrial_reliability/phase10a_gate.py`
- Create: `tests/test_phase10a_gate.py`
- Create: `docs/results/phase-10a-spark-decision.json`
- Create: `docs/results/phase-10a-spark-decision.md`

**Interfaces:**
- Consumes: Phase 1B aggregate verdict/champion manifest, Task 1 baseline result, Phase 4 golden digests, and Phase 8 recovery evidence.
- Produces: `baseline_need(result: ReplayBenchmarkResultV1, golden: GoldenDigests) -> Literal["NOT_ADOPTED", "EVALUATE_SPARK"]`, local `artifacts/phase10a/spark-need.json`, and terminal committed report when status is `N/A` or baseline-only `NOT_ADOPTED`.

- [ ] **Step 1: Write failing branch and threshold tests**

```python
def test_infeasible_platform_is_na_without_candidate() -> None:
    decision = decide_phase10a(feasible=False, champion=None, baseline=None)
    assert decision.status == "N/A"
    assert decision.reason_codes == ("PLATFORM_PATH_STOPPED",)


def test_capacity_pass_avoids_spark() -> None:
    result = baseline_fixture(
        p95_latency_ms=900.0,
        lag_drain_seconds=20.0,
        restart_recovery_passed=True,
    )
    assert baseline_need(result, golden_digests()) == "NOT_ADOPTED"


def test_only_capacity_miss_opens_candidate_gate() -> None:
    result = baseline_fixture(p95_latency_ms=2500.0, lag_drain_seconds=70.0)
    assert baseline_need(result, golden_digests()) == "EVALUATE_SPARK"


def test_parity_miss_is_not_a_spark_need() -> None:
    with pytest.raises(CurrentRuntimeDefect, match="feature digest"):
        baseline_need(baseline_fixture(feature_digest="0" * 64), golden_digests())
```

- [ ] **Step 2: Run the tests and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_phase10a_gate.py -q`

Expected: FAIL because `industrial_reliability.phase10a_gate` does not exist.

- [ ] **Step 3: Encode the predeclared baseline gate**

Baseline correctness requires feature/score/alert digests equal the Phase 4/5 golden digests, zero duplicates, zero unexpected quarantine rows, terminal session `COMPLETED`, and restart recovery true. Baseline capacity passes only when all five repetitions at `1000x` have p95 decision latency at most `2000 ms`, lag drain at most `60 s`, and no exhausted retry/session failure. Record CPU and peak RSS but do not invent absolute hardware-neutral limits for them.

If correctness fails, raise `CurrentRuntimeDefect`. If correctness passes and capacity passes, return `NOT_ADOPTED`. If correctness passes but either capacity threshold fails, write `EVALUATE_SPARK` with exact baseline/workload hashes.

- [ ] **Step 4: Run the exact baseline workload**

```powershell
git status --short --branch
git check-ignore artifacts/phase10a
.\.venv\Scripts\python.exe -m industrial_reliability.replay_benchmark --implementation python-worker --range-start 2020-04-17T22:00:00 --range-end 2020-04-19T00:00:00 --speed 1000 --repetitions 5 --restart-repetition 3 --output artifacts\phase10a\baseline
.\.venv\Scripts\python.exe -m industrial_reliability.phase10a_gate baseline --phase1b-result docs\results\phase-1b-metrics.json --champion artifacts\champion\manifest.json --benchmark artifacts\phase10a\baseline\benchmark.json --output artifacts\phase10a\spark-need.json
```

Expected: either (a) `N/A` from a second-infeasible path, (b) `NOT_ADOPTED` with `BASELINE_MEETS_CAPACITY`, or (c) `EVALUATE_SPARK` only for a capacity miss. A parity/recovery error exits nonzero and produces no decision.

- [ ] **Step 5: Stop immediately on a terminal baseline decision**

For `N/A` or `NOT_ADOPTED`, use the tested renderer to write both `docs/results/phase-10a-spark-decision.*` files, run the phase checks in Task 5, commit the result below, and skip Tasks 3-4. For `EVALUATE_SPARK`, keep the need artifact local, commit only gate code/tests, and continue to Task 3.

```powershell
git add src/industrial_reliability/phase10a_gate.py tests/test_phase10a_gate.py
git commit -m "test: gate Spark candidate evaluation"
```

### Task 3: Build an isolated Spark candidate only after the need gate

**Files:**
- Create: `requirements-phase10a-spark.txt`
- Create: `benchmarks/spark_worker.py`
- Create: `tests/optional/test_spark_worker.py`

**Interfaces:**
- Consumes: valid local `artifacts/phase10a/spark-need.json` with decision `EVALUATE_SPARK`, Phase 3 `TelemetryEventV1`, shared `causal_features.py`, stateless scoring API, and candidate-only Kafka output topics `irp.features.spark-candidate.v1` and `irp.scores.spark-candidate.v1`.
- Produces: `run_spark_candidate(input_topic: str, feature_topic: str, score_topic: str, checkpoint_dir: Path) -> None` in an isolated Python environment; it emits the unchanged `FeatureVectorV1` and `ScoreDecisionV1` schemas.

- [ ] **Step 1: Assert the need artifact before installing anything**

```powershell
.\.venv\Scripts\python.exe -m industrial_reliability.phase10a_gate authorize-candidate --need artifacts\phase10a\spark-need.json --expected-git-sha (git rev-parse HEAD) --expected-champion artifacts\champion\manifest.json
```

Expected: prints `EVALUATE_SPARK authorized` and exits 0 only when all exact hashes still match. Any mismatch stops this task before environment creation.

- [ ] **Step 2: Write the candidate parity test before PySpark installation**

```python
pyspark = pytest.importorskip("pyspark")


def test_spark_candidate_matches_python_feature_messages(spark_session, telemetry_fixture) -> None:
    expected = python_worker_features(telemetry_fixture)
    actual = spark_feature_messages(spark_session, telemetry_fixture)
    assert [item.window_id for item in actual] == [item.window_id for item in expected]
    np.testing.assert_allclose(
        [item.values for item in actual],
        [item.values for item in expected],
        rtol=1e-9,
        atol=1e-12,
    )
```

- [ ] **Step 3: Create the isolated pinned environment and confirm RED**

`requirements-phase10a-spark.txt` contains exactly:

```text
pyspark==4.0.1
```

Run:

```powershell
py -3.12 -m venv .venv-spark
.\.venv-spark\Scripts\python.exe -m pip install -e ".[dev]" -r requirements-phase10a-spark.txt
.\.venv-spark\Scripts\python.exe -m pytest --no-cov tests\optional\test_spark_worker.py -q
```

Expected: FAIL because `benchmarks.spark_worker` is absent. Java 17 absence fails preflight explicitly; it does not modify the default project environment.

- [ ] **Step 4: Implement the minimum candidate using shared feature math**

Parse Kafka JSON with an explicit Spark schema, partition by replay session/machine, use source timestamp and the Phase 1B five-minute right-closed bins, reject insufficient bins, close state on gaps/order violations, and call the existing shared causal feature function per complete six-bin segment. Use `foreachBatch` to serialize the existing message models and call `/v1/score`; checkpoint only under the supplied git-ignored path. Do not create a Spark-specific message or scoring implementation.

Candidate message IDs use the same deterministic functions as `worker.py`. Duplicate/restart behavior is verified through IDs and candidate-topic compaction in the test harness, not claimed as exactly-once.

- [ ] **Step 5: Run optional parity and restart tests**

```powershell
.\.venv-spark\Scripts\python.exe -m pytest --no-cov tests\optional\test_spark_worker.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
```

Expected: Spark candidate fixtures match Python feature/score IDs and numeric values, a gap creates the same segment boundary, and a checkpoint restart creates no new deterministic IDs.

- [ ] **Step 6: Commit only the isolated candidate**

```powershell
git add requirements-phase10a-spark.txt benchmarks/spark_worker.py tests/optional/test_spark_worker.py
git commit -m "perf: add isolated Spark streaming candidate"
```

### Task 4: Compare parity and net benefit before runtime adoption

**Files:**
- Modify: `src/industrial_reliability/phase10a_gate.py`
- Modify: `tests/test_phase10a_gate.py`
- Create: `tests/integration/test_spark_candidate.py`

**Interfaces:**
- Consumes: baseline and candidate `ReplayBenchmarkResultV1` for the same workload/champion/Git source, plus full ordered feature/score/alert captures.
- Produces: `compare_spark(baseline, candidate) -> OptionalTechnologyDecisionV1` with terminal status `ADOPTED` or `NOT_ADOPTED`.

- [ ] **Step 1: Write failing adoption-threshold tests**

```python
def test_candidate_requires_parity_and_large_measured_gain() -> None:
    decision = compare_spark(
        baseline_fixture(p95_latency_ms=3000, throughput_events_per_second=100),
        candidate_fixture(p95_latency_ms=1800, throughput_events_per_second=160),
    )
    assert decision.status == "ADOPTED"


def test_small_gain_is_not_adopted() -> None:
    decision = compare_spark(
        baseline_fixture(p95_latency_ms=3000, throughput_events_per_second=100),
        candidate_fixture(p95_latency_ms=2500, throughput_events_per_second=115),
    )
    assert decision.status == "NOT_ADOPTED"
    assert "NET_BENEFIT_GATE_FAILED" in decision.reason_codes


def test_resource_regression_blocks_adoption() -> None:
    decision = compare_spark(
        baseline_fixture(peak_rss_bytes=1_000_000_000),
        candidate_fixture(peak_rss_bytes=2_100_000_000),
    )
    assert decision.status == "NOT_ADOPTED"
```

- [ ] **Step 2: Run the gate tests and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_phase10a_gate.py -q`

Expected: FAIL because comparative decision rules are absent.

- [ ] **Step 3: Implement predeclared parity and benefit gates**

Parity requires identical ordered message IDs, window bounds, coverage, anomaly flags, alert IDs/actions, quarantine reasons, and output counts; numeric feature/score values use `rtol=1e-9`, `atol=1e-12`. Recovery must pass for both.

Net benefit requires the candidate to meet the baseline-missed capacity threshold and at least one of: throughput at least `1.50x` baseline or p95 latency at most `0.67x` baseline. It must also use at most `1.25x` baseline CPU-seconds per million events and at most `2.00x` baseline peak RSS. Any parity/resource miss is `NOT_ADOPTED`.

- [ ] **Step 4: Run the same five-repetition workload through the candidate**

```powershell
.\.venv-spark\Scripts\python.exe -m industrial_reliability.replay_benchmark --implementation spark-candidate --range-start 2020-04-17T22:00:00 --range-end 2020-04-19T00:00:00 --speed 1000 --repetitions 5 --restart-repetition 3 --output artifacts\phase10a\candidate
.\.venv\Scripts\python.exe -m industrial_reliability.phase10a_gate compare --baseline artifacts\phase10a\baseline\benchmark.json --candidate artifacts\phase10a\candidate\benchmark.json --output artifacts\phase10a\decision.json
.\.venv\Scripts\python.exe -m pytest --no-cov tests\integration\test_spark_candidate.py -q -m integration
```

Expected: one terminal decision with exact input hashes. `ADOPTED` is impossible unless all parity/recovery/resource checks and one capacity-improvement check pass.

- [ ] **Step 5: Commit comparison logic**

```powershell
git add src/industrial_reliability/phase10a_gate.py tests/test_phase10a_gate.py tests/integration/test_spark_candidate.py
git commit -m "test: compare Spark parity and capacity"
```

### Task 5: Publish the terminal decision and integrate only an adopted candidate

**Files:**
- Modify if adopted: `compose.yaml`
- Create if adopted: `Dockerfile.spark`
- Create if adopted: `src/industrial_reliability/spark_worker.py`
- Modify if adopted: `ops/prometheus/prometheus.yml`
- Modify if adopted: `tests/integration/test_phase4_gate.py`
- Create: `docs/results/phase-10a-spark-decision.json`
- Create: `docs/results/phase-10a-spark-decision.md`

**Interfaces:**
- Consumes: terminal decision from Task 2 or Task 4.
- Produces: default Compose remains Python for `NOT_ADOPTED`/`N/A`; for `ADOPTED`, `streaming-worker` runs Spark feature/scoring while a Python `alert-worker` runs the existing Phase 5 alert-consumer/outbox loops. All public topics/messages/APIs remain unchanged.

- [ ] **Step 1: Handle `NOT_ADOPTED` or `N/A` without runtime edits**

Render the two result files from the tested canonical decision. Include baseline/candidate aggregate metrics when measured, exact hashes, reason codes, resource trade-off, and the statement `Spark is not part of the default runtime.` Skip Steps 2-3 and proceed to Step 4.

- [ ] **Step 2: For `ADOPTED` only, write the failing default-runtime contract check**

Update the Phase 4 integration gate so the default Compose worker must reproduce the original Python golden feature/score digests and Phase 5 alert digest after a restart. Run it before changing Compose.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\integration\test_phase4_gate.py -q -m integration`

Expected: FAIL its engine assertion because Compose still runs the Python worker.

- [ ] **Step 3: Promote the measured candidate directly and rerun downstream gates**

Copy only validated candidate logic into `src/industrial_reliability/spark_worker.py`; `Dockerfile.spark` pins Java 17, Python 3.12, and `pyspark==4.0.1`; replace only feature/scoring in Compose without adding a selector. Keep the Phase 5 alert consumer and outbox dispatcher in a companion `alert-worker` Python service, and add both workers as Prometheus targets. Rerun Phase 4 parity, Phase 5 persistence/recovery, Phase 8 fault drills, and Phase 9 provider-fallback gate. Render the `ADOPTED` result only after every downstream gate passes.

- [ ] **Step 4: Run the common final verification**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
docker compose config --quiet
git diff --check
git check-ignore artifacts/phase10a
```

Expected: all commands PASS, branch coverage is at least 80%, local detailed evidence is ignored, and the committed JSON has status `ADOPTED`, `NOT_ADOPTED`, or `N/A` with an exact tested SHA.

- [ ] **Step 5: Commit the decision, and runtime only when adopted**

For `NOT_ADOPTED` or `N/A`:

```powershell
git add docs/results/phase-10a-spark-decision.json docs/results/phase-10a-spark-decision.md
git commit -m "docs: record Spark decision gate"
```

For `ADOPTED`:

```powershell
git add compose.yaml Dockerfile.spark src/industrial_reliability/spark_worker.py ops/prometheus/prometheus.yml tests/integration/test_phase4_gate.py docs/results/phase-10a-spark-decision.json docs/results/phase-10a-spark-decision.md
git commit -m "perf: adopt measured Spark worker"
```

## Phase 10A Exit Gate

The phase ends with exactly one evidence-backed status. `N/A` is valid only when the platform path stopped before a champion/runtime existed. `NOT_ADOPTED` is valid when the Python baseline already meets capacity or the isolated candidate misses parity/net-benefit/resource gates. `ADOPTED` is valid only after the candidate meets every gate and all affected Phase 4/5/8/9 checks pass on the new default runtime. A current-runtime defect produces no decision and must be fixed at its owning phase.
