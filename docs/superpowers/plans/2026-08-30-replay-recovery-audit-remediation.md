# Replay Recovery Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make replay recovery lossless and protocol-complete across crashes, pause/resume, and stop while preserving the committed migration and lint fixes.

**Architecture:** Keep `replay_checkpoints` as the durable source of replay position and control state. A zero-event checkpoint has no source cursor; after every acknowledged telemetry event the checkpoint stores that event's sequence/timestamp, and every terminal recovery path publishes the same `ReplayStatusV1` barrier used by a normal replay. Control commands update checkpoint state atomically without replacing the original START command payload.

**Tech Stack:** Python 3.12, asyncio, Pydantic runtime messages, psycopg 3/PostgreSQL 17, aiokafka, pytest/pytest-asyncio, Ruff, mypy, Docker Compose.

## Global Constraints

- Execute from an isolated worktree created with `superpowers:using-git-worktrees`; do not implement on the moving `fix/data-pipeline-audit-remediation` checkout.
- Pin and record the exact implementation base SHA before editing; this plan was re-verified against clean committed HEAD `714ead9573d4e2c84f83c7f2cf171f988fca4d31`.
- Preserve deterministic telemetry IDs: recovery starts at `last_sequence + 1` and never renumbers an already acknowledged event.
- Preserve the original START command in `command_payload`; PAUSE, RESUME, and STOP change only checkpoint state.
- Persist state before publishing the matching status or allowing the Kafka command offset to commit.
- Do not add a dependency, table, migration, background service, or generalized replay framework.
- Keep PostgreSQL/Kafka evidence separate from unit evidence; live tests must fail rather than skip when `REQUIRE_INTEGRATION_SERVICES=1`.
- Maintain at least 80% branch coverage and leave Ruff, mypy, `git diff --check`, and `docker compose config --quiet` clean.

## Current-State Finding Map

| Review finding | Current state at `714ead9` | Planned coverage |
|---|---|---|
| Crash after START but before event 1 skips the range-start row | Open: initial checkpoint stores `command.range_start`, while resumed filtering is exclusive | Task 1 |
| Recovery writes `COMPLETED` to PostgreSQL but publishes no terminal status | Open: worker cannot flush its final window or commit offsets | Task 1 |
| PAUSE/RESUME/STOP are not durable | Open: handlers publish status without changing checkpoint state | Task 2 |
| Replay lacks a completed migration dependency | Resolved by `6a6b5a1`; `replay-producer` now depends on successful `db-migrate` | Task 3 regression gate |
| Ruff import-order failure in `tests/test_worker.py` | Resolved at `714ead9`; `ruff check tests/test_worker.py` passes | Task 3 regression gate |

## File Structure

- Modify `src/industrial_reliability/replay_service.py`: checkpoint boundary semantics, recovery status publication, recovery control events, and durable command handling.
- Modify `src/industrial_reliability/persistence.py`: typed checkpoint state and an atomic state-only update that preserves the START payload and cursor.
- Modify `tests/test_replay_service.py`: deterministic unit regressions for zero-event recovery, recovery terminal status, recovery failure, paused startup, and command durability.
- Modify `tests/test_persistence.py`: SQL contract for state-only checkpoint updates and missing-checkpoint failure.
- Modify `tests/integration/test_kafka_replay.py`: live PostgreSQL recovery from sequence zero and durable PAUSED/STOPPED state verification.
- Verify only `compose.yaml` and `tests/test_worker.py`: both committed corrections are already present; do not edit them unless an earlier implementation task directly causes a regression.

---

### Task 1: Make crash recovery lossless and publish terminal status

**Files:**
- Modify: `src/industrial_reliability/replay_service.py:118-144,227-281`
- Test: `tests/test_replay_service.py:177-288`

**Interfaces:**
- Consumes: `ReplayCheckpoint.command`, `ReplayCheckpoint.last_sequence`, `ReplayCheckpoint.source_timestamp`, `ReplaySource.iter_events(...)`, and `ReplayController.mark_completed(...)`/`mark_failed(...)`.
- Produces: `ReplayService.resume_checkpoint(checkpoint: ReplayCheckpoint, pause_event: asyncio.Event | None = None, stop_event: asyncio.Event | None = None) -> None`.
- Guarantees: `last_sequence == 0` uses `source_timestamp=None`; recovery includes the row at `range_start`; successful recovery publishes `COMPLETED`; failed recovery records and publishes `FAILED`.

- [ ] **Step 1: Add the zero-event checkpoint regression**

Add this test after `test_replay_service_records_checkpoints_during_streaming` in `tests/test_replay_service.py`:

```python
@pytest.mark.asyncio
async def test_start_checkpoint_has_no_cursor_before_first_publish(tmp_path: Path) -> None:
    source = ReplaySource(
        _create_mock_parquet(tmp_path, n_rows=5),
        expected_contract_sha256="b" * 64,
    )
    store = MagicMock(spec=RuntimeStore)
    service = ReplayService(
        KafkaSettings("localhost:9092"),
        source,
        store=store,
        enable_pacing=False,
    )
    service.publish_telemetry = AsyncMock(side_effect=RuntimeError("simulated crash"))  # type: ignore[method-assign]
    service.publish_status = AsyncMock()  # type: ignore[method-assign]
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
    )

    await service.handle_command(command)
    assert service.active_session is not None
    await service.active_session.task

    initial = store.record_replay_checkpoint.call_args_list[0]
    assert initial.args == (command, "RUNNING", 0, None)
```

- [ ] **Step 2: Run the zero-event regression and observe RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_replay_service.py::test_start_checkpoint_has_no_cursor_before_first_publish -v
```

Expected: FAIL because the fourth positional argument is `command.range_start`, not `None`.

- [ ] **Step 3: Add success and failure recovery status regressions**

Add these tests after the zero-event checkpoint test:

```python
@pytest.mark.asyncio
async def test_resume_from_zero_replays_range_start_and_publishes_completed(
    tmp_path: Path,
) -> None:
    source = ReplaySource(
        _create_mock_parquet(tmp_path, n_rows=6),
        expected_contract_sha256="b" * 64,
    )
    store = MagicMock(spec=RuntimeStore)
    service = ReplayService(
        KafkaSettings("localhost:9092"),
        source,
        store=store,
        enable_pacing=False,
    )
    telemetry = []
    statuses = []
    service.publish_telemetry = AsyncMock(side_effect=telemetry.append)  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=statuses.append)  # type: ignore[method-assign]
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
    )
    expected = list(source.iter_events(command))
    checkpoint = ReplayCheckpoint(
        replay_session_id=command.replay_session_id,
        command=command,
        state="RUNNING",
        last_sequence=0,
        source_timestamp=None,
    )

    await service.resume_checkpoint(checkpoint)

    assert [(event.sequence, event.source_timestamp) for event in telemetry] == [
        (event.sequence, event.source_timestamp) for event in expected
    ]
    assert statuses[-1].state == "COMPLETED"
    assert statuses[-1].last_sequence == len(expected)


@pytest.mark.asyncio
async def test_resume_failure_records_and_publishes_failed(tmp_path: Path) -> None:
    source = ReplaySource(
        _create_mock_parquet(tmp_path, n_rows=3),
        expected_contract_sha256="b" * 64,
    )
    store = MagicMock(spec=RuntimeStore)
    service = ReplayService(
        KafkaSettings("localhost:9092"),
        source,
        store=store,
        enable_pacing=False,
    )
    statuses = []
    service.publish_telemetry = AsyncMock(side_effect=RuntimeError("publish failed"))  # type: ignore[method-assign]
    service.publish_status = AsyncMock(side_effect=statuses.append)  # type: ignore[method-assign]
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
    )
    checkpoint = ReplayCheckpoint(
        replay_session_id=command.replay_session_id,
        command=command,
        state="RUNNING",
        last_sequence=0,
        source_timestamp=None,
    )

    await service.resume_checkpoint(checkpoint)

    failed = store.record_replay_checkpoint.call_args_list[-1]
    assert failed.kwargs["state"] == "FAILED"
    assert statuses[-1].state == "FAILED"
    assert statuses[-1].error_code == "REPLAY_STREAM_ERROR"
```

- [ ] **Step 4: Run the recovery status tests and observe RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_replay_service.py::test_resume_from_zero_replays_range_start_and_publishes_completed tests/test_replay_service.py::test_resume_failure_records_and_publishes_failed -v
```

Expected: the success test FAILS because no `COMPLETED` status is published; the failure test FAILS because the exception escapes without recording or publishing `FAILED`.

- [ ] **Step 5: Store no cursor before the first acknowledged event**

In `ReplayService._handle_start_command`, replace the initial checkpoint call with:

```python
if self.store is not None:
    self.store.record_replay_checkpoint(command, "RUNNING", 0, None)
```

Do not change `ReplaySource.iter_events`: its existing `greater_equal` behavior is correct when `resume_from_timestamp is None`, and its exclusive `greater` behavior is correct after an acknowledged event.

- [ ] **Step 6: Replace `resume_checkpoint` with a protocol-complete recovery path**

Replace the method in `src/industrial_reliability/replay_service.py` with:

```python
async def resume_checkpoint(
    self,
    checkpoint: ReplayCheckpoint,
    pause_event: asyncio.Event | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    if pause_event is None:
        pause_event = asyncio.Event()
        pause_event.set()
    if stop_event is None:
        stop_event = asyncio.Event()

    ctrl = ReplayController.created(
        checkpoint.replay_session_id,
        checkpoint.command.source_dataset_sha256,
        checkpoint.command.contract_sha256,
    ).apply(checkpoint.command)
    last_sequence = checkpoint.last_sequence
    last_timestamp = checkpoint.source_timestamp

    try:
        for event in self.source.iter_events(
            checkpoint.command,
            start_sequence=checkpoint.last_sequence + 1,
            resume_from_timestamp=checkpoint.source_timestamp,
        ):
            await pause_event.wait()
            if stop_event.is_set():
                return
            await self.publish_telemetry(event)
            last_sequence = event.sequence
            last_timestamp = event.source_timestamp
            if self.store is not None:
                self.store.record_replay_checkpoint(
                    command=checkpoint.command,
                    state="RUNNING",
                    last_sequence=last_sequence,
                    source_timestamp=last_timestamp,
                )

        await pause_event.wait()
        if stop_event.is_set():
            return
        terminal_timestamp = (
            last_timestamp or checkpoint.command.range_start or checkpoint.command.source_timestamp
        )
        ctrl = ctrl.mark_completed(last_sequence, terminal_timestamp)
        if self.store is not None:
            self.store.record_replay_checkpoint(
                command=checkpoint.command,
                state="COMPLETED",
                last_sequence=last_sequence,
                source_timestamp=terminal_timestamp,
            )
        await self.publish_status(ctrl.status())
    except Exception as err:
        logger.exception("Recovered replay session failed: %s", err)
        terminal_timestamp = (
            last_timestamp or checkpoint.command.range_start or checkpoint.command.source_timestamp
        )
        ctrl = ctrl.mark_failed(
            error_code="REPLAY_STREAM_ERROR",
            last_sequence=last_sequence,
            source_timestamp=terminal_timestamp,
        )
        if self.store is not None:
            self.store.record_replay_checkpoint(
                command=checkpoint.command,
                state="FAILED",
                last_sequence=last_sequence,
                source_timestamp=terminal_timestamp,
            )
        await self.publish_status(ctrl.status())
```

- [ ] **Step 7: Run Task 1 GREEN verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_replay_service.py -v
.\.venv\Scripts\python.exe -m mypy src/industrial_reliability/replay_service.py
```

Expected: all replay-service tests PASS and mypy reports `Success: no issues found`.

- [ ] **Step 8: Commit Task 1**

```powershell
git add src/industrial_reliability/replay_service.py tests/test_replay_service.py
git commit -m "fix: make replay restart lossless"
```

---

### Task 2: Persist and restore replay control state

**Files:**
- Modify: `src/industrial_reliability/persistence.py:54-60,219-305`
- Modify: `src/industrial_reliability/replay_service.py:12,25,95-144,283-403`
- Test: `tests/test_persistence.py:438-513`
- Test: `tests/test_replay_service.py:63-94,210-288`

**Interfaces:**
- Consumes: Task 1's optional `pause_event` and `stop_event` arguments on `resume_checkpoint`.
- Produces: `ReplayCheckpointState`, `RuntimeStore.update_replay_checkpoint_state(replay_session_id: UUID, state: ReplayCheckpointState) -> None`, and `_checkpoint_state(pause_event: asyncio.Event, stop_event: asyncio.Event) -> ReplayCheckpointState`.
- Guarantees: state-only updates never replace `command_payload`, `last_sequence`, or `source_timestamp`; PAUSED recovery waits; RESUME restarts from the durable cursor; STOPPED sessions are not returned by `load_incomplete_replays()`.

- [ ] **Step 1: Add the state-only persistence tests**

Add this test after `test_store_replay_checkpoints` in `tests/test_persistence.py`:

```python
def test_update_replay_checkpoint_state_preserves_cursor_and_command() -> None:
    store = RuntimeStore("postgresql://test:5432/test")
    session_id = uuid4()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.rowcount = 1
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with patch("psycopg.connect", return_value=mock_conn):
        store.update_replay_checkpoint_state(session_id, "PAUSED")

    query, params = mock_cur.execute.call_args.args
    assert "UPDATE replay_checkpoints" in query
    assert "SET state = %s" in query
    assert "command_payload" not in query
    assert "last_sequence" not in query
    assert "source_timestamp" not in query
    assert params == ("PAUSED", str(session_id))
    assert mock_conn.commit.called


def test_update_replay_checkpoint_state_rejects_missing_session() -> None:
    store = RuntimeStore("postgresql://test:5432/test")
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.rowcount = 0
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    with (
        patch("psycopg.connect", return_value=mock_conn),
        pytest.raises(LookupError, match="Replay checkpoint not found"),
    ):
        store.update_replay_checkpoint_state(uuid4(), "STOPPED")
```

- [ ] **Step 2: Run the persistence tests and observe RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_persistence.py::test_update_replay_checkpoint_state_preserves_cursor_and_command tests/test_persistence.py::test_update_replay_checkpoint_state_rejects_missing_session -v
```

Expected: FAIL with `AttributeError` because `update_replay_checkpoint_state` does not exist.

- [ ] **Step 3: Add a typed checkpoint state and atomic update**

In `src/industrial_reliability/persistence.py`, define the alias above `ReplayCheckpoint` and use it for the dataclass plus both write methods:

```python
type ReplayCheckpointState = Literal[
    "RUNNING",
    "PAUSED",
    "STOPPED",
    "COMPLETED",
    "FAILED",
]


@dataclass(frozen=True, slots=True)
class ReplayCheckpoint:
    replay_session_id: UUID
    command: ReplayCommandV1
    state: ReplayCheckpointState
    last_sequence: int
    source_timestamp: datetime | None
```

Change `record_replay_checkpoint(..., state: str, ...)` to `state: ReplayCheckpointState`, then add this method immediately after it:

```python
def update_replay_checkpoint_state(
    self,
    replay_session_id: UUID,
    state: ReplayCheckpointState,
) -> None:
    with psycopg.connect(self.db_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE replay_checkpoints
            SET state = %s, updated_at = now()
            WHERE replay_session_id = %s;
            """,
            (state, str(replay_session_id)),
        )
        if cur.rowcount != 1:
            raise LookupError(f"Replay checkpoint not found: {replay_session_id}")
        conn.commit()
```

- [ ] **Step 4: Run the persistence tests GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_persistence.py -v
.\.venv\Scripts\python.exe -m mypy src/industrial_reliability/persistence.py
```

Expected: all persistence tests PASS and mypy reports no issues.

- [ ] **Step 5: Add durable control and paused-recovery tests**

Add `import asyncio` at the top of `tests/test_replay_service.py`. Update `test_replay_service_pause_resume_stop_lifecycle` to construct `store = MagicMock(spec=RuntimeStore)` and pass `store=store` into `ReplayService`, then append:

```python
assert [call.args[1] for call in store.update_replay_checkpoint_state.call_args_list] == [
    "PAUSED",
    "RUNNING",
    "STOPPED",
]
```

Add this test after the lifecycle test:

```python
@pytest.mark.asyncio
async def test_paused_checkpoint_waits_until_resume(tmp_path: Path) -> None:
    source = ReplaySource(
        _create_mock_parquet(tmp_path, n_rows=10),
        expected_contract_sha256="b" * 64,
    )
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
        range_end=datetime(2020, 3, 1, 1),
    )
    first_three = list(source.iter_events(command))[:3]
    checkpoint = ReplayCheckpoint(
        replay_session_id=command.replay_session_id,
        command=command,
        state="PAUSED",
        last_sequence=3,
        source_timestamp=first_three[-1].source_timestamp,
    )
    store = MagicMock(spec=RuntimeStore)
    store.load_incomplete_replays.return_value = (checkpoint,)
    service = ReplayService(
        KafkaSettings("localhost:9092"),
        source,
        store=store,
        enable_pacing=False,
    )
    telemetry = []
    service.publish_telemetry = AsyncMock(side_effect=telemetry.append)  # type: ignore[method-assign]
    service.publish_status = AsyncMock()  # type: ignore[method-assign]

    with (
        patch("industrial_reliability.replay_service.AIOKafkaProducer") as producer_cls,
        patch("industrial_reliability.replay_service.AIOKafkaConsumer") as consumer_cls,
    ):
        producer_cls.return_value = AsyncMock()
        consumer_cls.return_value = AsyncMock()
        await service.start()
        assert service.active_session is not None
        await asyncio.sleep(0)
        assert service.active_session.controller.state == "PAUSED"
        assert telemetry == []

        resume = make_sample_replay_command(
            action="RESUME",
            session_id=command.replay_session_id,
            speed=1000,
        )
        await service.handle_command(resume)
        await service.active_session.task
        assert telemetry[0].sequence == 4
        assert telemetry[0].source_timestamp > first_three[-1].source_timestamp
        await service.stop()
```

- [ ] **Step 6: Run the durable-control tests and observe RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_replay_service.py::test_replay_service_pause_resume_stop_lifecycle tests/test_replay_service.py::test_paused_checkpoint_waits_until_resume -v
```

Expected: FAIL because command handlers never call `update_replay_checkpoint_state`, startup restores a `CREATED` controller, and recovery does not receive pause/stop events.

- [ ] **Step 7: Add the shared control-state selector**

Change the persistence import in `src/industrial_reliability/replay_service.py` and add this function below `RunningSession`:

```python
from industrial_reliability.persistence import (
    ReplayCheckpoint,
    ReplayCheckpointState,
    RuntimeStore,
)


def _checkpoint_state(
    pause_event: asyncio.Event,
    stop_event: asyncio.Event,
) -> ReplayCheckpointState:
    if stop_event.is_set():
        return "STOPPED"
    if not pause_event.is_set():
        return "PAUSED"
    return "RUNNING"
```

- [ ] **Step 8: Restore the controller and event state during startup**

Import `replace` with `from dataclasses import dataclass, replace`. Replace the single-incomplete-checkpoint branch in `ReplayService.start` with:

```python
if incomplete:
    checkpoint = incomplete[0]
    if checkpoint.state not in ("RUNNING", "PAUSED"):
        raise RuntimeError(f"cannot resume checkpoint in state {checkpoint.state}")
    pause_event = asyncio.Event()
    if checkpoint.state == "RUNNING":
        pause_event.set()
    stop_event = asyncio.Event()
    controller = ReplayController.created(
        checkpoint.replay_session_id,
        checkpoint.command.source_dataset_sha256,
        checkpoint.command.contract_sha256,
    ).apply(checkpoint.command)
    controller = replace(
        controller,
        state=checkpoint.state,
        last_sequence=checkpoint.last_sequence,
        current_source_timestamp=checkpoint.source_timestamp,
    )
    task = asyncio.create_task(
        self.resume_checkpoint(checkpoint, pause_event, stop_event),
        name=f"replay-resume-{checkpoint.replay_session_id}",
    )
    self.active_session = RunningSession(
        controller=controller,
        task=task,
        pause_event=pause_event,
        stop_event=stop_event,
    )
```

- [ ] **Step 9: Persist control state before publishing status**

Replace the three control handlers with:

```python
async def _handle_pause_command(self, command: ReplayCommandV1) -> None:
    if (
        self.active_session
        and self.active_session.controller.session_id == command.replay_session_id
        and not self.active_session.task.done()
    ):
        ctrl = self.active_session.controller.apply(command)
        if self.store is not None:
            self.store.update_replay_checkpoint_state(ctrl.session_id, "PAUSED")
        self.active_session.controller = ctrl
        self.active_session.pause_event.clear()
        await self.publish_status(ctrl.status())


async def _handle_resume_command(self, command: ReplayCommandV1) -> None:
    if (
        self.active_session
        and self.active_session.controller.session_id == command.replay_session_id
        and not self.active_session.task.done()
    ):
        ctrl = self.active_session.controller.apply(command)
        if self.store is not None:
            self.store.update_replay_checkpoint_state(ctrl.session_id, "RUNNING")
        self.active_session.controller = ctrl
        self.active_session.pause_event.set()
        await self.publish_status(ctrl.status())


async def _handle_stop_command(self, command: ReplayCommandV1) -> None:
    if (
        self.active_session
        and self.active_session.controller.session_id == command.replay_session_id
        and not self.active_session.task.done()
    ):
        ctrl = self.active_session.controller.apply(command)
        if self.store is not None:
            self.store.update_replay_checkpoint_state(ctrl.session_id, "STOPPED")
        self.active_session.controller = ctrl
        self.active_session.stop_event.set()
        self.active_session.pause_event.set()
        await self.publish_status(ctrl.status())
```

- [ ] **Step 10: Prevent in-flight telemetry from overwriting PAUSED or STOPPED**

In both `resume_checkpoint` and `_run_replay_session`, replace the per-event `state="RUNNING"` argument with:

```python
state = (_checkpoint_state(pause_event, stop_event),)
```

In `_run_replay_session`, insert this guard immediately before `ctrl = ctrl.mark_completed(...)`:

```python
await pause_event.wait()
if stop_event.is_set():
    return
```

Task 1 already added the equivalent final barrier to `resume_checkpoint`.

- [ ] **Step 11: Run Task 2 GREEN verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_persistence.py tests/test_replay_service.py -v
.\.venv\Scripts\python.exe -m mypy src/industrial_reliability/persistence.py src/industrial_reliability/replay_service.py
```

Expected: all selected tests PASS and mypy reports no issues.

- [ ] **Step 12: Commit Task 2**

```powershell
git add src/industrial_reliability/persistence.py src/industrial_reliability/replay_service.py tests/test_persistence.py tests/test_replay_service.py
git commit -m "fix: persist replay control state"
```

---

### Task 3: Prove live recovery and retain resolved audit fixes

**Files:**
- Test: `tests/integration/test_kafka_replay.py:119-167`
- Verify: `compose.yaml:18-32,86-105`
- Verify: `tests/test_worker.py:375-379,394-398`

**Interfaces:**
- Consumes: Task 1 recovery behavior and Task 2 `RuntimeStore.update_replay_checkpoint_state(...)`.
- Produces: live PostgreSQL evidence that a zero-event checkpoint preserves the first telemetry row, publishes a terminal status, and excludes STOPPED checkpoints from recovery.
- Guarantees: the earlier migration and lint findings remain closed without new production changes.

- [ ] **Step 1: Add the live zero-event recovery regression**

Add `REPLAY_STATUS_TOPIC` and `ReplayStatusV1` to the runtime-message imports in `tests/integration/test_kafka_replay.py`, then add:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_replay_resume_from_zero_is_lossless_and_terminal(
    store: RuntimeStore,
    tmp_path: Path,
) -> None:
    source = ReplaySource(
        _create_mock_parquet(tmp_path, n_rows=6),
        expected_contract_sha256="b" * 64,
    )
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
        range_start=datetime(2020, 3, 1),
        range_end=datetime(2020, 3, 1, 0, 1),
        source_dataset_sha256=source.identity.source_dataset_sha256,
        contract_sha256=source.identity.contract_sha256,
    )
    expected = list(source.iter_events(command))
    store.record_replay_checkpoint(command, "RUNNING", 0, None)
    checkpoint = store.load_replay_checkpoint(command.replay_session_id)
    assert checkpoint is not None
    service = ReplayService(
        KafkaSettings("localhost:29092"),
        source,
        store=store,
        enable_pacing=False,
    )
    service.producer = AsyncMock()

    await service.resume_checkpoint(checkpoint)

    telemetry = [
        decode_message(call.kwargs["value"], TelemetryEventV1)
        for call in service.producer.send_and_wait.await_args_list
        if call.args[0] == TELEMETRY_TOPIC
    ]
    statuses = [
        decode_message(call.kwargs["value"], ReplayStatusV1)
        for call in service.producer.send_and_wait.await_args_list
        if call.args[0] == REPLAY_STATUS_TOPIC
    ]
    assert [(event.sequence, event.source_timestamp) for event in telemetry] == [
        (event.sequence, event.source_timestamp) for event in expected
    ]
    assert statuses[-1].state == "COMPLETED"
    assert statuses[-1].last_sequence == len(expected)
    saved = store.load_replay_checkpoint(command.replay_session_id)
    assert saved is not None
    assert saved.state == "COMPLETED"
```

- [ ] **Step 2: Add the live durable-control regression**

Add this test below the zero-event recovery test:

```python
@pytest.mark.integration
def test_replay_checkpoint_control_state_is_durable(store: RuntimeStore) -> None:
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
    )
    store.record_replay_checkpoint(command, "RUNNING", 0, None)

    store.update_replay_checkpoint_state(command.replay_session_id, "PAUSED")
    paused = store.load_replay_checkpoint(command.replay_session_id)
    assert paused is not None
    assert paused.state == "PAUSED"
    assert paused.command == command
    assert any(
        checkpoint.replay_session_id == command.replay_session_id
        for checkpoint in store.load_incomplete_replays()
    )

    store.update_replay_checkpoint_state(command.replay_session_id, "STOPPED")
    stopped = store.load_replay_checkpoint(command.replay_session_id)
    assert stopped is not None
    assert stopped.state == "STOPPED"
    assert stopped.command == command
    assert all(
        checkpoint.replay_session_id != command.replay_session_id
        for checkpoint in store.load_incomplete_replays()
    )
```

- [ ] **Step 3: Start live dependencies and apply migrations**

Run:

```powershell
docker compose up -d --wait postgres kafka
docker compose run --rm db-migrate
```

Expected: PostgreSQL and Kafka report healthy; `db-migrate` exits `0` after applying or recognizing all migrations.

- [ ] **Step 4: Run integration tests with skips forbidden**

Run:

```powershell
$env:REQUIRE_INTEGRATION_SERVICES='1'
$env:DATABASE_URL='postgresql://irp:irp_password@localhost:5432/irp'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_kafka_replay.py -v
```

Expected: every test in the file PASS; no test reports SKIPPED.

- [ ] **Step 5: Run static and Compose regression gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
docker compose config --quiet
git diff --check
```

Expected: all four commands exit `0`. `compose.yaml` still contains `db-migrate: condition: service_completed_successfully` under `replay-producer`; Ruff no longer reports the import block at `tests/test_worker.py`.

- [ ] **Step 6: Run the complete non-live regression and coverage gate**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not integration and not slow" --cov=industrial_reliability --cov-report=term-missing
```

Expected: all selected tests PASS and total branch coverage is at least 80%.

- [ ] **Step 7: Commit Task 3**

```powershell
git add tests/integration/test_kafka_replay.py
git commit -m "test: prove durable replay recovery"
```

- [ ] **Step 8: Stop temporary live dependencies without deleting volumes**

```powershell
docker compose stop kafka postgres
```

Expected: the two containers stop; PostgreSQL and Kafka volumes remain available for later drills.

---

## Final Acceptance Gate

- [ ] Record `git rev-parse HEAD` and include that exact SHA in the implementation handoff.
- [ ] Confirm `git status --short` contains no unexpected implementation changes.
- [ ] Confirm the zero-event test proves the range-start timestamp is present, not merely that sequences are gap-free.
- [ ] Confirm recovered `COMPLETED` reaches `irp.replay.status.v1`, allowing `StreamingWorker._complete_session` to flush its final feature window and commit offsets.
- [ ] Confirm PAUSED remains in `load_incomplete_replays()`, STOPPED does not, and neither control update changes the stored START command or cursor.
- [ ] Confirm the three commits are independently reviewable and each review is performed against its immutable commit SHA.

## Self-Review Result

- Spec coverage: all five original review findings are mapped; three open findings have implementation tasks and two resolved findings have regression gates.
- Type consistency: `ReplayCheckpointState` is the single state type used by persistence and replay service; `resume_checkpoint` has one final signature across all tasks.
- Scope: no schema, dependency, service, or unrelated replay behavior is added.
