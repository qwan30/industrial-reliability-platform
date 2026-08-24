# Phase 5 Alert Lifecycle and Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Phase 4 score decisions into calibration-locked, idempotent, restart-safe alert lifecycles with durable PostgreSQL evidence and read APIs.

**Architecture:** A pure state machine consumes `ScoreDecisionV1`; one transactional PostgreSQL store persists the score, lifecycle transition, evidence snapshot, and Kafka outbox row before the consumer commits its offset. A separate dispatcher publishes `AlertEventV1` from the outbox. Policy calibration accepts only the hashed Phase 1B champion score artifact filtered to `split == "calibration"`, so no holdout observation can influence persistence, cooldown, or merge settings.

**Tech Stack:** Python 3.12, Pydantic runtime messages from Phases 2-4, psycopg 3 connection pool, PostgreSQL 17, FastAPI, Kafka, PyArrow, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Begin only after Phase 1B is `FEASIBLE`, `artifacts/phase1b/<run-id>/champion-manifest.json` has a non-null champion, and Phases 2-4 passed their exact artifact gates.
- Phase 1 remains permanent `NOT FEASIBLE` evidence; do not rewrite or tune against its viewed holdout.
- Validate `scores.parquet` against `champion-manifest.json` `artifact_sha256["scores.parquet"]`; filter exactly the champion `model_id` and `split == "calibration"` before selecting policy values.
- Lock `persistence_decisions`, `cooldown_decisions`, and `merge_gap_seconds` before any Phase 1B holdout replay; the runtime loads a policy by SHA-256 and never recalibrates it.
- Kafka delivery remains at-least-once. Deterministic identifiers and PostgreSQL unique constraints provide idempotence; never claim exactly-once delivery.
- PostgreSQL stores replay sessions, score decisions, alert state/events, evidence snapshots, and outbox rows; raw telemetry remains in Parquet.
- A contract or model mismatch fails the replay session closed. A database outage leaves the Kafka offset uncommitted; bounded retry exhaustion marks the replay failed.
- Preserve correlation `replay_session_id -> window_id -> decision_id -> alert_id`.
- Services bind to localhost; auth/RBAC, paging, email/SMS, and policy editing are out of scope.
- Keep branch coverage at or above 80%; synthetic CI evidence and private full-data gate evidence remain separately labeled.

---

### Task 1: Add immutable alert and evidence message contracts

**Files:**
- Modify: `src/industrial_reliability/runtime_messages.py`
- Test: `tests/test_runtime_messages.py`

**Interfaces:**
- Consumes: Phase 4 `ScoreDecisionV1(decision_id, window_id, model_version, score, threshold, is_anomaly, evidence_vector)` and its shared message fields.
- Produces: `AlertAction = Literal["OPENED", "UPDATED", "RESOLVED", "REOPENED"]`, `AlertEventV1`, `FeatureDeviationV1`, and `EvidenceSnapshotV1` Pydantic models; Kafka topic constant `ALERT_EVENTS_TOPIC = "irp.alerts.v1"`.

- [ ] **Step 1: Write failing round-trip and validation tests**

```python
def test_alert_event_round_trips_without_mutation() -> None:
    event = AlertEventV1(
        schema_version="alert-event-v1",
        message_id="msg-alert-1",
        replay_session_id="session-1",
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 4, 18, 0, 5),
        emitted_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
        alert_id="alert-1",
        machine_id="metropt3",
        action="OPENED",
        first_detection=datetime(2020, 4, 18, 0, 0),
        last_detection=datetime(2020, 4, 18, 0, 5),
        decision_ids=("decision-1", "decision-2"),
        policy_sha256="c" * 64,
    )
    assert AlertEventV1.model_validate_json(event.model_dump_json()) == event
    with pytest.raises(ValidationError):
        event.action = "PAGE_OPERATOR"


def test_evidence_snapshot_requires_matching_decision_reference() -> None:
    with pytest.raises(ValidationError, match="decision_id"):
        EvidenceSnapshotV1.model_validate({**valid_evidence_payload(), "decision_id": ""})
```

- [ ] **Step 2: Run the focused tests and observe the missing contracts**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_runtime_messages.py -q`

Expected: FAIL during collection because `AlertEventV1` and `EvidenceSnapshotV1` are not defined.

- [ ] **Step 3: Add the minimal frozen Pydantic models**

```python
ALERT_EVENTS_TOPIC = "irp.alerts.v1"
AlertAction = Literal["OPENED", "UPDATED", "RESOLVED", "REOPENED"]


class FeatureDeviationV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    feature_name: str = Field(min_length=1)
    observed_value: float
    baseline_value: float
    absolute_deviation: float = Field(ge=0.0)


class AlertEventV1(MessageV1):
    schema_version: Literal["alert-event-v1"] = "alert-event-v1"
    alert_id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    action: AlertAction
    first_detection: datetime
    last_detection: datetime
    decision_ids: tuple[str, ...] = Field(min_length=1)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvidenceSnapshotV1(MessageV1):
    schema_version: Literal["evidence-snapshot-v1"] = "evidence-snapshot-v1"
    evidence_id: str = Field(min_length=1)
    alert_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    window_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_deviations: tuple[FeatureDeviationV1, ...]
    data_quality: dict[str, float | int | str | bool]
    model: dict[str, float | int | str | bool]
    system_health: dict[str, float | int | str | bool]
```

- [ ] **Step 4: Run contract tests and the Phase 2-4 contract suite**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_runtime_messages.py tests/test_api.py tests/test_worker.py -q`

Expected: PASS; existing message serialization stays unchanged.

- [ ] **Step 5: Commit the message contract**

```powershell
git add src/industrial_reliability/runtime_messages.py tests/test_runtime_messages.py
git commit -m "feat: add alert evidence message contracts"
```

### Task 2: Calibrate and lock the alert policy without holdout access

**Files:**
- Create: `src/industrial_reliability/alert_policy.py`
- Create: `tests/test_alert_policy.py`

**Interfaces:**
- Consumes: `artifacts/phase1b/<run-id>/scores.parquet` columns `model_id`, `split`, `window_start`, `window_end`, `score`, `threshold`, `is_anomaly`; adjacent `champion-manifest.json` with champion identity, literal split bounds, threshold provenance, and `artifact_sha256["scores.parquet"]`.
- Produces: frozen `LockedAlertPolicyV1` and CLI `.\.venv\Scripts\python.exe -m industrial_reliability.alert_policy lock --champion-manifest <path> --output <path>`; canonical artifact `artifacts/phase5/<run-id>/alert-policy.json` with `schema_version="alert-policy-v1"` and self-verifying `policy_sha256`.

- [ ] **Step 1: Write tests that reject tampering and any non-calibration selection input**

```python
def test_lock_policy_uses_only_champion_calibration_rows(tmp_path: Path) -> None:
    manifest = write_champion_fixture(tmp_path, model_id="statistical")
    policy = lock_alert_policy(manifest, tmp_path / "alert-policy.json")
    assert policy.source_split == "calibration"
    assert policy.model_id == "statistical"
    assert policy.persistence_decisions in (1, 2, 3)
    assert policy.cooldown_decisions in (1, 2, 3, 6)
    assert policy.merge_gap_seconds in (0, 300, 900)


def test_lock_policy_rejects_score_hash_mismatch(tmp_path: Path) -> None:
    manifest = write_champion_fixture(tmp_path, model_id="statistical")
    (tmp_path / "scores.parquet").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="scores.parquet SHA-256"):
        lock_alert_policy(manifest, tmp_path / "alert-policy.json")


def test_candidate_evaluator_rejects_holdout_rows() -> None:
    frame = calibration_frame().assign(split="holdout")
    with pytest.raises(ValueError, match="calibration"):
        select_policy(frame, stride_seconds=300)
```

- [ ] **Step 2: Verify the tests fail before implementation**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_alert_policy.py -q`

Expected: FAIL during collection because `industrial_reliability.alert_policy` does not exist.

- [ ] **Step 3: Implement the fixed candidate ladder and canonical hash**

```python
PERSISTENCE_CANDIDATES = (1, 2, 3)
COOLDOWN_CANDIDATES = (1, 2, 3, 6)
MERGE_GAP_SECONDS_CANDIDATES = (0, 300, 900)


@dataclass(frozen=True)
class LockedAlertPolicyV1:
    schema_version: str
    source_split: str
    source_scores_sha256: str
    source_dataset_sha256: str
    contract_sha256: str
    model_id: str
    model_version: str
    threshold: float
    stride_seconds: int
    persistence_decisions: int
    cooldown_decisions: int
    merge_gap_seconds: int
    calibration_false_episodes_per_day: float
    calibration_time_in_alert: float
    policy_sha256: str


def select_policy(frame: pd.DataFrame, *, stride_seconds: int) -> PolicySelection:
    if set(frame["split"].unique()) != {"calibration"}:
        raise ValueError("policy selection accepts calibration rows only")
    for persistence, cooldown, merge_gap in product(
        PERSISTENCE_CANDIDATES,
        COOLDOWN_CANDIDATES,
        MERGE_GAP_SECONDS_CANDIDATES,
    ):
        metrics = evaluate_candidate(frame, persistence, cooldown, merge_gap, stride_seconds)
        if metrics.false_episodes_per_day <= 1.0 and metrics.time_in_alert <= 0.05:
            return PolicySelection(persistence, cooldown, merge_gap, metrics)
    raise ValueError("no predeclared alert policy satisfies the calibration gates")
```

`lock_alert_policy` must verify the score file hash, manifest self-hash, champion identity, model threshold, exact calibration bounds, and ordered timestamps; select the first passing tuple in the declared product order; write canonical JSON with `sort_keys=True`, `allow_nan=False`, and SHA-256 over the payload without `policy_sha256`. The CLI exposes no split or candidate override flag.

- [ ] **Step 4: Prove the policy lock and leakage guards**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_alert_policy.py -q`

Expected: PASS, including deterministic policy hashes from two identical inputs.

- [ ] **Step 5: Commit the locked calibration policy**

```powershell
git add src/industrial_reliability/alert_policy.py tests/test_alert_policy.py
git commit -m "feat: lock alert policy from calibration evidence"
```

### Task 3: Implement the deterministic alert state machine

**Files:**
- Create: `src/industrial_reliability/alert_state.py`
- Create: `tests/test_alert_state.py`

**Interfaces:**
- Consumes: `LockedAlertPolicyV1`, `ScoreDecisionV1`, and optional persisted `AlertState` for one `(replay_session_id, machine_id)`.
- Produces: pure `transition(state: AlertState, decision: ScoreDecisionV1, policy: LockedAlertPolicyV1) -> TransitionResult`; deterministic IDs `alert_id_for(session_id, first_decision_id)` and `evidence_id_for(alert_id, decision_id)`.

- [ ] **Step 1: Write a table-driven lifecycle test**

```python
@pytest.mark.parametrize(
    ("flags", "actions"),
    [
        ([True, True, False, False], [None, "OPENED", None, "RESOLVED"]),
        ([True, False, True, True], [None, None, None, "OPENED"]),
    ],
)
def test_transition_obeys_persistence_and_cooldown(
    flags: list[bool], actions: list[str | None]
) -> None:
    state = AlertState.empty("session-1", "metropt3")
    actual = []
    for index, flag in enumerate(flags):
        result = transition(state, decision(index, flag), policy(persistence=2, cooldown=2))
        state = result.state
        actual.append(result.event.action if result.event else None)
    assert actual == actions


def test_replay_of_same_decision_is_a_noop() -> None:
    state = AlertState.empty("session-1", "metropt3")
    first = transition(state, decision(1, True), policy(persistence=1, cooldown=1))
    duplicate = transition(first.state, decision(1, True), policy(persistence=1, cooldown=1))
    assert duplicate.event is None
    assert duplicate.state == first.state
```

- [ ] **Step 2: Run the tests and observe the missing state machine**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_alert_state.py -q`

Expected: FAIL during collection because `industrial_reliability.alert_state` does not exist.

- [ ] **Step 3: Implement immutable state transitions**

```python
@dataclass(frozen=True)
class AlertState:
    replay_session_id: str
    machine_id: str
    active_alert_id: str | None
    previous_alert_id: str | None
    first_detection: datetime | None
    last_detection: datetime | None
    resolved_at: datetime | None
    anomaly_decision_ids: tuple[str, ...]
    anomaly_streak: int
    normal_streak: int
    last_decision_id: str | None
    last_source_timestamp: datetime | None


@dataclass(frozen=True)
class TransitionResult:
    state: AlertState
    event: AlertEventV1 | None
    evidence: EvidenceSnapshotV1 | None


def transition(
    state: AlertState,
    decision: ScoreDecisionV1,
    policy: LockedAlertPolicyV1,
) -> TransitionResult:
    if decision.decision_id == state.last_decision_id:
        return TransitionResult(state, None, None)
    if state.last_source_timestamp and decision.source_timestamp <= state.last_source_timestamp:
        raise OrderingViolation(decision.decision_id)
    return _advance_anomaly(state, decision, policy) if decision.is_anomaly else _advance_normal(
        state, decision, policy
    )
```

An `OPENED` transition uses the first decision in the persistence streak; `UPDATED` records each subsequent anomalous decision; `RESOLVED` occurs after `cooldown_decisions` consecutive normal decisions; a new persistence streak whose first detection is within `merge_gap_seconds` of the previous `last_detection` emits `REOPENED` with the previous `alert_id`. A gap or ordering violation returns a closed segment to the consumer and never invents a decision.

- [ ] **Step 4: Run unit tests with branch coverage**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_alert_state.py --cov=industrial_reliability.alert_state --cov-branch --cov-report=term-missing -q`

Expected: PASS with at least 80% branch coverage for `alert_state.py`.

- [ ] **Step 5: Commit the state machine**

```powershell
git add src/industrial_reliability/alert_state.py tests/test_alert_state.py
git commit -m "feat: add deterministic alert lifecycle"
```

### Task 4: Persist score, alert, evidence, and outbox atomically

**Files:**
- Modify: `pyproject.toml`
- Create: `db/migrations/001_alert_lifecycle.sql`
- Create: `src/industrial_reliability/persistence.py`
- Create: `tests/integration/test_alert_persistence.py`
- Modify: `compose.yaml`

**Interfaces:**
- Consumes: `TransitionResult`, `ScoreDecisionV1`, `ReplayStatusV1`, PostgreSQL URL from `DATABASE_URL`.
- Produces: concrete `RuntimeStore` methods `record_replay_status`, `load_alert_state`, `record_decision_transition`, `mark_outbox_published`, `get_replay`, `list_alerts`, and `get_alert_detail`; SQL constraints make repeated decision/message IDs no-ops.

- [ ] **Step 1: Write the real-PostgreSQL transaction tests**

```python
@pytest.mark.integration
def test_record_transition_is_atomic_and_idempotent(runtime_store: RuntimeStore) -> None:
    item = opened_transition_fixture()
    runtime_store.record_decision_transition(item.decision, item.result)
    runtime_store.record_decision_transition(item.decision, item.result)
    assert runtime_store.count("score_decisions") == 1
    assert runtime_store.count("alert_events") == 1
    assert runtime_store.count("evidence_snapshots") == 1
    assert runtime_store.count("alert_outbox") == 1


@pytest.mark.integration
def test_failed_evidence_insert_rolls_back_decision(runtime_store: RuntimeStore) -> None:
    item = opened_transition_fixture(invalid_evidence_id="")
    with pytest.raises(psycopg.errors.CheckViolation):
        runtime_store.record_decision_transition(item.decision, item.result)
    assert runtime_store.count("score_decisions") == 0
```

- [ ] **Step 2: Start PostgreSQL and prove the tests fail before the migration**

Run: `docker compose up -d postgres`

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_alert_persistence.py -q -m integration`

Expected: FAIL with `UndefinedTable` for `score_decisions`.

- [ ] **Step 3: Add the native SQL schema and concrete store**

Add `psycopg[binary]>=3.2,<4` and `psycopg-pool>=3.2,<4` to project dependencies. Mount `./db/migrations:/migrations:ro` into the PostgreSQL service. The migration creates:

```sql
CREATE TABLE replay_sessions (
  replay_session_id text PRIMARY KEY,
  source_dataset_sha256 char(64) NOT NULL,
  contract_sha256 char(64) NOT NULL,
  model_version text NOT NULL,
  state text NOT NULL CHECK (state IN ('CREATED','RUNNING','PAUSED','STOPPED','COMPLETED','FAILED')),
  last_sequence bigint,
  source_timestamp timestamp,
  error_code text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE score_decisions (
  decision_id text PRIMARY KEY,
  replay_session_id text NOT NULL REFERENCES replay_sessions,
  window_id text NOT NULL UNIQUE,
  source_timestamp timestamp NOT NULL,
  model_version text NOT NULL,
  score double precision NOT NULL,
  threshold double precision NOT NULL,
  is_anomaly boolean NOT NULL,
  payload jsonb NOT NULL
);
CREATE TABLE alerts (
  alert_id text PRIMARY KEY,
  replay_session_id text NOT NULL REFERENCES replay_sessions,
  machine_id text NOT NULL,
  state text NOT NULL CHECK (state IN ('OPEN','RESOLVED')),
  first_detection timestamp NOT NULL,
  last_detection timestamp NOT NULL,
  resolved_at timestamp,
  latest_decision_id text NOT NULL REFERENCES score_decisions,
  policy_sha256 char(64) NOT NULL
);
CREATE TABLE alert_events (
  message_id text PRIMARY KEY,
  alert_id text NOT NULL REFERENCES alerts,
  decision_id text NOT NULL REFERENCES score_decisions,
  action text NOT NULL CHECK (action IN ('OPENED','UPDATED','RESOLVED','REOPENED')),
  payload jsonb NOT NULL,
  UNIQUE (alert_id, decision_id, action)
);
CREATE TABLE evidence_snapshots (
  evidence_id text PRIMARY KEY,
  alert_id text NOT NULL REFERENCES alerts,
  decision_id text NOT NULL REFERENCES score_decisions,
  payload jsonb NOT NULL,
  UNIQUE (alert_id, decision_id)
);
CREATE TABLE alert_outbox (
  message_id text PRIMARY KEY REFERENCES alert_events,
  topic text NOT NULL CHECK (topic = 'irp.alerts.v1'),
  message_key text NOT NULL,
  payload jsonb NOT NULL,
  published_at timestamptz
);
```

`RuntimeStore.record_decision_transition` opens one transaction, inserts the decision with `ON CONFLICT DO NOTHING`, locks the current alert row with `FOR UPDATE`, and writes alert/event/evidence/outbox only when the decision insert succeeded. It raises `IdentityMismatch` if an existing decision ID has a different payload.

- [ ] **Step 4: Apply the migration and verify retry/restart behavior**

Run: `docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U irp -d irp -f /migrations/001_alert_lifecycle.sql`

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_alert_persistence.py -q -m integration`

Expected: PASS; duplicate delivery leaves one row per deterministic identity and a new `RuntimeStore` instance reloads the same open alert state.

- [ ] **Step 5: Commit persistence as one reviewable unit**

```powershell
git add pyproject.toml compose.yaml db/migrations/001_alert_lifecycle.sql src/industrial_reliability/persistence.py tests/integration/test_alert_persistence.py
git commit -m "feat: persist alert lifecycle atomically"
```

### Task 5: Consume score decisions and publish the transactional outbox

**Files:**
- Create: `src/industrial_reliability/alert_consumer.py`
- Modify: `src/industrial_reliability/worker.py`
- Create: `tests/test_alert_consumer.py`
- Modify: `tests/test_worker.py`

**Interfaces:**
- Consumes: Kafka `irp.scores.v1`, `RuntimeStore`, locked policy path from `ALERT_POLICY_PATH`, and Phase 3 `KafkaConsumer`/`KafkaProducer` wrappers.
- Produces: `AlertConsumer.process(record) -> ProcessOutcome`, outbox dispatcher to `irp.alerts.v1`, durable replay failure status on mismatch/retry exhaustion; worker subcommand `.\.venv\Scripts\python.exe -m industrial_reliability.worker alerts`.

- [ ] **Step 1: Write failure-first consumer tests**

```python
def test_offset_commits_only_after_database_commit(consumer_harness: ConsumerHarness) -> None:
    consumer_harness.store.fail_next_commit = True
    with pytest.raises(DatabaseUnavailable):
        consumer_harness.process(score_record())
    assert consumer_harness.kafka.committed_offsets == []


def test_contract_mismatch_fails_session_closed(consumer_harness: ConsumerHarness) -> None:
    record = score_record(contract_sha256="f" * 64)
    outcome = consumer_harness.process(record)
    assert outcome == ProcessOutcome.SESSION_FAILED
    assert consumer_harness.store.get_replay("session-1").error_code == "CONTRACT_MISMATCH"


def test_outbox_retry_republishes_same_message_id(dispatcher_harness: DispatcherHarness) -> None:
    dispatcher_harness.publish_twice(opened_outbox_row())
    assert {message.message_id for message in dispatcher_harness.kafka.messages} == {"msg-alert-1"}
```

- [ ] **Step 2: Run focused tests and confirm missing consumer behavior**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_alert_consumer.py tests/test_worker.py -q`

Expected: FAIL because the alert consumer command and outbox dispatcher do not exist.

- [ ] **Step 3: Implement bounded retry and offset ordering**

```python
class AlertConsumer:
    def process(self, record: ConsumerRecord) -> ProcessOutcome:
        decision = ScoreDecisionV1.model_validate_json(record.value)
        self._assert_identity(decision)
        state = self._store.load_alert_state(decision.replay_session_id, decision.machine_id)
        result = transition(state, decision, self._policy)
        self._retry.run(lambda: self._store.record_decision_transition(decision, result))
        self._consumer.commit(record)
        return ProcessOutcome.COMMITTED


class AlertOutboxDispatcher:
    def dispatch_one(self) -> bool:
        row = self._store.next_unpublished_outbox()
        if row is None:
            return False
        self._producer.send(row.topic, key=row.message_key, value=row.payload).get()
        self._store.mark_outbox_published(row.message_id)
        return True
```

Use the existing Phase 4 bounded retry primitive and error taxonomy. An ordering/gap violation closes the current state segment and records quarantine evidence; a policy/model/contract hash mismatch marks the replay `FAILED`; a database failure never commits the score-topic offset.

- [ ] **Step 4: Verify consumer, worker, and retry suites**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_alert_consumer.py tests/test_worker.py -q`

Expected: PASS with the commit call ordered after the durable transaction.

- [ ] **Step 5: Commit alert consumption and outbox delivery**

```powershell
git add src/industrial_reliability/alert_consumer.py src/industrial_reliability/worker.py tests/test_alert_consumer.py tests/test_worker.py
git commit -m "feat: consume scores into durable alerts"
```

### Task 6: Expose replay, alert, and evidence read APIs

**Files:**
- Modify: `src/industrial_reliability/api.py`
- Create: `tests/test_alert_api.py`

**Interfaces:**
- Consumes: `RuntimeStore.get_replay`, `RuntimeStore.list_alerts`, and `RuntimeStore.get_alert_detail`.
- Produces: `GET /v1/replays/{replay_session_id}`, `GET /v1/replays/{replay_session_id}/alerts?after=<alert_id>&limit=<1..100>`, and `GET /v1/alerts/{alert_id}`. Alert detail returns the persisted alert, lifecycle events, score decisions, evidence snapshots, provenance hashes, and `rca=null` until Phase 9.

- [ ] **Step 1: Write API contract tests**

```python
def test_alert_detail_is_traceable(client: TestClient, seeded_alert: SeededAlert) -> None:
    response = client.get(f"/v1/alerts/{seeded_alert.alert_id}")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["replay_session_id"] == seeded_alert.replay_session_id
    assert body["events"][0]["decision_ids"] == [seeded_alert.decision_id]
    assert body["evidence"][0]["contract_sha256"] == seeded_alert.contract_sha256
    assert body["rca"] is None


def test_unknown_alert_uses_stable_error_envelope(client: TestClient) -> None:
    response = client.get("/v1/alerts/missing")
    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "data": None,
        "error": {"code": "ALERT_NOT_FOUND", "message": "Alert not found"},
    }
```

- [ ] **Step 2: Run API tests and observe missing routes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_alert_api.py -q`

Expected: FAIL with HTTP 404 for the new routes.

- [ ] **Step 3: Implement read-only route handlers with bounded pagination**

```python
@app.get("/v1/replays/{replay_session_id}/alerts")
def list_replay_alerts(
    replay_session_id: str,
    after: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ApiEnvelope[AlertPageV1]:
    return success(store.list_alerts(replay_session_id, after=after, limit=limit))


@app.get("/v1/alerts/{alert_id}")
def get_alert(alert_id: str) -> ApiEnvelope[AlertDetailV1]:
    detail = store.get_alert_detail(alert_id)
    if detail is None:
        raise ApiError(404, "ALERT_NOT_FOUND", "Alert not found")
    return success(detail)
```

The response schemas are frozen and `extra="forbid"`. Never return raw telemetry, local paths, database errors, or provider secrets.

- [ ] **Step 4: Run API and security-boundary tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_alert_api.py tests/test_api.py -q`

Expected: PASS; invalid limits return 422 and missing records use stable error codes.

- [ ] **Step 5: Commit the durable read surface**

```powershell
git add src/industrial_reliability/api.py tests/test_alert_api.py
git commit -m "feat: expose replay alert evidence APIs"
```

### Task 7: Certify policy lock, duplicate retry, and restart recovery

**Files:**
- Create: `tests/integration/test_phase5_gate.py`
- Create: `src/industrial_reliability/phase5_gate.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: running Kafka/PostgreSQL/API/worker stack, locked policy artifact, deterministic bounded Phase 1B replay range, champion package.
- Produces: private `artifacts/phase5/<replay-session-id>/phase5-gate.json` with exact code, dataset, contract, model, policy, and input artifact hashes plus booleans `policy_locked_before_holdout`, `duplicate_idempotence_passed`, `restart_recovery_passed`, and `traceability_passed`.

- [ ] **Step 1: Write the end-to-end gate assertion**

```python
@pytest.mark.integration
def test_phase5_gate_survives_duplicate_and_restart(real_stack: RealStack) -> None:
    session_id = real_stack.start_known_alert_replay()
    real_stack.redeliver_first_anomalous_score(session_id)
    real_stack.restart_alert_worker()
    alert = real_stack.wait_for_resolved_alert(session_id)
    assert real_stack.count_decision(alert.latest_decision_id) == 1
    assert real_stack.trace_ids(alert.alert_id) == {
        "replay_session_id": session_id,
        "window_id": alert.window_id,
        "decision_id": alert.latest_decision_id,
        "alert_id": alert.alert_id,
    }
```

- [ ] **Step 2: Run the gate before the verifier exists**

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_phase5_gate.py -q -m integration`

Expected: FAIL because `phase5_gate.write_gate` and the restart helpers are absent.

- [ ] **Step 3: Add the fail-closed gate writer and README commands**

```python
REQUIRED_PASSES = (
    "policy_locked_before_holdout",
    "duplicate_idempotence_passed",
    "restart_recovery_passed",
    "traceability_passed",
)


def write_gate(output: Path, evidence: Phase5Evidence) -> None:
    payload = evidence.to_dict()
    if not all(payload[name] is True for name in REQUIRED_PASSES):
        raise ValueError("Phase 5 gate evidence is incomplete")
    atomic_write_json(output, with_sha256(payload))
```

Document separate commands for synthetic CI and private Phase 1B replay. The private command must first assert that `alert-policy.json` exists and its recorded lock timestamp precedes the holdout replay session creation timestamp.

- [ ] **Step 4: Run all Phase 5 and repository gates**

Run: `.\.venv\Scripts\python.exe -m ruff check .`

Run: `.\.venv\Scripts\python.exe -m ruff format --check .`

Run: `.\.venv\Scripts\python.exe -m mypy src`

Run: `.\.venv\Scripts\python.exe -m pytest -q --cov-branch --cov-fail-under=80`

Run: `.\.venv\Scripts\python.exe -m pip check`

Run: `.\.venv\Scripts\python.exe -m build`

Expected: every command exits 0; the integration gate produces one self-hashed JSON artifact and does not commit private scores, raw telemetry, or model binaries.

- [ ] **Step 5: Commit Phase 5 certification**

```powershell
git add src/industrial_reliability/phase5_gate.py tests/integration/test_phase5_gate.py README.md
git commit -m "test: certify alert persistence recovery"
```

## Phase 5 Exit Gate

Move Phase 6 to `Ready` only when the policy artifact was derived from the hashed champion calibration rows before holdout replay, duplicate score delivery produces no duplicate durable records, restart restores the same open lifecycle, every alert resolves to its score/evidence/provenance chain, all local quality commands pass, and `phase5-gate.json` records the exact hashes. A policy-calibration failure or identity mismatch blocks the phase; do not tune on holdout.
