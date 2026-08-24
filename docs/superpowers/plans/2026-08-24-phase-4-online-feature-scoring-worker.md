# Phase 4 Online Feature and Scoring Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consume replay telemetry, build the same causal feature vectors as Phase 1B, call the stateless scoring API, and publish traceable score decisions with retry-safe deterministic identity.

**Architecture:** A stateful `OnlineFeatureBuilder` wraps the shared Phase 1B feature math and resets segments on coverage, sequence, ordering, or split violations. One async worker consumes telemetry/status with manual offsets, publishes each feature, obtains one score through the Phase 2 API, publishes the decision, and commits only after the bounded replay session completes successfully; retries may duplicate Kafka records but preserve logical IDs.

**Tech Stack:** Python 3.12, NumPy, Pydantic v2, aiokafka, httpx, FastAPI scoring API, Apache Kafka, Docker Compose, pytest

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Do not start Phase 4 unless Phase 1B, Phase 2, and Phase 3 exit gates passed for exact ancestor commits and matching source/contract/model/package hashes.
- Online feature values and ordered names must match Phase 1B offline output exactly; `causal_features.compute_feature_values` remains the single feature-math implementation.
- A gap, sequence conflict, timestamp regression, invalid bin, or split boundary closes the active segment. Never fill, interpolate, reorder, or invent telemetry.
- Publish `FeatureVectorV1` to `irp.features.v1` and `ScoreDecisionV1` to `irp.scores.v1`; use their deterministic window/decision IDs as Kafka keys.
- Commit input offsets only after all required downstream operations succeed. Retry exhaustion marks the replay session `FAILED` and leaves its telemetry offsets uncommitted.
- Delivery remains at-least-once. Logical retry idempotence means repeated work has identical IDs and values; duplicate Kafka records are allowed and later PostgreSQL unique constraints enforce durable deduplication.
- A contract/model mismatch is permanent and fail-closed. Only network, timeout, HTTP 429, and HTTP 5xx failures use the bounded retry policy.
- Raw telemetry is not written to PostgreSQL or logs. Quarantine contains payload hashes and bounded error details only.
- Every phase gate includes contract/unit tests, real Kafka/API integration, at least 80% branch coverage, Ruff, format, mypy, `pip check`, package build, Docker build, and Compose validation.

---

### Task 1: Wrap the shared feature math in an online segment builder

**Files:**
- Create: `src/industrial_reliability/online_features.py`
- Create: `tests/test_online_features.py`

**Interfaces:**
- Consumes: ordered `TelemetryEventV1`, champion `feature_names`, and `causal_features.compute_feature_values`.
- Produces: `OnlineFeatureBuilder.push(event: TelemetryEventV1) -> BuilderResult`, `OnlineFeatureBuilder.complete(source_timestamp: datetime) -> BuilderResult`, and immutable `BuilderResult(features, segment_closed_reason)`.

- [ ] **Step 1: Write offline-online parity and reset tests**

```python
def test_online_features_equal_phase1b_offline_rows(real_window: pd.DataFrame, builder: OnlineFeatureBuilder) -> None:
    emitted = tuple(
        feature
        for event in telemetry_events(real_window)
        for feature in builder.push(event).features
    ) + builder.complete(real_window["timestamp"].iloc[-1]).features
    offline = tuple(iter_phase1b_windows(real_window, PHASE1B))
    assert len(emitted) == len(offline)
    for actual, expected in zip(emitted, offline, strict=True):
        assert actual.feature_names == expected.feature_names
        assert actual.feature_values == pytest.approx(expected.feature_values, rel=0.0, abs=1e-12)


@pytest.mark.parametrize("fault", ["sequence_gap", "conflicting_duplicate", "timestamp_regression", "invalid_bin"])
def test_stream_fault_closes_segment_without_crossing(fault: str) -> None:
    result = feed_faulted_stream(fault)
    assert result.segment_closed_reason == fault
    assert all(not window_crosses_fault(item) for item in result.features)
```

Also prove an exact duplicate `(message_id, sequence, payload)` is a no-op, while the same sequence with different identity/content fails the session.

- [ ] **Step 2: Run tests and verify the builder module is absent**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_online_features.py -q`

Expected: FAIL because `industrial_reliability.online_features` does not exist.

- [ ] **Step 3: Implement immutable builder results and segment tracking**

```python
SegmentCloseReason = Literal[
    "sequence_gap", "conflicting_duplicate", "timestamp_regression", "invalid_bin", "split_boundary"
]


@dataclass(frozen=True, slots=True)
class BuilderResult:
    features: tuple[FeatureVectorV1, ...]
    segment_closed_reason: SegmentCloseReason | None


class OnlineFeatureBuilder:
    def push(self, event: TelemetryEventV1) -> BuilderResult:
        duplicate = self._classify_identity(event)
        if duplicate == "exact":
            return BuilderResult((), None)
        close_reason = self._ordering_fault(event)
        if close_reason is not None:
            self._reset_segment()
        completed_bins = self._append_and_close_elapsed_bins(event)
        features = tuple(self._emit_window(item) for item in completed_bins if item.window_ready)
        return BuilderResult(features, close_reason)
```

The builder constructor requires replay session, machine ID, source/contract hashes, exact champion feature names, and a UTC clock. Keep only current-bin samples and the last six valid bins. Convert telemetry into `TelemetrySample`; call shared `compute_feature_values` only when six right-closed adjacent bins each have at least 24 observations.

- [ ] **Step 4: Implement deterministic feature envelopes and completion**

```python
window_id = runtime_id("window", event.replay_session_id, window_end.isoformat(timespec="seconds"))
feature = FeatureVectorV1(
    message_id=window_id,
    window_id=window_id,
    replay_session_id=event.replay_session_id,
    source_dataset_sha256=event.source_dataset_sha256,
    contract_sha256=event.contract_sha256,
    source_timestamp=window_end,
    emitted_at=self.clock(),
    machine_id=event.machine_id,
    window_start=window_start,
    window_end=window_end,
    feature_names=self.feature_names,
    feature_values=compute_feature_values(samples, self.feature_names),
    coverage=coverage,
)
```

`complete` is called only after `ReplayStatusV1(state="COMPLETED")`; it finalizes the last known bin, emits it only when coverage and adjacency pass, then closes the session. It rejects a completion timestamp before the last telemetry timestamp.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_online_features.py -q`

Expected: PASS on synthetic faults and real Phase 1B golden rows with absolute tolerance `1e-12`.

- [ ] **Step 5: Commit the online feature slice**

```powershell
git add src/industrial_reliability/online_features.py tests/test_online_features.py
git commit -m "feat: build online causal feature windows"
```

Expected: no scoring, Kafka consumer, persistence, or alert code is included.

### Task 2: Add a bounded, contract-validating scoring client

**Files:**
- Create: `src/industrial_reliability/scoring_client.py`
- Create: `tests/test_scoring_client.py`

**Interfaces:**
- Consumes: `FeatureVectorV1`, model version, `POST /v1/score`, `ScoreResponseV1`, and `ErrorResponseV1` exactly as defined in Phase 2.
- Produces: `RetryPolicy`, `async ScoringClient.score(feature: FeatureVectorV1) -> ScoreDecisionV1`, `RetryableScoringError`, and `PermanentScoringError`.

- [ ] **Step 1: Write retry classification and response-identity tests**

```python
@pytest.mark.asyncio
async def test_client_retries_timeout_then_returns_verified_decision() -> None:
    transport = sequence_transport(TimeoutException("timeout"), score_response())
    client = ScoringClient("http://scoring-api:8000", MODEL_VERSION, transport=transport, sleep=no_sleep)
    decision = await client.score(feature_vector())
    assert decision.window_id == feature_vector().window_id
    assert transport.request_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 409, 422])
async def test_client_does_not_retry_permanent_contract_errors(status: int) -> None:
    client, transport = client_returning(status)
    with pytest.raises(PermanentScoringError):
        await client.score(feature_vector())
    assert transport.request_count == 1
```

Add tests for retries on 429/500/503, exhaustion after exactly three attempts, malformed success envelope, and mismatch in window, replay session, source hash, contract hash, or model version.

- [ ] **Step 2: Run tests and verify the client is absent**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_scoring_client.py -q`

Expected: FAIL because `industrial_reliability.scoring_client` does not exist.

- [ ] **Step 3: Implement the fixed retry policy and exact API envelope**

```python
@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    delays_seconds: tuple[float, float] = (0.25, 1.0)


async def score(self, feature: FeatureVectorV1) -> ScoreDecisionV1:
    request = ScoreRequestV1(model_version=self.model_version, feature_vector=feature)
    for attempt in range(self.retry_policy.attempts):
        try:
            response = await self.client.post("/v1/score", content=request.model_dump_json())
            return self._validated_decision(response, feature)
        except RetryableScoringError:
            if attempt + 1 == self.retry_policy.attempts:
                raise
            await self.sleep(self.retry_policy.delays_seconds[attempt])
    raise AssertionError("retry loop exhausted without returning or raising")
```

Set `Content-Type: application/json`, a five-second request timeout, and no automatic httpx retries. Parse HTTP 200 only as `ScoreResponseV1`; parse non-200 as `ErrorResponseV1`. Treat 429/5xx/timeouts/connect errors as retryable and every other status/schema/identity mismatch as permanent. Do not log request feature values.

- [ ] **Step 4: Run focused scoring-client tests**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_scoring_client.py -q`

Expected: PASS with exactly `0.25` then `1.0` seconds scheduled and no fourth attempt.

- [ ] **Step 5: Commit the scoring client**

```powershell
git add src/industrial_reliability/scoring_client.py tests/test_scoring_client.py
git commit -m "feat: call scoring API with bounded retry"
```

Expected: retry policy is fixed and small; no circuit breaker or provider abstraction is added.

### Task 3: Orchestrate Kafka feature and score processing safely

**Files:**
- Create: `src/industrial_reliability/worker.py`
- Create: `tests/test_worker.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `irp.telemetry.v1`, `irp.replay.status.v1`, champion manifest, and Phase 2 scoring API.
- Produces: keyed `FeatureVectorV1` on `irp.features.v1`, keyed `ScoreDecisionV1` on `irp.scores.v1`, quarantine records, and failed replay status on retry exhaustion.

- [ ] **Step 1: Write processing-order, commit, and failure tests**

```python
@pytest.mark.asyncio
async def test_offset_commits_only_after_completed_session_outputs_succeed(worker: StreamingWorker) -> None:
    await worker.handle(telemetry_record_for_complete_window())
    assert worker.consumer.commits == []
    assert worker.producer.topics == [FEATURES_TOPIC, SCORES_TOPIC]
    await worker.handle(completed_status_record())
    assert worker.consumer.commits == [expected_session_offsets()]


@pytest.mark.asyncio
async def test_score_retry_exhaustion_fails_session_without_commit(worker: StreamingWorker) -> None:
    worker.scoring_client.fail_all_attempts()
    with pytest.raises(SessionFailedError):
        await worker.handle(telemetry_record_for_complete_window())
    assert worker.consumer.commits == []
    assert last_status(worker).state == "FAILED"
```

Also test invalid telemetry quarantine without offset commit, exact duplicate no-op, conflicting duplicate failure, feature send failure before scoring, score send failure after scoring, worker-originated `FAILED` status no-op on re-consumption, and model/contract mismatch failure without retry.

```python
@pytest.mark.asyncio
async def test_completed_status_waits_for_its_last_telemetry_sequence(worker: StreamingWorker) -> None:
    await worker.handle(completed_status_record(last_sequence=180))
    assert worker.consumer.commits == []
    assert worker.builders[SESSION_ID].is_complete is False
    await worker.handle(telemetry_record(sequence=180))
    assert worker.builders[SESSION_ID].is_complete is True
    assert worker.consumer.commits == [expected_session_offsets()]
```

- [ ] **Step 2: Run tests and verify the worker is absent**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_worker.py -q`

Expected: FAIL because `industrial_reliability.worker` does not exist.

- [ ] **Step 3: Implement one manual-commit session processor**

```python
class StreamingWorker:
    async def _process_feature(self, feature: FeatureVectorV1) -> None:
        await self.producer.send_and_wait(
            FEATURES_TOPIC, encode_message(feature), key=str(feature.window_id).encode("ascii")
        )
        decision = await self.scoring_client.score(feature)
        await self.producer.send_and_wait(
            SCORES_TOPIC, encode_message(decision), key=str(decision.decision_id).encode("ascii")
        )

    async def _complete_session(self, status: ReplayStatusV1) -> None:
        for feature in self.builders[status.replay_session_id].complete(status.source_timestamp).features:
            await self._process_feature(feature)
        await self.consumer.commit(self.session_offsets[status.replay_session_id])

    async def _handle_terminal_status(self, status: ReplayStatusV1) -> None:
        self.terminal_status[status.replay_session_id] = status
        if self.last_sequence.get(status.replay_session_id) == status.last_sequence:
            await self._complete_session(status)
```

Consume telemetry and replay status in group `irp-streaming-worker-v1` with `enable_auto_commit=False`. Keep the terminal status, per-session builder, last processed telemetry sequence, and highest offsets per topic/partition. Kafka does not order records across topics: a terminal status is only a barrier declaration and cannot finalize until the worker has processed exactly `status.last_sequence`; if telemetry arrives later, its handler rechecks the stored terminal barrier. Reject telemetry beyond the declared terminal sequence. Use `# ponytail: session-scoped commits replay more after a crash; persist window checkpoints if long replays make recovery cost unacceptable` beside the session commit policy. This intentionally favors correctness and deterministic replay over early checkpoint complexity.

- [ ] **Step 4: Implement fail-closed error routing and settings**

On decode failure publish `QuarantineRecordV1`, mark that input partition blocked, and do not commit: committing a later invalid offset could skip earlier uncommitted session telemetry. On transient score exhaustion publish `ReplayStatusV1(state="FAILED", error_code="SCORING_RETRY_EXHAUSTED")` and leave session offsets uncommitted. When the worker consumes that deterministic failure status from the shared status topic, recognize its message ID and do not publish or commit again. On identity/order/contract errors publish `FAILED` with allowlisted codes and stop that session. Require `KAFKA_BOOTSTRAP_SERVERS`, `SCORING_API_URL`, `CHAMPION_PACKAGE_DIR`, and `CHAMPION_MANIFEST_SHA256`; derive model/source/contract/feature order only from the verified champion.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_worker.py -q`

Expected: PASS; no failure path advances a session offset past an unacknowledged feature or score.

- [ ] **Step 5: Commit the worker slice**

```powershell
git add .env.example src/industrial_reliability/worker.py tests/test_worker.py
git commit -m "feat: stream features through champion scoring"
```

Expected: no alert policy, PostgreSQL, SSE, RCA, or drift code is included.

### Task 4: Prove real Kafka/API parity and recovery

**Files:**
- Create: `tests/integration/test_online_worker.py`
- Modify: `compose.yaml`
- Modify: `Dockerfile`

**Interfaces:**
- Consumes: Kafka, replay producer, mounted champion package, mounted normalized Parquet, and scoring API.
- Produces: a real dependency path `telemetry -> feature -> score` and restart/retry evidence.

- [ ] **Step 1: Write the full dependency integration test**

```python
@dataclass(frozen=True, slots=True)
class GoldenOnlineRange:
    command: ReplayCommandV1
    window_count: int
    offline_feature_values: tuple[tuple[float, ...], ...]
    offline_scores: tuple[float, ...]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_replay_matches_offline_feature_and_score_golden(
    kafka_bootstrap: str, golden_online_range: GoldenOnlineRange
) -> None:
    await publish_command(kafka_bootstrap, golden_online_range.command)
    features = await consume_exact(kafka_bootstrap, FEATURES_TOPIC, golden_online_range.window_count)
    scores = await consume_exact(kafka_bootstrap, SCORES_TOPIC, golden_online_range.window_count)
    assert [item.feature_values for item in features] == pytest.approx(
        golden_online_range.offline_feature_values, rel=0.0, abs=1e-12
    )
    assert [item.score for item in scores] == pytest.approx(
        golden_online_range.offline_scores, rel=0.0, abs=1e-12
    )
```

Add a second integration case that stops scoring API, observes bounded retry and uncommitted offsets, restarts it, replays, and asserts repeated logical feature/decision IDs and values are identical even if Kafka contains duplicate records.

Add a third integration case that publishes `ReplayStatusV1(state="COMPLETED", last_sequence=180)` before telemetry sequence 180 on its separate topic, verifies no completion/commit occurs, then publishes sequence 180 and verifies the final offline-parity window and commit occur exactly once logically.

- [ ] **Step 2: Extend Compose with local application services**

Add services using the shared project image:

```yaml
  scoring-api:
    build: .
    command: ["python", "-m", "uvicorn", "industrial_reliability.api:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]
    ports: ["127.0.0.1:8000:8000"]
    volumes: ["./artifacts/champion:/runtime/champion:ro"]
    depends_on:
      kafka: {condition: service_healthy}

  replay-producer:
    build: .
    command: ["python", "-m", "industrial_reliability.replay_service"]
    volumes: ["./data/processed/phase1b:/runtime/data:ro", "./artifacts/champion:/runtime/champion:ro"]
    depends_on:
      kafka: {condition: service_healthy}

  streaming-worker:
    build: .
    command: ["python", "-m", "industrial_reliability.worker"]
    volumes: ["./artifacts/champion:/runtime/champion:ro"]
    depends_on:
      kafka: {condition: service_healthy}
      scoring-api: {condition: service_healthy}
```

Supply exact environment names from `.env`, never inline private hashes. Give scoring API a `/healthz` health check. `Dockerfile` remains one non-root image with command overrides; do not create service-specific Dockerfiles.

- [ ] **Step 3: Start dependencies and run integration tests**

```powershell
docker compose config --quiet
docker compose up -d --build kafka scoring-api replay-producer streaming-worker
.\.venv\Scripts\python.exe -m pytest --no-cov tests/integration/test_online_worker.py -q
docker compose stop streaming-worker replay-producer scoring-api kafka
```

Expected: real replay feature/score parity and outage recovery PASS; stopping services preserves volumes and local evidence.

- [ ] **Step 4: Run Docker and package checks**

```powershell
docker build --tag industrial-reliability:phase4 .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
```

Expected: image build, dependency check, and Python package build exit 0.

- [ ] **Step 5: Commit Compose integration**

```powershell
git add compose.yaml Dockerfile tests/integration/test_online_worker.py
git commit -m "test: prove online feature score parity"
```

Expected: Compose contains only local runtime dependencies and no secrets or copied model/data artifacts.

### Task 5: Publish Phase 4 parity evidence and enforce the next gate

**Files:**
- Create: `docs/results/phase-4-online-parity.md`
- Modify: `requirements-runtime.txt`

**Interfaces:**
- Consumes: exact upstream hashes and successful real-dependency evidence.
- Produces: aggregate Phase 4 evidence; local detailed captures remain under `artifacts/certification/phase-4/`.

- [ ] **Step 1: Verify the complete upstream hash chain**

```powershell
$phase1b = Get-Content -LiteralPath docs/results/phase-1b-metrics.json -Raw | ConvertFrom-Json
if ($phase1b.verdict -ne 'FEASIBLE' -or [string]::IsNullOrWhiteSpace($phase1b.selected_model)) { throw 'Phase 1B gate failed' }
$package = Get-Content -LiteralPath artifacts/champion/manifest.json -Raw | ConvertFrom-Json
if ($package.contract_sha256 -ne $phase1b.contract_sha256 -or $package.model_id -ne $phase1b.selected_model) { throw 'Champion provenance mismatch' }
```

Expected: certification stops before tests on any source/contract/model mismatch.

- [ ] **Step 2: Run complete quality and real-dependency gates**

```powershell
.\.venv\Scripts\python.exe -m pip freeze --exclude-editable | Sort-Object | Set-Content -Encoding ascii requirements-runtime.txt
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest --cov=industrial_reliability --cov-branch --cov-fail-under=80
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
docker compose config --quiet
docker build --tag industrial-reliability:phase4 .
git diff --check
```

Expected: all commands exit 0, including real Kafka/API tests, and branch coverage is at least 80%.

- [ ] **Step 3: Capture bounded parity and retry evidence locally**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests/integration/test_online_worker.py -q --junitxml=artifacts/certification/phase-4/integration.xml`

Expected: the local artifact records offline-online feature/score parity, exact logical ID equality after retry, outage status, and offset behavior without raw telemetry values in logs.

- [ ] **Step 4: Write the evidence-scoped report**

Record exact Git/upstream/package hashes, real source range, feature/window counts, maximum absolute feature and score differences, retry attempts/delays, duplicate logical-ID comparison, offset behavior, commands, Docker image ID, and limitations in `docs/results/phase-4-online-parity.md`. State that session-scoped commits may replay more records after a crash and that durable deduplication begins in Phase 5.

- [ ] **Step 5: Commit only aggregate evidence and the lock update**

```powershell
git add requirements-runtime.txt docs/results/phase-4-online-parity.md
git commit -m "docs: certify Phase 4 online parity"
git status --short --branch
```

Expected: no JUnit capture, raw event, package, model, Parquet, or `.env` file is staged.

## Whole-Phase Review and Merge Gate

Phase 5 becomes ready only when the worker uses shared feature math, real-data offline-online feature/score parity passes within `1e-12`, sequence/gap faults close segments, retries preserve logical IDs, permanent mismatches fail closed, retry exhaustion leaves offsets uncommitted, real Kafka/API integration passes, and coverage remains at least 80%. The review must retain the at-least-once wording and the explicit session-scoped recovery ceiling.
