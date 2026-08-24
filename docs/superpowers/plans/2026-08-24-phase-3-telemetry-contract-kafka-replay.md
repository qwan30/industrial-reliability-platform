# Phase 3 Telemetry Contract and Kafka Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replay normalized MetroPT-3 telemetry through Kafka as a deterministic, ordered, versioned event stream whose source time is unchanged by replay speed.

**Architecture:** Extend the Phase 2 runtime contract with replay command, status, telemetry, and quarantine messages; use canonical JSON and deterministic UUIDv5 identifiers at the Kafka boundary. A single Python replay producer reads the existing Parquet source, reacts to Kafka commands, applies pacing only to wall-clock emission, and publishes telemetry/status without persisting raw rows to PostgreSQL.

**Tech Stack:** Python 3.12, Pydantic v2, PyArrow, aiokafka, Apache Kafka 4.0 in KRaft mode, Docker Compose, pytest

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Phase 3 remains blocked unless Phase 1B is `FEASIBLE`, Phase 2 parity passed, and the integrity-checked local champion package exists.
- Kafka delivery is at-least-once. Deterministic identifiers support downstream idempotence; never claim exactly-once delivery.
- Every valid runtime message carries `schema_version`, `message_id`, `replay_session_id`, `source_dataset_sha256`, `contract_sha256`, `source_timestamp`, and `emitted_at`.
- Topic names are fixed: `irp.replay.commands.v1`, `irp.replay.status.v1`, `irp.telemetry.v1`, `irp.features.v1`, `irp.scores.v1`, and `irp.quarantine.v1`.
- Replay supports start, pause, resume, stop, bounded range, and speeds `1`, `100`, and `1000`; within one replay session, speed changes wall-clock delay only and never rewrites source timestamps, sequence, IDs, or sensor values.
- The producer emits only canonical sensor values and keeps raw Parquet as source of truth. PostgreSQL raw-telemetry duplication is out of scope.
- Invalid schemas are not silently dropped; they produce a hash-only quarantine record with topic/partition/offset and reason.
- The local demo runs one active replay session at a time; a second `START` fails with `REPLAY_ALREADY_ACTIVE` until the first reaches a terminal state.
- Kafka and every application service bind only to the local Docker network or localhost-published ports.
- Contract tests, focused unit tests, real-Kafka integration tests, at least 80% branch coverage, Ruff, format, mypy, `pip check`, package build, and Compose validation are mandatory.

---

### Task 1: Extend the versioned runtime message contract

**Files:**
- Modify: `src/industrial_reliability/runtime_messages.py`
- Modify: `tests/test_runtime_messages.py`

**Interfaces:**
- Consumes: Phase 2 `FeatureVectorV1` and `ScoreDecisionV1` without field changes.
- Produces: `ReplayCommandV1`, `ReplayStatusV1`, `TelemetryEventV1`, `QuarantineRecordV1`, and topic constants.

- [ ] **Step 1: Write failing replay/telemetry schema tests**

```python
def test_start_command_requires_bounded_range_and_supported_speed() -> None:
    with pytest.raises(ValidationError, match="range"):
        ReplayCommandV1(**command_payload(action="START", range_start=None))
    with pytest.raises(ValidationError, match="speed"):
        ReplayCommandV1(**command_payload(action="START", speed=10))


def test_telemetry_rejects_nonbinary_state_or_sequence_zero() -> None:
    payload = telemetry_payload()
    payload["comp"] = 2
    with pytest.raises(ValidationError):
        TelemetryEventV1.model_validate(payload)
    payload = telemetry_payload() | {"sequence": 0}
    with pytest.raises(ValidationError):
        TelemetryEventV1.model_validate(payload)


def test_phase2_message_json_remains_unchanged() -> None:
    assert FeatureVectorV1.model_validate_json(FROZEN_PHASE2_JSON).model_dump_json() == FROZEN_PHASE2_JSON
```

- [ ] **Step 2: Run tests and observe missing replay types**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_runtime_messages.py -q`

Expected: FAIL on imports for the new message types while frozen Phase 2 contract tests remain green.

- [ ] **Step 3: Add exact message types and topic constants**

```python
REPLAY_COMMANDS_TOPIC = "irp.replay.commands.v1"
REPLAY_STATUS_TOPIC = "irp.replay.status.v1"
TELEMETRY_TOPIC = "irp.telemetry.v1"
FEATURES_TOPIC = "irp.features.v1"
SCORES_TOPIC = "irp.scores.v1"
QUARANTINE_TOPIC = "irp.quarantine.v1"


class ReplayCommandV1(FrozenMessage):
    schema_version: Literal["replay-command-v1"] = "replay-command-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str
    contract_sha256: str
    source_timestamp: datetime
    emitted_at: datetime
    command_id: UUID
    action: Literal["START", "PAUSE", "RESUME", "STOP"]
    speed: Literal[1, 100, 1000]
    range_start: datetime | None
    range_end: datetime | None


class ReplayStatusV1(FrozenMessage):
    schema_version: Literal["replay-status-v1"] = "replay-status-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str
    contract_sha256: str
    source_timestamp: datetime
    emitted_at: datetime
    state: Literal["CREATED", "RUNNING", "PAUSED", "STOPPED", "COMPLETED", "FAILED"]
    last_sequence: int | None
    error_code: str | None
```

`TelemetryEventV1` adds `machine_id`, positive `sequence`, `tp2`, `tp3`, `h1`, `dv_pressure`, `reservoirs`, `oil_temperature`, `motor_current` as finite floats, and `comp`, `dv_electric`, `towers`, `mpg`, `lps`, `pressure_switch`, `oil_level`, `caudal_impulses` as `Literal[0, 1]` directly to the common envelope. `QuarantineRecordV1` contains its own schema version/common provenance plus `original_topic`, non-negative `partition`/`offset`, `payload_sha256`, `error_code`, and bounded `error_detail`; it never embeds raw payload bytes.

- [ ] **Step 4: Enforce action-specific and temporal invariants**

Require `START` to carry naive `range_start < range_end` inside Phase 1B holdout bounds and `source_timestamp == range_start`; require pause/resume/stop to carry neither range and to set `source_timestamp` to the producer's current replay cursor. Require `COMPLETED`, `STOPPED`, and `FAILED` status to carry the exact last emitted positive sequence (`0` only when failure occurred before telemetry); require `FAILED` to carry an allowlisted error code and every non-failed status to carry `error_code=None`. Require source timestamps naive and emitted times UTC-aware. Validate lowercase SHA-256 strings and forbid extra fields on every new model.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_runtime_messages.py -q`

Expected: PASS, including frozen Phase 2 JSON round trips.

- [ ] **Step 5: Commit the message extension**

```powershell
git add src/industrial_reliability/runtime_messages.py tests/test_runtime_messages.py
git commit -m "feat: define Kafka replay contracts"
```

Expected: no producer or broker code is included in this contract-only commit.

### Task 2: Add deterministic IDs and canonical Kafka I/O

**Files:**
- Create: `src/industrial_reliability/runtime_ids.py`
- Create: `src/industrial_reliability/kafka_io.py`
- Create: `tests/test_runtime_ids.py`
- Create: `tests/test_kafka_io.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: frozen Pydantic runtime messages.
- Produces: `runtime_id(kind: str, replay_session_id: UUID, identity: str) -> UUID`, `encode_message(message: FrozenMessage) -> bytes`, `decode_message(payload: bytes, message_type: type[MessageT]) -> MessageT`, and `KafkaSettings.from_env()`.

- [ ] **Step 1: Write ID/codec failure tests**

```python
def test_runtime_id_is_stable_and_domain_separated() -> None:
    session = UUID("11111111-1111-1111-1111-111111111111")
    assert runtime_id("telemetry", session, "42") == runtime_id("telemetry", session, "42")
    assert runtime_id("window", session, "42") != runtime_id("telemetry", session, "42")


def test_codec_is_canonical_and_rejects_wrong_schema() -> None:
    message = TelemetryEventV1.model_validate(telemetry_payload())
    assert encode_message(message) == encode_message(message)
    with pytest.raises(MessageDecodeError, match="schema_version"):
        decode_message(encode_message(message), ReplayCommandV1)
```

- [ ] **Step 2: Run tests and verify missing modules**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_runtime_ids.py tests\test_kafka_io.py -q`

Expected: FAIL because the ID and Kafka I/O modules do not exist.

- [ ] **Step 3: Implement UUIDv5 IDs and canonical JSON**

```python
RUNTIME_NAMESPACE = UUID("bc626fb9-7438-5da3-9437-f5b66d34aa52")


def runtime_id(kind: str, replay_session_id: UUID, identity: str) -> UUID:
    if not kind or not identity:
        raise ValueError("kind and identity must be non-empty")
    return uuid5(RUNTIME_NAMESPACE, f"{kind}:{replay_session_id}:{identity}")


def encode_message(message: FrozenMessage) -> bytes:
    payload = message.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def decode_message(payload: bytes, message_type: type[MessageT]) -> MessageT:
    try:
        return message_type.model_validate_json(payload)
    except (UnicodeDecodeError, ValidationError, ValueError) as error:
        raise MessageDecodeError(str(error)) from error
```

Add `aiokafka>=0.12,<1` explicitly to project dependencies and `pytest-asyncio>=1.1,<2` to the `dev` optional-dependency list in `pyproject.toml`. `KafkaSettings.from_env()` must require `KAFKA_BOOTSTRAP_SERVERS`, default `KAFKA_CLIENT_ID` to `industrial-reliability`, and never log credentials or payloads.

- [ ] **Step 4: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_runtime_ids.py tests\test_kafka_io.py -q`

Expected: PASS; JSON has stable key ordering/UTF-8 bytes, NaN is rejected, and settings reject empty broker lists.

- [ ] **Step 5: Commit the Kafka boundary primitives**

```powershell
git add pyproject.toml src/industrial_reliability/runtime_ids.py src/industrial_reliability/kafka_io.py tests/test_runtime_ids.py tests/test_kafka_io.py
git commit -m "feat: add deterministic Kafka message I/O"
```

Expected: only reusable boundary primitives and their direct dependency change are committed.

### Task 3: Build a deterministic Parquet replay source

**Files:**
- Create: `src/industrial_reliability/replay.py`
- Create: `tests/test_replay.py`

**Interfaces:**
- Consumes: normalized Phase 1B `telemetry.parquet` and `ReplayCommandV1`.
- Produces: `ReplaySource.iter_events(command: ReplayCommandV1) -> Iterator[TelemetryEventV1]`, `pace_seconds(previous: datetime, current: datetime, speed: int) -> float`, and `ReplayController` state transitions.

- [ ] **Step 1: Write deterministic ordering and speed tests**

```python
def test_same_range_has_same_stream_at_every_speed(source: ReplaySource) -> None:
    streams = [tuple(source.iter_events(start_command(speed=speed))) for speed in (1, 100, 1000)]
    identities = [
        tuple((event.sequence, event.message_id, event.source_timestamp, event.model_dump(exclude={"emitted_at"})) for event in stream)
        for stream in streams
    ]
    assert identities[0] == identities[1] == identities[2]


def test_pacing_changes_only_wall_clock_delay() -> None:
    previous = datetime(2020, 3, 1, 0, 0, 0)
    current = datetime(2020, 3, 1, 0, 0, 10)
    assert pace_seconds(previous, current, 1) == 10.0
    assert pace_seconds(previous, current, 1000) == 0.01
```

Also test inclusive start/exclusive end filtering, positive contiguous sequence starting at 1, duplicate/regressing source timestamps fail closed, and pause/resume/stop transitions reject the wrong current state.

- [ ] **Step 2: Run tests and verify the replay module is missing**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_replay.py -q`

Expected: FAIL because `industrial_reliability.replay` does not exist.

- [ ] **Step 3: Implement pure source iteration**

```python
def pace_seconds(previous: datetime, current: datetime, speed: int) -> float:
    if speed not in (1, 100, 1000) or current <= previous:
        raise ReplayContractError("invalid speed or non-increasing source time")
    return (current - previous).total_seconds() / speed


def iter_events(self, command: ReplayCommandV1) -> Iterator[TelemetryEventV1]:
    frame = read_bounded_parquet(self.path, command.range_start, command.range_end)
    validate_strict_source_order(frame)
    for sequence, row in enumerate(frame.itertuples(index=False), start=1):
        message_id = runtime_id("telemetry", command.replay_session_id, str(sequence))
        yield telemetry_event_from_row(row, command, sequence, message_id, self.clock())
```

Read only exact canonical columns with PyArrow filter predicates. Require the Parquet and Phase 1B preparation manifest hashes to equal the champion package source/contract hashes before yielding the first row. A clock callable may be injected for tests; it affects only `emitted_at`.

- [ ] **Step 4: Implement the small replay state machine**

```python
ALLOWED_TRANSITIONS = {
    "CREATED": frozenset({"START"}),
    "RUNNING": frozenset({"PAUSE", "STOP"}),
    "PAUSED": frozenset({"RESUME", "STOP"}),
    "STOPPED": frozenset(),
    "COMPLETED": frozenset(),
    "FAILED": frozenset(),
}
```

`ReplayController.apply(command)` returns a new immutable controller state, preserving session, range, speed, and last sequence; resume continues at the next sequence and source row. Do not add a general workflow engine.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_replay.py -q`

Expected: PASS; the same source/range/session produces the same event identity and ordering after pause/resume.

- [ ] **Step 5: Commit the replay source**

```powershell
git add src/industrial_reliability/replay.py tests/test_replay.py
git commit -m "feat: build deterministic telemetry replay"
```

Expected: this commit has no Kafka service loop or Compose changes.

### Task 4: Connect replay commands to a real local Kafka broker

**Files:**
- Create: `src/industrial_reliability/replay_service.py`
- Create: `tests/integration/test_kafka_replay.py`
- Create: `compose.yaml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `irp.replay.commands.v1` and normalized local Parquet.
- Produces: keyed `TelemetryEventV1` on `irp.telemetry.v1`, `ReplayStatusV1` on `irp.replay.status.v1`, and `QuarantineRecordV1` on `irp.quarantine.v1`.

- [ ] **Step 1: Write the real-broker integration test**

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_kafka_replay_is_ordered_and_reports_completion(kafka_bootstrap: str, replay_fixture: Path) -> None:
    command = start_command(speed=1000, rows=12)
    await publish_command(kafka_bootstrap, command)
    telemetry = await consume_exact(kafka_bootstrap, TELEMETRY_TOPIC, count=12)
    statuses = await consume_until_state(kafka_bootstrap, REPLAY_STATUS_TOPIC, "COMPLETED")
    assert [item.sequence for item in telemetry] == list(range(1, 13))
    assert statuses[-1].last_sequence == 12
```

Add integration cases for pause/resume, duplicate command IDs, malformed command quarantine, stop, and rejection of a second concurrent `START` with `REPLAY_ALREADY_ACTIVE`. Duplicate delivery may repeat Kafka records, but repeated logical outputs must retain the same deterministic IDs.

- [ ] **Step 2: Start Kafka and verify the service test fails before implementation**

Run:

```powershell
docker compose up -d kafka
.\.venv\Scripts\python.exe -m pytest --no-cov tests/integration/test_kafka_replay.py -q
```

Expected: Kafka becomes healthy; tests FAIL because `replay_service` does not exist. Do not remove volumes or other user data during teardown.

- [ ] **Step 3: Implement the async command/service loop**

```python
class ReplayService:
    async def run(self) -> None:
        await self.producer.start()
        await self.consumer.start()
        try:
            async for record in self.consumer:
                await self._handle_record(record)
        finally:
            await self.consumer.stop()
            await self.producer.stop()

    async def _publish(self, topic: str, message: FrozenMessage, key: UUID) -> None:
        await self.producer.send_and_wait(topic, encode_message(message), key=str(key).encode("ascii"))

    async def _handle_start(self, record: ConsumerRecord, command: ReplayCommandV1) -> None:
        controller = ReplayController.created(command.replay_session_id).apply(command)
        task = asyncio.create_task(self._run_session(controller), name=f"replay-{command.replay_session_id}")
        self.sessions[command.replay_session_id] = RunningSession(controller, task)
        await self._publish_status(controller.status("RUNNING"))
        await self.consumer.commit(offset_after(record))
```

Use consumer group `irp-replay-producer-v1`, `enable_auto_commit=False`, `acks="all"`, and idempotent producer mode. `START` validates and registers one background session task, publishes `RUNNING`, then commits the START command so the command consumer remains available for controls. If any session task is active, a different `START` publishes `FAILED` with `REPLAY_ALREADY_ACTIVE` and commits that rejected command. Pause/resume/stop update the registered task, publish the matching status, and then commit their command offsets. Invalid command bytes publish a hash-only quarantine record and then commit that invalid command offset. The replay task uses `asyncio.Event` for pause/resume and checks stop between rows; it publishes `FAILED` on handled task errors. A process crash may require the operator to reissue the same command/session; deterministic telemetry IDs make that replay downstream-safe, while automatic durable session recovery begins in Phase 5.

- [ ] **Step 4: Define the local KRaft broker and pass integration tests**

Write the broker exactly as a one-node local KRaft service:

```yaml
services:
  kafka:
    image: apache/kafka:4.0.0
    hostname: kafka
    ports: ["127.0.0.1:29092:29092"]
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: CONTROLLER://:9093,PLAINTEXT://:9092,HOST://:29092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,HOST://localhost:29092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,HOST:PLAINTEXT
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_NUM_PARTITIONS: 1
    volumes: ["kafka-data:/var/lib/kafka/data"]
    healthcheck:
      test: ["CMD-SHELL", "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1"]
      interval: 5s
      timeout: 5s
      retries: 20

volumes:
  kafka-data:
```

Add `KAFKA_BOOTSTRAP_SERVERS=localhost:29092`, `REPLAY_PARQUET_PATH=data/processed/phase1b/metropt3/telemetry.parquet`, `PHASE1B_PREPARATION_MANIFEST=data/processed/phase1b/metropt3/manifest.json`, and safe non-secret defaults to `.env.example`.

Run:

```powershell
docker compose config --quiet
.\.venv\Scripts\python.exe -m pytest --no-cov tests/integration/test_kafka_replay.py -q
docker compose stop kafka
```

Expected: Compose validates, all integration cases PASS against the real broker, and stop preserves the broker volume for later phases.

- [ ] **Step 5: Commit the Kafka replay slice**

```powershell
git add compose.yaml .env.example src/industrial_reliability/replay_service.py tests/integration/test_kafka_replay.py
git commit -m "feat: stream replay telemetry through Kafka"
```

Expected: one Kafka service commit with localhost-only exposure and no raw data.

### Task 5: Certify deterministic replay and publish bounded evidence

**Files:**
- Create: `docs/results/phase-3-telemetry-contract-kafka-replay.md`
- Modify: `requirements-runtime.txt`

**Interfaces:**
- Consumes: reviewed Phase 2 package, real Kafka, and a bounded real-data holdout range.
- Produces: aggregate Phase 3 replay evidence; private event captures stay under `artifacts/certification/phase-3/`.

- [ ] **Step 1: Fail closed if upstream evidence is absent**

```powershell
$phase1b = Get-Content -LiteralPath docs/results/phase-1b-metrics.json -Raw | ConvertFrom-Json
if ($phase1b.verdict -ne 'FEASIBLE' -or [string]::IsNullOrWhiteSpace($phase1b.selected_model)) { throw 'Phase 1B champion gate failed' }
if (-not (Test-Path -LiteralPath artifacts/champion/manifest.json)) { throw 'Phase 2 champion package is absent' }
```

Expected: the shell stops before Kafka startup if either gate fails.

- [ ] **Step 2: Replay one fixed real range at every supported speed**

Run the replay CLI three times with separate deterministic session UUIDs derived from contract, range, and trial number at speeds 1, 100, and 1000; capture decoded telemetry/status to `artifacts/certification/phase-3/`. Compare ordered `(sequence, source_timestamp, sensors)` tuples after excluding `replay_session_id`, `message_id`, and `emitted_at`; separately assert each trial's IDs are stable when that same session is reissued.

Run: `.\.venv\Scripts\python.exe -m industrial_reliability.replay_service --certify-range-start 2020-03-01T00:00:00 --certify-range-end 2020-03-01T00:02:00 --speeds 1 100 1000 --output artifacts/certification/phase-3`

Expected: all three logical streams are identical, source timestamps remain original naive values, wall-clock duration decreases with speed, and every run reaches `COMPLETED`.

- [ ] **Step 3: Run full local quality and dependency gates**

```powershell
.\.venv\Scripts\python.exe -m pip freeze --exclude-editable | Sort-Object | Set-Content -Encoding ascii requirements-runtime.txt
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest --cov=industrial_reliability --cov-branch --cov-fail-under=80
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
docker compose config --quiet
git diff --check
```

Expected: all commands exit 0 and coverage remains at least 80% branch coverage.

- [ ] **Step 4: Write the evidence-scoped Phase 3 report**

Record exact Git SHA, Kafka image/tag, contract/source/package hashes, bounded source range, event count, per-speed logical-stream hash and duration, pause/resume/stop/quarantine results, commands, and limitations in `docs/results/phase-3-telemetry-contract-kafka-replay.md`. State at-least-once explicitly and do not call the bounded certification a full-data or production pass.

- [ ] **Step 5: Commit the report and lock file**

```powershell
git add requirements-runtime.txt docs/results/phase-3-telemetry-contract-kafka-replay.md
git commit -m "docs: certify deterministic Kafka replay"
git status --short --branch
```

Expected: no captured Kafka payload, Parquet, package, or local environment file is staged.

## Whole-Phase Review and Merge Gate

Phase 4 becomes ready only after contract compatibility, deterministic IDs, ordered replay, source-time invariance, command lifecycle, quarantine behavior, real-Kafka integration, dependency checks, and 80% branch coverage pass. Reviewers must confirm the report claims at-least-once only and `compose.yaml` exposes Kafka exclusively on localhost.
