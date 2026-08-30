# Data Pipeline Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the audited data path fail closed on identity, preserve runtime state across restarts, prevent false model/evidence promotion, and leave exact-SHA integration and recovery proof.

**Architecture:** Keep the existing Parquet → Kafka → feature/scoring → PostgreSQL flow. Add verification only at trust boundaries, persist the alert state that is currently process-local, and require verified attestations before external mutation. Reuse Pydantic, psycopg, aiokafka, Prometheus, MLflow, and pytest; do not add a new data platform.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, PyArrow, aiokafka, PostgreSQL 17/psycopg 3, MLflow 3, Prometheus/Grafana, Docker Compose, pytest.

## Global Constraints

- Execute from a worktree created with `using-git-worktrees`; audited baseline: `2d054c65db8ce63ff6aebbf48d472c5c0586b0fc`.
- Preserve `docs/data-pipeline-audit-2026-08-29.md` and all Phase 1/1B results as historical evidence.
- Python remains `>=3.12,<3.13`. Add no dependency unless the existing stack cannot do the work.
- `RESEARCH_CANDIDATE + NOT_FEASIBLE + RESEARCH_ONLY` must never acquire the MLflow `champion` alias.
- Evidence level is derived from observed dependencies, never from a CLI argument or credential presence.
- Do not clip uncertain sensor values; quarantine hard violations with metadata and payload SHA-256.
- Use RED → GREEN → REFACTOR. Every task ends in an independently recoverable commit.
- Maintain at least 80% branch-aware coverage.
- Do not overwrite datasets, packages, receipts, or certification artifacts. Corrected evaluation uses versioned `phase1c` paths.
- Retention defaults to `RETAIN_UNTIL_MANUAL_APPROVAL`; no automatic deletion is added.

---

## File Map

**Create**

- `db/migrations/004_alert_runtime_state.sql` — durable pre-alert state.
- `src/industrial_reliability/artifact_integrity.py` — shared manifest/byte verification.
- `src/industrial_reliability/migrations.py` — ordered migration runner.
- `tests/test_artifact_integrity.py` and `tests/test_migrations.py`.
- `tests/integration/test_data_path.py` — dependency-backed critical path.
- `ops/prometheus/alerts.yml` — bounded data-quality alerts.
- `scripts/test_postgres_restore.ps1` and `docs/DATA_RETENTION.md`.

**Modify**

- `persistence.py`, `alert_consumer.py`, `alert_service.py` — durable state and quarantine.
- `phase1b_features.py`, `phase1b_benchmark.py`, `ml_lifecycle.py` — offline boundary verification.
- `replay.py`, `replay_service.py`, `worker.py`, `compose.yaml` — authenticated runtime lineage.
- `phase7_gate.py`, `phase8_live_gate.py`, `phase9_live_gate.py`, `release_certification.py` — truthful promotion/evidence.
- `phase1b_contracts.py`, `phase1b_data.py`, `runtime_messages.py`, `docs/DATA_CARD.md` — data semantics.
- `.github/workflows/ci.yml`, `ops/prometheus/prometheus.yml`, `README.md`, `docs/RUNBOOK.md`.

---

## Gate A — Data Correctness and Identity

### Task 1: Persist pre-alert state transactionally

**Files:**
- Create: `db/migrations/004_alert_runtime_state.sql`
- Modify: `src/industrial_reliability/persistence.py:190-355`
- Test: `tests/integration/test_alert_persistence.py`

**Interfaces:**
- Consumes: `AlertState` and `TransitionResult`.
- Produces: `RuntimeStore.load_alert_state(...) -> AlertState` backed by `alert_runtime_states`; `record_decision_transition` stores `result.state` in the decision transaction.

- [ ] **Step 1: Write the restart regression**

~~~python
@pytest.mark.integration
def test_two_anomalies_open_one_alert_across_restart(store: RuntimeStore) -> None:
    session_id = uuid4()
    policy = replace(_make_policy(), persistence_decisions=2)
    first = _make_decision(session_id, is_anomaly=True)
    second = replace(
        _make_decision(session_id, is_anomaly=True),
        decision_id=uuid4(),
        window_id=uuid4(),
        source_timestamp=first.source_timestamp + timedelta(minutes=5),
    )
    result1 = transition(AlertState.empty(session_id, "metropt3"), first, policy)
    assert result1.event is None
    store.record_decision_transition(first, result1)

    restarted = RuntimeStore(TEST_DB_URL)
    recovered = restarted.load_alert_state(session_id, "metropt3")
    assert recovered.anomaly_streak == 1
    assert recovered.anomaly_decision_ids == (first.decision_id,)

    result2 = transition(recovered, second, policy)
    assert result2.event is not None
    restarted.record_decision_transition(second, result2)
    assert restarted.count("alerts", "replay_session_id", str(session_id)) == 1
    assert restarted.count("alert_outbox") == 1
~~~

- [ ] **Step 2: Run RED**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_alert_persistence.py::test_two_anomalies_open_one_alert_across_restart -v
~~~

Expected: FAIL because recovered `anomaly_streak` is zero.

- [ ] **Step 3: Add the state table**

~~~sql
CREATE TABLE IF NOT EXISTS alert_runtime_states (
  replay_session_id text NOT NULL REFERENCES replay_sessions(replay_session_id) ON DELETE CASCADE,
  machine_id text NOT NULL,
  payload jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (replay_session_id, machine_id)
);
~~~

- [ ] **Step 4: Add exact state serialization**

~~~python
def _state_payload(state: AlertState) -> dict[str, object]:
    return {
        "replay_session_id": str(state.replay_session_id),
        "machine_id": state.machine_id,
        "active_alert_id": str(state.active_alert_id) if state.active_alert_id else None,
        "previous_alert_id": str(state.previous_alert_id) if state.previous_alert_id else None,
        "first_detection": state.first_detection.isoformat() if state.first_detection else None,
        "last_detection": state.last_detection.isoformat() if state.last_detection else None,
        "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
        "anomaly_decision_ids": [str(value) for value in state.anomaly_decision_ids],
        "anomaly_streak": state.anomaly_streak,
        "normal_streak": state.normal_streak,
        "last_decision_id": str(state.last_decision_id) if state.last_decision_id else None,
        "last_source_timestamp": (
            state.last_source_timestamp.isoformat() if state.last_source_timestamp else None
        ),
    }
~~~

Add the inverse:

~~~python
def _state_from_payload(payload: Mapping[str, object]) -> AlertState:
    def optional_uuid(name: str) -> UUID | None:
        value = payload[name]
        return UUID(str(value)) if value is not None else None

    def optional_datetime(name: str) -> datetime | None:
        value = payload[name]
        return datetime.fromisoformat(str(value)) if value is not None else None

    ids = cast(list[object], payload["anomaly_decision_ids"])
    return AlertState(
        replay_session_id=UUID(str(payload["replay_session_id"])),
        machine_id=str(payload["machine_id"]),
        active_alert_id=optional_uuid("active_alert_id"),
        previous_alert_id=optional_uuid("previous_alert_id"),
        first_detection=optional_datetime("first_detection"),
        last_detection=optional_datetime("last_detection"),
        resolved_at=optional_datetime("resolved_at"),
        anomaly_decision_ids=tuple(UUID(str(value)) for value in ids),
        anomaly_streak=int(cast(int, payload["anomaly_streak"])),
        normal_streak=int(cast(int, payload["normal_streak"])),
        last_decision_id=optional_uuid("last_decision_id"),
        last_source_timestamp=optional_datetime("last_source_timestamp"),
    )
~~~

- [ ] **Step 5: Upsert state before the existing commit**

~~~python
cur.execute(
    """
    INSERT INTO alert_runtime_states (replay_session_id, machine_id, payload)
    VALUES (%s, %s, %s)
    ON CONFLICT (replay_session_id, machine_id) DO UPDATE SET
      payload = EXCLUDED.payload,
      updated_at = now()
    """,
    (
        str(result.state.replay_session_id),
        result.state.machine_id,
        json.dumps(_state_payload(result.state)),
    ),
)
~~~

`load_alert_state` must return this row before falling back to `AlertState.empty`.

- [ ] **Step 6: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_alert_state.py tests/test_alert_consumer.py tests/test_persistence.py tests/integration/test_alert_persistence.py -v
~~~

Expected: PASS with PostgreSQL available; redelivery remains idempotent.

- [ ] **Step 7: Commit**

~~~powershell
git add db/migrations/004_alert_runtime_state.sql src/industrial_reliability/persistence.py tests/integration/test_alert_persistence.py
git commit -m "fix: persist alert runtime state"
~~~

### Task 2: Add one shared artifact-integrity verifier

**Files:**
- Create: `src/industrial_reliability/artifact_integrity.py`
- Test: `tests/test_artifact_integrity.py`

**Interfaces:**
- Produces: `load_self_hashed_manifest(path: Path) -> dict[str, Any]`.
- Produces: `verify_file_sha256(path: Path, expected: str, label: str) -> str`.
- Produces: `verify_prepared_parquet(path: Path, expected_contract_sha256: str) -> PreparedArtifactIdentity`.

- [ ] **Step 1: Write tamper tests**

~~~python
def test_verified_prepared_parquet_rejects_byte_tamper(tmp_path: Path) -> None:
    parquet = tmp_path / "telemetry.parquet"
    parquet.write_bytes(b"approved")
    manifest = {
        "archive_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "output_sha256": hashlib.sha256(b"approved").hexdigest(),
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    parquet.write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError, match="telemetry.parquet SHA-256"):
        verify_prepared_parquet(parquet, "b" * 64)


def test_manifest_metadata_tamper_fails(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"contract_sha256": "b" * 64, "manifest_sha256": "0" * 64}),
        encoding="utf-8",
    )
    with pytest.raises(ArtifactIntegrityError, match="manifest self-hash"):
        load_self_hashed_manifest(path)
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_integrity.py -v
~~~

Expected: collection FAIL because the module is absent.

- [ ] **Step 3: Implement the verifier**

~~~python
class ArtifactIntegrityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedArtifactIdentity:
    source_dataset_sha256: str
    contract_sha256: str
    parquet_sha256: str
    manifest_sha256: str


def load_self_hashed_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    supplied = str(data.get("manifest_sha256", ""))
    unhashed = {key: value for key, value in data.items() if key != "manifest_sha256"}
    canonical = json.dumps(unhashed, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if supplied != actual:
        raise ArtifactIntegrityError(
            f"{path.name} manifest self-hash mismatch: expected {supplied}, got {actual}"
        )
    return data


def verify_file_sha256(path: Path, expected: str, label: str) -> str:
    actual = sha256_file(path)
    if actual != expected:
        raise ArtifactIntegrityError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")
    return actual


def verify_prepared_parquet(path: Path, expected_contract_sha256: str) -> PreparedArtifactIdentity:
    manifest = load_self_hashed_manifest(path.with_name("manifest.json"))
    contract = str(manifest["contract_sha256"])
    if contract != expected_contract_sha256:
        raise ArtifactIntegrityError(
            f"prepared contract SHA-256 mismatch: expected {expected_contract_sha256}, got {contract}"
        )
    parquet_sha = verify_file_sha256(path, str(manifest["output_sha256"]), "telemetry.parquet")
    return PreparedArtifactIdentity(
        source_dataset_sha256=str(manifest["archive_sha256"]),
        contract_sha256=contract,
        parquet_sha256=parquet_sha,
        manifest_sha256=str(manifest["manifest_sha256"]),
    )
~~~

- [ ] **Step 4: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_integrity.py -v
~~~

Expected: PASS.

- [ ] **Step 5: Commit**

~~~powershell
git add src/industrial_reliability/artifact_integrity.py tests/test_artifact_integrity.py
git commit -m "feat: verify data artifact identity"
~~~

### Task 3: Enforce integrity at offline boundaries

**Files:**
- Modify: `src/industrial_reliability/phase1b_features.py:224-289`
- Modify: `src/industrial_reliability/phase1b_benchmark.py:174-192`
- Modify: `src/industrial_reliability/ml_lifecycle.py:290-322`
- Modify: `src/industrial_reliability/package_champion.py:48-98`
- Test: `tests/test_phase1b_features.py`, `tests/test_phase1b_benchmark.py`, `tests/test_ml_lifecycle.py`

**Interfaces:**
- Consumes: Task 2 verifier functions.
- Produces: feature build, benchmark, and reproduction fail before reading unverified bytes.

- [ ] **Step 1: Add one tamper test per boundary**

~~~python
def test_build_features_rejects_tampered_prepared_parquet(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    samples = _generate_samples_for_bins(
        (25, 25, 25, 25, 25, 25, 25, 25),
        datetime(2020, 2, 1),
    )
    frame = pd.DataFrame(
        [
            {
                "timestamp": sample.timestamp,
                **dict(zip(PHASE1B.analog_columns, sample.analog, strict=True)),
                **dict(
                    zip(
                        tuple(
                            name
                            for name in PHASE1B.digital_columns
                            if name in PHASE1B.predictor_columns
                        ),
                        sample.digital,
                        strict=True,
                    )
                ),
                "lps": 0,
            }
            for sample in samples
        ]
    )
    parquet = prepared / "telemetry.parquet"
    frame.to_parquet(parquet, index=False)
    manifest = {
        "archive_sha256": "a" * 64,
        "contract_sha256": str(phase1b_contract_manifest()["contract_sha256"]),
        "output_sha256": sha256_file(parquet),
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    (prepared / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    parquet.write_bytes(parquet.read_bytes() + b"tamper")
    with pytest.raises(ArtifactIntegrityError, match="telemetry.parquet SHA-256"):
        build_phase1b_features(prepared, tmp_path / "features.parquet")


def test_benchmark_rejects_tampered_features(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    telemetry = prepared / "telemetry.parquet"
    telemetry.write_bytes(b"verified-prepared-bytes")
    data_manifest = {
        "archive_sha256": "a" * 64,
        "contract_sha256": str(phase1b_contract_manifest()["contract_sha256"]),
        "output_sha256": sha256_file(telemetry),
    }
    data_canonical = json.dumps(data_manifest, sort_keys=True, separators=(",", ":"))
    data_manifest["manifest_sha256"] = hashlib.sha256(data_canonical.encode()).hexdigest()
    (prepared / "manifest.json").write_text(json.dumps(data_manifest), encoding="utf-8")

    features = tmp_path / "features.parquet"
    pd.DataFrame(
        {
            "split": ["train", "calibration", "holdout"],
            "window_start": pd.to_datetime(["2020-02-01", "2020-02-22", "2020-03-02"]),
            "window_end": pd.to_datetime(
                ["2020-02-01 00:30", "2020-02-22 00:30", "2020-03-02 00:30"]
            ),
            "tp2_mean": [1.0, 2.0, 3.0],
        }
    ).to_parquet(features, index=False)
    feature_manifest = {
        "contract_sha256": data_manifest["contract_sha256"],
        "data_manifest_sha256": data_manifest["manifest_sha256"],
        "output_sha256": sha256_file(features),
        "active_feature_names": ["tp2_mean"],
    }
    feature_canonical = json.dumps(feature_manifest, sort_keys=True, separators=(",", ":"))
    feature_manifest["manifest_sha256"] = hashlib.sha256(feature_canonical.encode()).hexdigest()
    features.with_name("feature_manifest.json").write_text(
        json.dumps(feature_manifest),
        encoding="utf-8",
    )
    features.write_bytes(features.read_bytes() + b"tamper")
    with pytest.raises(ArtifactIntegrityError, match="features.parquet SHA-256"):
        run_phase1b_benchmark(prepared, features, tmp_path / "artifacts")
~~~

Add the reproduction boundary test:

~~~python
def test_reproduction_rejects_tampered_features(tmp_path: Path) -> None:
    run_dir, features, package = _create_mock_feasible_phase1b_run(tmp_path)
    features.write_bytes(features.read_bytes() + b"tamper")
    with pytest.raises(ArtifactIntegrityError, match="features.parquet SHA-256"):
        reproduce_candidate(
            ReproductionRequest(
                features_path=features,
                phase1b_run_dir=run_dir,
                champion_package=package,
            ),
            mlflow_client=FakeMlflowClient(),
        )
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase1b_features.py tests/test_phase1b_benchmark.py tests/test_ml_lifecycle.py -v
~~~

Expected: tamper tests FAIL because consumers trust manifest strings.

- [ ] **Step 3: Verify before each read**

Feature boundary:

~~~python
contract_sha = str(phase1b_contract_manifest()["contract_sha256"])
verified_data = verify_prepared_parquet(parquet_file, contract_sha)
data_manifest = load_self_hashed_manifest(manifest_file)
df = pq.read_table(parquet_file).to_pandas()
~~~

Benchmark boundary:

~~~python
verified_data = verify_prepared_parquet(
    prepared_dir / "telemetry.parquet",
    str(phase1b_contract_manifest()["contract_sha256"]),
)
feature_manifest = load_self_hashed_manifest(feature_path.with_name("feature_manifest.json"))
verify_file_sha256(feature_path, str(feature_manifest["output_sha256"]), "features.parquet")
if feature_manifest["data_manifest_sha256"] != verified_data.manifest_sha256:
    raise ArtifactIntegrityError("feature manifest does not reference verified prepared data")
~~~

Add required `feature_output_sha256: str = Field(pattern=HEX_64_PATTERN)` to `ChampionManifest`, populate it in both package builders, and verify the supplied features path before reproduction.

- [ ] **Step 4: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_integrity.py tests/test_phase1b_features.py tests/test_phase1b_benchmark.py tests/test_ml_lifecycle.py -v
~~~

Expected: PASS; every tampered artifact fails at its next consumer.

- [ ] **Step 5: Commit**

~~~powershell
git add src/industrial_reliability/phase1b_features.py src/industrial_reliability/phase1b_benchmark.py src/industrial_reliability/ml_lifecycle.py src/industrial_reliability/package_champion.py tests/test_phase1b_features.py tests/test_phase1b_benchmark.py tests/test_ml_lifecycle.py
git commit -m "fix: verify offline pipeline artifacts"
~~~

### Task 4: Bind replay and worker identity to verified source bytes

**Files:**
- Modify: `src/industrial_reliability/replay.py:180-258`
- Modify: `src/industrial_reliability/replay_service.py:173-208,372-410`
- Modify: `src/industrial_reliability/worker.py:188-219,340-394`
- Modify: `compose.yaml:70-104`
- Test: `tests/test_replay.py`, `tests/test_replay_service.py`, `tests/test_worker.py`

**Interfaces:**
- Consumes: Task 2 `PreparedArtifactIdentity` and `verify_prepared_parquet`.
- Produces: `ReplaySource.identity`; replay events use it, and mismatched command/event identities are quarantined without scoring.

- [ ] **Step 1: Write source and worker mismatch tests**

~~~python
def write_prepared_manifest(
    parquet: Path,
    source_dataset_sha256: str,
    contract_sha256: str,
) -> None:
    manifest = {
        "archive_sha256": source_dataset_sha256,
        "contract_sha256": contract_sha256,
        "output_sha256": sha256_file(parquet),
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    parquet.with_name("manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def test_replay_source_uses_verified_identity(tmp_path: Path) -> None:
    parquet = _create_mock_parquet(tmp_path)
    write_prepared_manifest(parquet, source_dataset_sha256="a" * 64, contract_sha256="b" * 64)
    source = ReplaySource(parquet, expected_contract_sha256="b" * 64)
    command = _start_command(
        uuid4(),
        datetime(2020, 3, 1),
        datetime(2020, 3, 1, 0, 1),
    )
    event = next(source.iter_events(command))
    assert event.source_dataset_sha256 == source.identity.source_dataset_sha256
    assert event.contract_sha256 == source.identity.contract_sha256


@pytest.mark.asyncio
async def test_worker_quarantines_event_identity_mismatch(
    worker_settings: WorkerSettings,
) -> None:
    scoring_client = AsyncMock()
    metrics = build_runtime_metrics(CollectorRegistry())
    worker = StreamingWorker(
        worker_settings,
        scoring_client=scoring_client,
        metrics=metrics,
    )
    worker.producer = AsyncMock()
    event = replace(make_sample_telemetry_event(), source_dataset_sha256="f" * 64)
    await worker.handle_record(MockKafkaRecord(TELEMETRY_TOPIC, encode_message(event)))
    scoring_client.score.assert_not_awaited()
    assert metrics.telemetry_events.labels(outcome="quarantined")._value.get() == 1
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_replay.py tests/test_replay_service.py tests/test_worker.py -v
~~~

Expected: FAIL because `ReplaySource` has no verified identity and the worker replaces event identity.

- [ ] **Step 3: Verify the source and reject command mismatch**

~~~python
def __init__(
    self,
    parquet_path: Path,
    expected_contract_sha256: str,
    clock: Callable[[], datetime] | None = None,
) -> None:
    self.path = parquet_path.resolve()
    self.identity = verify_prepared_parquet(self.path, expected_contract_sha256)
    self.clock = clock if clock is not None else (lambda: datetime.now(UTC))
~~~

Before starting a replay:

~~~python
if (
    command.source_dataset_sha256 != self.source.identity.source_dataset_sha256
    or command.contract_sha256 != self.source.identity.contract_sha256
):
    failed = ReplayController.created(
        command.replay_session_id,
        self.source.identity.source_dataset_sha256,
        self.source.identity.contract_sha256,
    ).mark_failed(
        "REPLAY_SOURCE_IDENTITY_MISMATCH",
        0,
        command.source_timestamp,
    )
    await self.publish_status(failed.status())
    return
~~~

Build each `TelemetryEventV1` from `self.identity`, never from command-provided hashes.

- [ ] **Step 4: Fail closed in the worker**

Immediately after decoding telemetry:

~~~python
if (
    event.source_dataset_sha256 != self.settings.source_dataset_sha256
    or event.contract_sha256 != self.settings.contract_sha256
):
    await self.publish_quarantine(
        raw_bytes,
        topic,
        partition,
        offset,
        "TELEMETRY_IDENTITY_MISMATCH",
        "telemetry identity does not match scoring package",
    )
    await self._fail_session(
        event.replay_session_id,
        "TELEMETRY_IDENTITY_MISMATCH",
        self.last_sequence.get(event.replay_session_id, 0),
        event.source_timestamp,
    )
    return
~~~

Only after this guard may the worker create `OnlineFeatureBuilder` from the event hashes.

- [ ] **Step 5: Use the existing replay environment variable**

~~~python
default_parquet = Path(
    os.environ.get(
        "REPLAY_PARQUET_PATH",
        "data/processed/phase1b/metropt3/telemetry.parquet",
    )
)
parser.add_argument("--parquet", type=Path, default=default_parquet)
~~~

Keep the Compose mount and `REPLAY_PARQUET_PATH=/runtime/data/metropt3/telemetry.parquet`. Remove `PHASE1B_PREPARATION_MANIFEST` if the sibling manifest is derived and no caller reads that variable.

- [ ] **Step 6: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_replay.py tests/test_replay_service.py tests/test_worker.py -v
docker compose config --quiet
~~~

Expected: PASS; Compose resolves the mounted file and mismatched events never reach scoring.

- [ ] **Step 7: Commit**

~~~powershell
git add src/industrial_reliability/replay.py src/industrial_reliability/replay_service.py src/industrial_reliability/worker.py compose.yaml tests/test_replay.py tests/test_replay_service.py tests/test_worker.py
git commit -m "fix: authenticate replay data identity"
~~~

### Task 5: Persist replay checkpoints before committing START

**Files:**
- Modify: `db/migrations/004_alert_runtime_state.sql`
- Modify: `src/industrial_reliability/persistence.py`
- Modify: `src/industrial_reliability/replay_service.py:132-140,173-309`
- Modify: `compose.yaml:70-84`
- Modify: `tests/test_replay_service.py`
- Test: `tests/integration/test_kafka_replay.py`

**Interfaces:**
- Produces: `ReplayCheckpoint`, `record_replay_checkpoint(...)`, `load_incomplete_replays() -> tuple[ReplayCheckpoint, ...]`, and `ReplayService.resume_checkpoint(...) -> None`.
- Changes: `ReplayService.__init__(..., store: RuntimeStore)`; Compose supplies `DATABASE_URL`.
- Guarantees: START offset commits only after durable session state; restart resumes from `last_sequence + 1` and `source_timestamp`.

- [ ] **Step 1: Write the crash/restart regression**

~~~python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_replay_resumes_from_durable_checkpoint(
    store: RuntimeStore,
    prepared_parquet: Path,
) -> None:
    source = ReplaySource(prepared_parquet, expected_contract_sha256="b" * 64)
    command = make_sample_replay_command(
        action="START",
        session_id=uuid4(),
        speed=1000,
        range_start=datetime(2020, 3, 1),
        range_end=datetime(2020, 3, 1, 1),
        source_dataset_sha256=source.identity.source_dataset_sha256,
        contract_sha256=source.identity.contract_sha256,
    )
    first_batch = list(islice(source.iter_events(command), 25))
    store.record_replay_checkpoint(
        command=command,
        state="RUNNING",
        last_sequence=first_batch[-1].sequence,
        source_timestamp=first_batch[-1].source_timestamp,
    )
    checkpoint = store.load_incomplete_replays()[0]
    service = ReplayService(
        KafkaSettings("localhost:29092"),
        source,
        store=store,
        enable_pacing=False,
    )
    service.producer = AsyncMock()
    await service.resume_checkpoint(checkpoint)

    payloads = [
        decode_message(call.kwargs["value"], TelemetryEventV1)
        for call in service.producer.send_and_wait.await_args_list
        if call.args[0] == TELEMETRY_TOPIC
    ]
    assert payloads[0].sequence == 26
    assert payloads[0].source_timestamp > first_batch[-1].source_timestamp
    assert [event.sequence for event in payloads] == list(range(26, payloads[-1].sequence + 1))
    assert store.load_replay_checkpoint(command.replay_session_id).state == "COMPLETED"
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_kafka_replay.py::test_replay_resumes_from_durable_checkpoint -v
~~~

Expected: FAIL because checkpoint persistence and resume APIs do not exist.

- [ ] **Step 3: Add the checkpoint table**

Append to migration 004:

~~~sql
CREATE TABLE IF NOT EXISTS replay_checkpoints (
  replay_session_id text PRIMARY KEY,
  command_payload jsonb NOT NULL,
  state text NOT NULL CHECK (state IN ('RUNNING','PAUSED','STOPPED','COMPLETED','FAILED')),
  last_sequence bigint NOT NULL DEFAULT 0,
  source_timestamp timestamp,
  updated_at timestamptz NOT NULL DEFAULT now()
);
~~~

Add:

~~~python
@dataclass(frozen=True, slots=True)
class ReplayCheckpoint:
    replay_session_id: UUID
    command: ReplayCommandV1
    state: Literal["RUNNING", "PAUSED", "STOPPED", "COMPLETED", "FAILED"]
    last_sequence: int
    source_timestamp: datetime | None
~~~

- [ ] **Step 4: Persist before Kafka commit and after acknowledged events**

Add `store: RuntimeStore` to the replay service. On START, persist `state="RUNNING"` before `handle_command_record` returns. Since `run()` commits only afterward, a crash cannot lose the accepted command. After each successful `publish_telemetry`, update sequence/timestamp.

Implement:

~~~python
async def resume_checkpoint(self, checkpoint: ReplayCheckpoint) -> None:
    last_sequence = checkpoint.last_sequence
    last_timestamp = checkpoint.source_timestamp
    for event in self.source.iter_events(
        checkpoint.command,
        start_sequence=checkpoint.last_sequence + 1,
        resume_from_timestamp=checkpoint.source_timestamp,
    ):
        if last_timestamp is not None and event.source_timestamp <= last_timestamp:
            continue
        await self.publish_telemetry(event)
        last_sequence = event.sequence
        last_timestamp = event.source_timestamp
        self.store.record_replay_checkpoint(
            command=checkpoint.command,
            state="RUNNING",
            last_sequence=last_sequence,
            source_timestamp=last_timestamp,
        )
    self.store.record_replay_checkpoint(
        command=checkpoint.command,
        state="COMPLETED",
        last_sequence=last_sequence,
        source_timestamp=last_timestamp,
    )
~~~

During `start()` schedule the single incomplete checkpoint (the service already permits one active session):

~~~python
incomplete = self.store.load_incomplete_replays()
if len(incomplete) > 1:
    raise RuntimeError("multiple incomplete replay sessions require operator resolution")
if incomplete:
    checkpoint = incomplete[0]
    task = asyncio.create_task(self.resume_checkpoint(checkpoint))
    self.active_session = RunningSession(
        controller=ReplayController.created(
            checkpoint.replay_session_id,
            checkpoint.command.source_dataset_sha256,
            checkpoint.command.contract_sha256,
        ),
        task=task,
        pause_event=asyncio.Event(),
        stop_event=asyncio.Event(),
    )
~~~

In Compose add `DATABASE_URL=postgresql://irp:irp_password@postgres:5432/irp` to `replay-producer` and make it depend on healthy PostgreSQL and completed `db-migrate`.

- [ ] **Step 5: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_replay_service.py tests/integration/test_kafka_replay.py -v
~~~

Expected: PASS with one gap-free logical sequence and deterministic IDs.

- [ ] **Step 6: Commit**

~~~powershell
git add db/migrations/004_alert_runtime_state.sql src/industrial_reliability/persistence.py src/industrial_reliability/replay_service.py compose.yaml tests/test_replay_service.py tests/integration/test_kafka_replay.py
git commit -m "fix: persist replay checkpoints"
~~~

### Task 6: Enforce full-window split containment

**Files:**
- Modify: `src/industrial_reliability/phase1b_features.py:119-195`
- Test: `tests/test_phase1b_features.py`
- Modify: `docs/DATA_CARD.md:39-49`

**Interfaces:**
- Produces: `_window_is_within_split(window: Phase1BWindow, split: Split) -> bool`.
- Guarantees: every emitted window is wholly inside its declared split.

- [ ] **Step 1: Add the exact calibration-boundary test**

~~~python
def test_window_never_crosses_train_calibration_boundary() -> None:
    samples = _generate_samples_for_bins(
        (24, 24, 24, 24, 24, 24, 24),
        datetime(2020, 2, 21, 23, 30),
    )
    windows = list(iter_phase1b_windows(samples, PHASE1B))
    assert all(
        window.split != "calibration" or window.window_start >= PHASE1B.calibration.start
        for window in windows
    )
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase1b_features.py::test_window_never_crosses_train_calibration_boundary -v
~~~

Expected: FAIL with a calibration window starting `2020-02-21 23:55`.

- [ ] **Step 3: Add the containment guard**

~~~python
def _window_is_within_split(window: Phase1BWindow, split: Split) -> bool:
    return split.start <= window.window_start and window.window_end <= split.end
~~~

Build the candidate window, look up the matching `Split` object, and yield only if the guard passes. Add `cross_split_windows_skipped` to the feature manifest; stop hard-coding `invalid_bins_skipped=0`.

- [ ] **Step 4: Run GREEN and document versioning**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase1b_features.py tests/test_online_features.py -v
~~~

Expected: PASS. Add to `DATA_CARD.md` that boundary-crossing windows are rejected and corrected full-data output is versioned instead of replacing Phase 1B.

- [ ] **Step 5: Commit**

~~~powershell
git add src/industrial_reliability/phase1b_features.py tests/test_phase1b_features.py docs/DATA_CARD.md
git commit -m "fix: enforce feature split containment"
~~~

---

## Gate B — Truthful ML Promotion and Certification

### Task 7: Turn Phase 7 into a pre-promotion attestation

**Files:**
- Modify: `src/industrial_reliability/phase7_gate.py`
- Modify: `src/industrial_reliability/ml_lifecycle.py:148-155,426-493`
- Modify: `src/industrial_reliability/ml_provenance.py`
- Test: `tests/test_phase7_gate.py`, `tests/test_ml_lifecycle.py`, `tests/integration/test_mlflow_promotion.py`

**Interfaces:**
- Produces: `load_phase7_attestation(path: Path) -> Phase7GateResult` with a verified self-hash.
- Changes: `PromotionRequest` requires `phase7_gate: Path` and non-optional `champion_package: Path`.
- Guarantees: all validation occurs before model-version or alias mutation.

- [ ] **Step 1: Write fail-closed promotion tests**

~~~python
def _write_gate(
    path: Path,
    candidate: CandidateResult,
    package: Path,
) -> Path:
    gate = Phase7GateResult(
        schema_version="phase7-gate-v2",
        source_git_sha=candidate.provenance.source_git_sha,
        timestamp=datetime.now(UTC).isoformat(),
        verdict="PASS",
        threshold_delta=0.0,
        golden_scores_max_delta=0.0,
        candidate_run_id=candidate.run_id,
        reproduction_run_id="reproduction-run",
        package_manifest_sha256=sha256_file(package / "manifest.json"),
        alert_policy_sha256=candidate.provenance.alert_policy_sha256,
        verified_hashes={
            "dataset_sha256": candidate.provenance.dataset_sha256,
            "contract_sha256": candidate.provenance.contract_sha256,
            "feature_schema_sha256": candidate.provenance.feature_schema_sha256,
            "source_git_sha": candidate.provenance.source_git_sha,
            "champion_package_sha256": candidate.provenance.champion_package_sha256,
            "alert_policy_sha256": candidate.provenance.alert_policy_sha256,
        },
        reasons=[],
        self_sha256="",
    ).with_computed_hash()
    write_phase7_gate_report(path, gate)
    return path


def test_promotion_rejects_research_package_before_mutation(tmp_path: Path) -> None:
    run_dir, _features, package = _create_mock_feasible_phase1b_run(tmp_path)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "package_role": "RESEARCH_CANDIDATE",
            "evaluation_verdict": "NOT_FEASIBLE",
            "operational_status": "RESEARCH_ONLY",
            "source_champion_schema": "phase1b-run-v1",
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    client = FakeMlflowClient()
    candidate = import_candidate(ImportCandidateRequest(package, run_dir), mlflow_client=client)
    gate = _write_gate(tmp_path / "phase7-gate.json", candidate, package)
    with pytest.raises(ValueError, match="package_role"):
        promote_candidate(
            PromotionRequest(
                run_id=candidate.run_id,
                approver="reliability-lead",
                expected_source_git_sha=candidate.provenance.source_git_sha,
                output=tmp_path / "receipt.json",
                champion_package=package,
                phase7_gate=gate,
            ),
            mlflow_client=client,
        )
    assert client.model_versions == {}
    assert client.aliases == {}
~~~

Add one parameterized precondition test:

~~~python
@pytest.mark.parametrize(
    "case,error",
    [
        ("fail_gate", "must PASS"),
        ("wrong_run", "candidate run"),
        ("wrong_git", "Source Git SHA"),
        ("wrong_package", "package SHA"),
        ("existing_receipt", "Refusing to overwrite"),
    ],
)
def test_promotion_preconditions_do_not_mutate_registry(
    tmp_path: Path,
    case: str,
    error: str,
) -> None:
    run_dir, _features, package = _create_mock_feasible_phase1b_run(tmp_path)
    client = FakeMlflowClient()
    candidate = import_candidate(ImportCandidateRequest(package, run_dir), mlflow_client=client)
    gate_path = _write_gate(tmp_path / "phase7-gate.json", candidate, package)
    gate_data = json.loads(gate_path.read_text(encoding="utf-8"))
    expected_git = candidate.provenance.source_git_sha
    receipt_path = tmp_path / "receipt.json"
    if case == "fail_gate":
        gate_data["verdict"] = "FAIL"
    elif case == "wrong_run":
        gate_data["candidate_run_id"] = "other-run"
    elif case == "wrong_git":
        expected_git = "f" * 40
    elif case == "wrong_package":
        gate_data["package_manifest_sha256"] = "f" * 64
    elif case == "existing_receipt":
        receipt_path.write_text("occupied", encoding="utf-8")
    if case in {"fail_gate", "wrong_run", "wrong_package"}:
        gate_data["self_sha256"] = ""
        gate = Phase7GateResult(**gate_data).with_computed_hash()
        write_phase7_gate_report(gate_path, gate)

    request = PromotionRequest(
        run_id=candidate.run_id,
        approver="reliability-lead",
        expected_source_git_sha=expected_git,
        output=receipt_path,
        champion_package=package,
        phase7_gate=gate_path,
    )
    with pytest.raises((ValueError, FileExistsError), match=error):
        promote_candidate(request, mlflow_client=client)
    assert client.model_versions == {}
    assert client.aliases == {}
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase7_gate.py tests/test_ml_lifecycle.py -v
~~~

Expected: FAIL because promotion does not consume a gate and mutates too early.

- [ ] **Step 3: Make Phase 7 pre-promotion**

Remove `receipt` from `evaluate_phase7_gate`. Compare candidate/reproduction dataset, contract, feature schema, package, source Git, and alert-policy hashes. Add `package_manifest_sha256`, `alert_policy_sha256`, and `self_sha256` to `Phase7GateResult`. `run_phase7_gate` no longer reads `promotion-receipt.json`.

~~~python
def compute_hash(self) -> str:
    data = asdict(self)
    data.pop("self_sha256", None)
    return canonical_sha256(data)


def with_computed_hash(self) -> Phase7GateResult:
    return replace(self, self_sha256=self.compute_hash())
~~~

~~~python
def load_phase7_attestation(path: Path) -> Phase7GateResult:
    result = Phase7GateResult(**json.loads(path.read_text(encoding="utf-8")))
    expected = result.compute_hash()
    if result.self_sha256 != expected:
        raise ValueError(
            f"Phase 7 gate self-hash mismatch: expected {expected}, got {result.self_sha256}"
        )
    return result
~~~

- [ ] **Step 4: Validate before mutation**

~~~python
gate = load_phase7_attestation(request.phase7_gate)
manifest_path = request.champion_package / "manifest.json"
manifest = ChampionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
manifest_sha = sha256_file(manifest_path)

if gate.verdict != "PASS":
    raise ValueError("Phase 7 gate must PASS before promotion")
if gate.candidate_run_id != request.run_id:
    raise ValueError("Phase 7 candidate run does not match promotion run")
if gate.package_manifest_sha256 != manifest_sha:
    raise ValueError("Phase 7 package SHA does not match promotion package")
if source_git_sha != request.expected_source_git_sha or gate.source_git_sha != source_git_sha:
    raise ValueError("Source Git SHA mismatch")
if manifest.package_role != "CHAMPION":
    raise ValueError("package_role must be CHAMPION")
if manifest.evaluation_verdict != "FEASIBLE":
    raise ValueError("evaluation_verdict must be FEASIBLE")
if manifest.operational_status != "PRODUCTION_CANDIDATE":
    raise ValueError("operational_status must be PRODUCTION_CANDIDATE")
if request.output.exists():
    raise FileExistsError(f"Refusing to overwrite promotion receipt: {request.output}")
~~~

Use `datetime.now(UTC).isoformat()`. After all validation and model-version creation, publish the receipt and alias in this order:

~~~python
receipt = PromotionReceiptV1(
    schema_version="mlflow-promotion-receipt-v1",
    mlflow_run_id=request.run_id,
    registered_model_name=REGISTERED_MODEL_NAME,
    registered_model_version=reg_version,
    alias="champion",
    model_version=manifest.model_version,
    dataset_sha256=manifest.source_dataset_sha256,
    contract_sha256=manifest.contract_sha256,
    champion_package_sha256=manifest_sha,
    source_git_sha=source_git_sha,
    approver=request.approver.strip(),
    promoted_at=datetime.now(UTC).isoformat(),
    receipt_sha256="",
).with_computed_hash()
temporary = request.output.with_suffix(request.output.suffix + ".tmp")
write_promotion_receipt(temporary, receipt)
try:
    client.set_registered_model_alias(REGISTERED_MODEL_NAME, "champion", reg_version)
    temporary.replace(request.output)
except Exception:
    temporary.unlink(missing_ok=True)
    raise
~~~

A validation failure occurs before `create_model_version` and creates no model version, alias, or receipt. An alias failure may leave an unaliased model version, which is recoverable registry state and has no success receipt.

- [ ] **Step 5: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase7_gate.py tests/test_ml_lifecycle.py tests/integration/test_mlflow_promotion.py -v
~~~

Expected: PASS; invalid preconditions leave registry collections empty.

- [ ] **Step 6: Commit**

~~~powershell
git add src/industrial_reliability/phase7_gate.py src/industrial_reliability/ml_lifecycle.py src/industrial_reliability/ml_provenance.py tests/test_phase7_gate.py tests/test_ml_lifecycle.py tests/integration/test_mlflow_promotion.py
git commit -m "fix: gate mlflow promotion before mutation"
~~~

### Task 8: Make evidence levels non-user-controlled

**Files:**
- Modify: `src/industrial_reliability/phase8_live_gate.py:111-160`
- Modify: `src/industrial_reliability/phase9_live_gate.py:52-179`
- Modify: `src/industrial_reliability/rca_gate_checks.py:41-53`
- Modify: `src/industrial_reliability/release_certification.py:154-185`
- Test: `tests/test_phase8_live_gate.py`, `tests/test_phase9_live_gate.py`, `tests/test_release_certification.py`

**Interfaces:**
- Produces: Phase 8 in-process reports always use `evidence_level="IN_PROCESS"`.
- Produces: `check_live_openai_generation(api_key: str, model: str) -> ProviderCallReceipt` after an actual provider response.
- Release certification requires dependency receipts and no simulated components for `INTEGRATION`/`LIVE`.

- [ ] **Step 1: Add relabeling regressions**

~~~python
def test_phase8_in_process_gate_cannot_claim_integration(tmp_path: Path) -> None:
    report = run_phase8_live_gate(output_dir=tmp_path, git_sha="a" * 40)
    assert report.evidence_level == "IN_PROCESS"


def test_dummy_key_does_not_create_live_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "industrial_reliability.phase9_live_gate.check_live_openai_generation",
        Mock(side_effect=RuntimeError("provider not contacted")),
    )
    report = run_phase9_live_gate(
        output_dir=tmp_path,
        git_sha="a" * 40,
        api_key="dummy",
        model="test-model",
    )
    assert report["evidence_level"] == "IN_PROCESS"
    assert report["provider_mode"] == "FALLBACK_ONLY"
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase8_live_gate.py tests/test_phase9_live_gate.py tests/test_release_certification.py -v
~~~

Expected: FAIL because callers can supply `INTEGRATION` and key presence becomes `LIVE_OPENAI`.

- [ ] **Step 3: Hardcode Phase 8 in-process evidence**

Remove `evidence_level` from the function and CLI:

~~~python
return publish_live_drill_report(
    drills,
    json_path=json_path,
    md_path=md_path,
    git_sha=sha,
    evidence_level="IN_PROCESS",
)
~~~

- [ ] **Step 4: Require an actual OpenAI response**

~~~python
@dataclass(frozen=True, slots=True)
class ProviderCallReceipt:
    dependency: Literal["openai"]
    model: str
    report_id: str
    evidence_bundle_sha256: str


def check_live_openai_generation(api_key: str, model: str) -> ProviderCallReceipt:
    _alert_id, bundle = gather_synthetic_alert_evidence()
    client = OpenAI(api_key=api_key, timeout=20.0, max_retries=0)
    report = OpenAiRcaGenerator(client=client, model=model, timeout_seconds=20.0).generate(bundle)
    if report.status != "COMPLETE" or report.provider_model != model:
        raise RuntimeError("provider did not return a complete grounded report")
    return ProviderCallReceipt(
        dependency="openai",
        model=model,
        report_id=report.report_id,
        evidence_bundle_sha256=report.evidence_bundle_sha256,
    )
~~~

Only after this succeeds may Phase 9 set `provider_mode="LIVE_OPENAI"` and `evidence_level="LIVE"`.

Use the receipt, not key presence, in `run_phase9_live_gate`:

~~~python
receipt: ProviderCallReceipt | None = None
if api_key and model:
    try:
        receipt = check_live_openai_generation(api_key, model)
    except Exception:
        logger.exception("Live OpenAI verification failed; retaining IN_PROCESS evidence")
provider_mode = "LIVE_OPENAI" if receipt is not None else "FALLBACK_ONLY"
derived_evidence_level = "LIVE" if receipt is not None else "IN_PROCESS"
report = gate.generate_report(
    git_sha=sha,
    evidence_level=derived_evidence_level,
)
report["provider_mode"] = provider_mode
report["dependency_receipts"] = [asdict(receipt)] if receipt is not None else []
~~~

Keep `simulated_components` truthful. A real provider receipt does not erase an in-process/mock evidence-store dependency.

- [ ] **Step 5: Require receipts in release certification**

~~~python
required = {
    "phase8-live-fault-drills-v1": {"kafka", "postgres", "scoring_api"},
    "phase-9-rca-openai-v1": {"openai"},
}[expected_schema]
receipts = {item["dependency"] for item in data.get("dependency_receipts", [])}
if data.get("simulated_components") or not required <= receipts:
    return False
~~~

- [ ] **Step 6: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase8_live_gate.py tests/test_phase9_live_gate.py tests/test_release_certification.py -v
~~~

Expected: PASS; CLI strings and dummy credentials cannot upgrade evidence.

- [ ] **Step 7: Commit**

~~~powershell
git add src/industrial_reliability/phase8_live_gate.py src/industrial_reliability/phase9_live_gate.py src/industrial_reliability/rca_gate_checks.py src/industrial_reliability/release_certification.py tests/test_phase8_live_gate.py tests/test_phase9_live_gate.py tests/test_release_certification.py
git commit -m "fix: derive certification evidence levels"
~~~

---

## Gate C — Durable Failure Evidence and Integration Proof

### Task 9: Quarantine malformed scores before offset commit

**Files:**
- Modify: `src/industrial_reliability/alert_consumer.py:93-100`
- Modify: `src/industrial_reliability/alert_service.py:155-176`
- Test: `tests/test_alert_consumer.py:114-130`, `tests/test_alert_service.py`

**Interfaces:**
- Produces: `AlertConsumer._publish_quarantine(record, raw_bytes, error) -> Awaitable[None]`.
- Guarantees: `QUARANTINED` is returned only after `irp.quarantine.v1` accepts metadata evidence.

- [ ] **Step 1: Write publish-before-outcome test**

~~~python
@pytest.mark.asyncio
async def test_invalid_score_is_durably_quarantined_before_commit() -> None:
    producer = AsyncMock()
    consumer = AlertConsumer(
        store=MagicMock(spec=RuntimeStore),
        policy=_make_policy(),
        producer=producer,
    )
    record = MockKafkaRecord(b"not-json", offset=42)
    record.partition = 3
    outcome = await consumer.process(record)
    assert outcome == ProcessOutcome.QUARANTINED
    assert producer.send_and_wait.call_args.args[0] == QUARANTINE_TOPIC
    payload = decode_message(
        producer.send_and_wait.call_args.kwargs["value"],
        QuarantineRecordV1,
    )
    assert payload.partition == 3
    assert payload.offset == 42
    assert payload.payload_sha256 == hashlib.sha256(b"not-json").hexdigest()
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_alert_consumer.py::test_invalid_score_is_durably_quarantined_before_commit -v
~~~

Expected: FAIL because no quarantine record is published.

- [ ] **Step 3: Publish the existing quarantine schema**

~~~python
async def _publish_quarantine(
    self,
    record: object,
    raw_bytes: bytes,
    error: Exception,
) -> None:
    if self.producer is None:
        raise RuntimeError("Kafka producer is required to quarantine invalid scores")
    payload_hash = hashlib.sha256(raw_bytes).hexdigest()
    quarantine = QuarantineRecordV1(
        message_id=uuid4(),
        replay_session_id=None,
        source_dataset_sha256="0" * 64,
        contract_sha256="0" * 64,
        source_timestamp=datetime(2020, 1, 1),
        emitted_at=datetime.now(UTC),
        original_topic=str(getattr(record, "topic", SCORES_TOPIC)),
        partition=int(getattr(record, "partition", 0)),
        offset=int(getattr(record, "offset", 0)),
        payload_sha256=payload_hash,
        error_code="INVALID_SCORE_PAYLOAD",
        error_detail=str(error)[:1000],
    )
    await self.producer.send_and_wait(
        QUARANTINE_TOPIC,
        value=encode_message(quarantine),
        key=payload_hash.encode("ascii"),
    )
~~~

Change the decode branch:

~~~python
try:
    decision = decode_message(raw_bytes, ScoreDecisionV1)
except Exception as error:
    logger.exception("Failed to decode score decision")
    await self._publish_quarantine(record, raw_bytes, error)
    return ProcessOutcome.QUARANTINED
~~~

If publish raises, propagate it so `alert_service` leaves the score offset uncommitted.

- [ ] **Step 4: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_alert_consumer.py tests/test_alert_service.py -v
~~~

Expected: PASS; quarantine publish failure prevents commit.

- [ ] **Step 5: Commit**

~~~powershell
git add src/industrial_reliability/alert_consumer.py src/industrial_reliability/alert_service.py tests/test_alert_consumer.py tests/test_alert_service.py
git commit -m "fix: persist invalid score quarantine"
~~~

### Task 10: Add one dependency-backed critical-path test

**Files:**
- Create: `tests/integration/test_data_path.py`
- Modify: `tests/integration/test_console_stream_persistence.py:16-44`
- Modify: `.github/workflows/ci.yml:45-91`

**Interfaces:**
- Consumes: real PostgreSQL and Kafka; scoring uses a live local Uvicorn port and a synthetic verified package.
- Produces: one test proving verified telemetry → Kafka → HTTP scoring → two-decision alert/outbox → PostgreSQL.

- [ ] **Step 1: Correct integration collection**

Add `@pytest.mark.integration` to the real PostgreSQL console-persistence test.

Run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest --collect-only -q -m integration
~~~

Expected: at least 8 integration tests, including console persistence.

- [ ] **Step 2: Write the full-path test**

Create the test module with these imports and server helper:

~~~python
import asyncio
import contextlib
import hashlib
import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import psycopg
import uvicorn
from aiokafka import AIOKafkaProducer
import pandas as pd

from industrial_reliability.alert_policy import compute_policy_sha256
from industrial_reliability.alert_service import AlertService, AlertServiceSettings
from industrial_reliability.api import create_app
from industrial_reliability.champion import load_champion
from industrial_reliability.kafka_io import KafkaSettings, encode_message
from industrial_reliability.persistence import RuntimeStore
from industrial_reliability.replay import ReplaySource
from industrial_reliability.replay_service import ReplayService
from industrial_reliability.runtime_messages import REPLAY_COMMANDS_TOPIC
from industrial_reliability.worker import StreamingWorker, WorkerSettings
from tests.helpers_champion import build_research_candidate_from_mock_run
from tests.helpers_replay import make_sample_replay_command


@asynccontextmanager
async def running_scoring_api(scorer: object) -> AsyncIterator[str]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(scorer),  # type: ignore[arg-type]
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        if not server.started:
            raise TimeoutError("scoring API did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)


def write_prepared_manifest(
    parquet: Path,
    source_dataset_sha256: str,
    contract_sha256: str,
) -> None:
    content = parquet.read_bytes()
    manifest = {
        "archive_sha256": source_dataset_sha256,
        "contract_sha256": contract_sha256,
        "output_sha256": hashlib.sha256(content).hexdigest(),
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    parquet.with_name("manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def write_prepared_parquet(path: Path, rows: int = 400) -> Path:
    path.mkdir(parents=True)
    start = datetime(2020, 3, 1)
    frame = pd.DataFrame(
        {
            "timestamp": [start + timedelta(seconds=10 * index) for index in range(rows)],
            "tp2": [10.0] * rows,
            "tp3": [9.0] * rows,
            "h1": [9.0] * rows,
            "dv_pressure": [9.0] * rows,
            "reservoirs": [8.0] * rows,
            "oil_temperature": [80.0] * rows,
            "motor_current": [9.0] * rows,
            "comp": [index % 2 for index in range(rows)],
            "dv_electric": [0] * rows,
            "towers": [1] * rows,
            "mpg": [0] * rows,
            "lps": [0] * rows,
            "pressure_switch": [0] * rows,
            "oil_level": [0] * rows,
            "caudal_impulses": [0] * rows,
        }
    )
    target = path / "telemetry.parquet"
    frame.to_parquet(target, index=False)
    return target


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verified_telemetry_reaches_one_durable_alert(
    tmp_path: Path,
) -> None:
    database_url = "postgresql://irp:irp_password@localhost:5432/irp"
    bootstrap = "localhost:29092"
    mock = build_research_candidate_from_mock_run(tmp_path)
    scorer = load_champion(
        mock.package_dir,
        mock.manifest_sha256,
        allow_research_candidate=True,
    )

    policy_path = mock.package_dir / "alert-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["persistence_decisions"] = 2
    policy["policy_sha256"] = compute_policy_sha256(policy)
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")

    parquet = write_prepared_parquet(tmp_path / "prepared")
    write_prepared_manifest(
        parquet,
        scorer.source_dataset_sha256,
        scorer.contract_sha256,
    )
    kafka = KafkaSettings(bootstrap_servers=bootstrap, client_id=f"data-path-{uuid4()}")
    store = RuntimeStore(database_url)
    for migration in sorted(Path("db/migrations").glob("*.sql")):
        store.execute_script(migration.read_text(encoding="utf-8"))

    async with running_scoring_api(scorer) as scoring_url:
        replay = ReplayService(
            kafka,
            ReplaySource(parquet, expected_contract_sha256=scorer.contract_sha256),
            enable_pacing=False,
        )
        worker = StreamingWorker(
            WorkerSettings(
                bootstrap_servers=bootstrap,
                scoring_api_url=scoring_url,
                model_version=scorer.model_version,
                source_dataset_sha256=scorer.source_dataset_sha256,
                contract_sha256=scorer.contract_sha256,
                feature_names=tuple(scorer.feature_names),
                client_id=f"worker-{uuid4()}",
                group_id=f"worker-{uuid4()}",
            )
        )
        alerts = AlertService(
            AlertServiceSettings(
                kafka=KafkaSettings(bootstrap, f"alerts-{uuid4()}"),
                database_url=database_url,
                policy_path=policy_path,
            )
        )
        replay_task = asyncio.create_task(replay.run())
        worker_task = asyncio.create_task(worker.run())
        await alerts.start()
        try:
            await asyncio.sleep(1)
            session_id = uuid4()
            command = make_sample_replay_command(
                action="START",
                session_id=session_id,
                speed=1000,
                range_start=datetime(2020, 3, 1),
                range_end=datetime(2020, 3, 1) + timedelta(hours=1),
                source_dataset_sha256=scorer.source_dataset_sha256,
                contract_sha256=scorer.contract_sha256,
            )
            producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
            await producer.start()
            try:
                await producer.send_and_wait(
                    REPLAY_COMMANDS_TOPIC,
                    value=encode_message(command),
                    key=str(session_id).encode(),
                )
            finally:
                await producer.stop()

            for _ in range(300):
                if store.count("alerts", "replay_session_id", str(session_id)) == 1:
                    break
                await asyncio.sleep(0.2)
            else:
                raise TimeoutError("durable alert was not created")
        finally:
            await alerts.stop()
            await replay.stop()
            await worker.stop()
            for task in (replay_task, worker_task):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    assert store.count("score_decisions", "replay_session_id", str(session_id)) >= 2
    assert store.count("alerts", "replay_session_id", str(session_id)) == 1
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM alert_outbox AS outbox
            JOIN alert_events AS event ON event.message_id = outbox.message_id
            JOIN alerts AS alert ON alert.alert_id = event.alert_id
            WHERE alert.replay_session_id = %s
            """,
            (str(session_id),),
        )
        assert cursor.fetchone()[0] >= 1
~~~

Do not mock Kafka, PostgreSQL, HTTP, or persistence.

- [ ] **Step 3: Run RED with services**

~~~powershell
docker compose up -d postgres kafka
$env:DATABASE_URL='postgresql://irp:irp_password@localhost:5432/irp'
$env:KAFKA_BOOTSTRAP_SERVERS='localhost:29092'
$env:REQUIRE_INTEGRATION_SERVICES='true'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_data_path.py -v
~~~

Expected: FAIL until Tasks 1, 4, 5, and 9 are integrated.

- [ ] **Step 4: Make CI fail closed**

Use:

~~~yaml
- name: Run integration tests
  env:
    DATABASE_URL: postgresql://irp:irp_password@localhost:5432/irp
    KAFKA_BOOTSTRAP_SERVERS: localhost:29092
    REQUIRE_INTEGRATION_SERVICES: "true"
  run: pytest -m "integration"
~~~

Set `timeout-minutes: 10`. Required-service tests must not skip.

- [ ] **Step 5: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest -m integration -v
~~~

Expected: PASS with zero required-service skips.

- [ ] **Step 6: Commit**

~~~powershell
git add tests/integration/test_data_path.py tests/integration/test_console_stream_persistence.py .github/workflows/ci.yml
git commit -m "test: prove dependency-backed data path"
~~~

---

## Gate D — Database, Monitoring, and Data Contract Operations

### Task 11: Add repeatable migrations and a recovery drill

**Files:**
- Create: `src/industrial_reliability/migrations.py`
- Create: `tests/test_migrations.py`
- Create: `scripts/test_postgres_restore.ps1`
- Create: `docs/DATA_RETENTION.md`
- Modify: `compose.yaml:1-18`
- Modify: `docs/RUNBOOK.md:17-36`

**Interfaces:**
- Produces: `discover_migrations(path: Path) -> tuple[Migration, ...]`.
- Produces: `apply_migrations(db_url: str, path: Path) -> tuple[str, ...]`.
- Guarantees: existing volumes apply each immutable migration once; changed checksums fail closed.

- [ ] **Step 1: Write migration tests**

~~~python
def test_discover_migrations_is_ordered_and_hashed() -> None:
    migrations = discover_migrations(Path("db/migrations"))
    assert [item.name for item in migrations] == sorted(item.name for item in migrations)
    assert migrations[-1].name == "004_alert_runtime_state.sql"
    assert all(len(item.sha256) == 64 for item in migrations)


def test_changed_applied_migration_fails(migrated_database: str, tmp_path: Path) -> None:
    copy_migrations(Path("db/migrations"), tmp_path)
    apply_migrations(migrated_database, tmp_path)
    changed = tmp_path / "001_alert_lifecycle.sql"
    changed.write_text(changed.read_text(encoding="utf-8") + "\nSELECT 1;\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="checksum changed"):
        apply_migrations(migrated_database, tmp_path)
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_migrations.py -v
~~~

Expected: collection FAIL because `industrial_reliability.migrations` is absent.

- [ ] **Step 3: Implement the ordered runner**

~~~python
@dataclass(frozen=True, slots=True)
class Migration:
    name: str
    path: Path
    sha256: str


def discover_migrations(path: Path) -> tuple[Migration, ...]:
    return tuple(
        Migration(file.name, file, sha256_file(file))
        for file in sorted(path.glob("[0-9][0-9][0-9]_*.sql"))
    )


def apply_migrations(db_url: str, path: Path) -> tuple[str, ...]:
    applied: list[str] = []
    with psycopg.connect(db_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              name text PRIMARY KEY,
              sha256 char(64) NOT NULL,
              applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        for migration in discover_migrations(path):
            cursor.execute(
                "SELECT sha256 FROM schema_migrations WHERE name = %s",
                (migration.name,),
            )
            row = cursor.fetchone()
            if row and row[0] != migration.sha256:
                raise MigrationError(f"migration checksum changed: {migration.name}")
            if row:
                continue
            cursor.execute(migration.path.read_text(encoding="utf-8"))
            cursor.execute(
                "INSERT INTO schema_migrations (name, sha256) VALUES (%s, %s)",
                (migration.name, migration.sha256),
            )
            applied.append(migration.name)
        connection.commit()
    return tuple(applied)
~~~

Add the CLI:

~~~python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply ordered IRP database migrations")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--path", type=Path, required=True)
    args = parser.parse_args(argv)
    for name in apply_migrations(args.database_url, args.path):
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
~~~

- [ ] **Step 4: Add a one-shot Compose migrator**

Remove the `docker-entrypoint-initdb.d` mount. Add:

~~~yaml
db-migrate:
  build: .
  command:
    - python
    - -m
    - industrial_reliability.migrations
    - --database-url
    - postgresql://irp:irp_password@postgres:5432/irp
    - --path
    - /app/db/migrations
  volumes:
    - ./db/migrations:/app/db/migrations:ro
  depends_on:
    postgres:
      condition: service_healthy
~~~

Make database-using services depend on `db-migrate: condition: service_completed_successfully`.

- [ ] **Step 5: Add the restore drill**

Create `scripts/test_postgres_restore.ps1`:

~~~powershell
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$outputDir = Join-Path 'artifacts/backups' $stamp
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$dump = Join-Path $outputDir 'irp.dump'
$restoreDb = "irp_restore_$($stamp.Replace('T','_').Replace('Z',''))"
$containerDump = "/tmp/irp-$stamp.dump"
try {
    docker compose exec -T postgres sh -c "pg_dump -U irp -d irp -Fc -f '$containerDump'"
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
    docker compose cp "postgres:$containerDump" $dump
    if ($LASTEXITCODE -ne 0) { throw 'docker compose cp failed' }
    docker compose exec -T postgres createdb -U irp $restoreDb
    docker compose exec -T postgres pg_restore -U irp -d $restoreDb --exit-on-error $containerDump
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed' }
    $tables = 'replay_sessions','score_decisions','alerts','rca_reports'
    $counts = @{}
    foreach ($table in $tables) {
        $source = docker compose exec -T postgres psql -U irp -d irp -Atc "SELECT count(*) FROM $table"
        $restored = docker compose exec -T postgres psql -U irp -d $restoreDb -Atc "SELECT count(*) FROM $table"
        if ($source.Trim() -ne $restored.Trim()) { throw "row count mismatch: $table" }
        $counts[$table] = [int64]$source.Trim()
    }
    @{ verdict='PASS'; counts=$counts; dump_sha256=(Get-FileHash $dump -Algorithm SHA256).Hash.ToLower() } |
        ConvertTo-Json -Depth 4 | Set-Content (Join-Path $outputDir 'restore-report.json')
}
finally {
    docker compose exec -T postgres dropdb -U irp --if-exists $restoreDb
    docker compose exec -T postgres rm -f $containerDump
}
~~~

- [ ] **Step 6: Document safe retention and corrected migration commands**

Create `docs/DATA_RETENTION.md`:

~~~markdown
# Data Retention

- Policy state: `RETAIN_UNTIL_MANUAL_APPROVAL`.
- Raw UCI archives and prepared/model artifacts are immutable and never deleted automatically.
- Kafka and PostgreSQL records remain on persistent volumes until an owner approves archival.
- A future deletion path must support dry-run, explicit date bounds, backup confirmation,
  and a durable audit receipt.
~~~

Replace the two nonexistent runbook migration filenames with the migration CLI and restore script commands.

- [ ] **Step 7: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_migrations.py -v
docker compose config --quiet
~~~

Expected: PASS; second migration run applies zero files and changed SQL fails.

- [ ] **Step 8: Commit**

~~~powershell
git add src/industrial_reliability/migrations.py tests/test_migrations.py scripts/test_postgres_restore.ps1 docs/DATA_RETENTION.md compose.yaml docs/RUNBOOK.md
git commit -m "feat: add database migration and recovery path"
~~~

### Task 12: Wire lag, drift identity, and Prometheus alerts

**Files:**
- Modify: `src/industrial_reliability/worker.py:238-242,440-477`
- Modify: `src/industrial_reliability/drift.py:85-97,168-219`
- Modify: `src/industrial_reliability/package_research_candidate.py`
- Modify: `src/industrial_reliability/package_champion.py`
- Modify: `compose.yaml:85-104,146-160`
- Create: `ops/prometheus/alerts.yml`
- Modify: `ops/prometheus/prometheus.yml`
- Test: `tests/test_worker.py`, `tests/test_drift.py`, `tests/test_package.py`, `tests/test_package_champion.py`

**Interfaces:**
- Produces: packaged `drift-reference.json` bound to model, dataset, contract, and feature names.
- Guarantees: zero feature overlap raises and the worker updates Kafka lag after records.

- [ ] **Step 1: Write lag and drift tests**

~~~python
@pytest.mark.asyncio
async def test_worker_updates_consumer_lag(worker: StreamingWorker) -> None:
    tp = TopicPartition(TELEMETRY_TOPIC, 0)
    worker.consumer.highwater.return_value = 20
    worker.consumer.position = AsyncMock(return_value=15)
    await worker._update_consumer_lag(tp)
    assert worker.metrics.kafka_consumer_lag._value.get() == 5


def test_drift_requires_feature_overlap(reference: DriftReferenceV1) -> None:
    with pytest.raises(ValueError, match="no feature overlap"):
        max_population_stability_index({"unknown": [1.0]}, reference)
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_worker.py tests/test_drift.py -v
~~~

Expected: FAIL because lag is never read and no-overlap returns zero.

- [ ] **Step 3: Update lag and fail closed on drift mismatch**

~~~python
async def _update_consumer_lag(self, partition: TopicPartition) -> None:
    if self.consumer is None or self.metrics is None:
        return
    highwater = self.consumer.highwater(partition)
    position = await self.consumer.position(partition)
    if highwater is not None:
        self.metrics.set_consumer_lag(highwater - position)
~~~

Call it from `handle_record` after the topic-specific handler completes:

~~~python
async def handle_record(self, record: object) -> None:
    topic = getattr(record, "topic", "")
    partition = int(getattr(record, "partition", 0))
    if topic == TELEMETRY_TOPIC:
        await self._handle_telemetry_record(record)
    elif topic == REPLAY_STATUS_TOPIC:
        await self._handle_status_record(record)
    else:
        return
    await self._update_consumer_lag(TopicPartition(topic, partition))
~~~

Replace the no-overlap return:

~~~python
if not psi_list:
    raise ValueError("drift reference and current features have no feature overlap")
~~~

Load the reference with the active package manifest, not `expected_manifest=None`.

- [ ] **Step 4: Package and mount the drift reference**

Add `DRIFT_REFERENCE_FILENAME = "drift-reference.json"` to package artifacts. Build it from train-only features, include its hash in `artifact_sha256`, and verify it in `load_champion`. The existing package volume supplies:

~~~yaml
DRIFT_REFERENCE_PATH: /runtime/scoring-package/drift-reference.json
~~~

- [ ] **Step 5: Add four Prometheus rules**

~~~yaml
groups:
  - name: industrial-reliability-data
    rules:
      - alert: IRPQuarantineDetected
        expr: increase(irp_telemetry_events_total{outcome="quarantined"}[5m]) > 0
        for: 1m
      - alert: IRPKafkaConsumerLag
        expr: irp_kafka_consumer_lag > 1000
        for: 5m
      - alert: IRPWindowCoverageLow
        expr: irp_window_coverage_ratio < 0.8
        for: 10m
      - alert: IRPFeatureDriftHigh
        expr: irp_feature_psi_max >= 0.2
        for: 15m
~~~

Add `rule_files: ["/etc/prometheus/alerts.yml"]` and mount it read-only.

- [ ] **Step 6: Run GREEN**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_worker.py tests/test_drift.py tests/test_package.py tests/test_package_champion.py -v
docker compose config --quiet
~~~

Expected: PASS; wrong drift identity fails, lag becomes 5, and Compose renders.

- [ ] **Step 7: Commit**

~~~powershell
git add src/industrial_reliability/worker.py src/industrial_reliability/drift.py src/industrial_reliability/package_research_candidate.py src/industrial_reliability/package_champion.py compose.yaml ops/prometheus/prometheus.yml ops/prometheus/alerts.yml tests/test_worker.py tests/test_drift.py tests/test_package.py tests/test_package_champion.py
git commit -m "feat: wire data quality monitoring"
~~~

### Task 13: Version units, plausibility envelopes, and time semantics

**Files:**
- Modify: `src/industrial_reliability/phase1b_contracts.py:26-65`
- Modify: `src/industrial_reliability/phase1b_data.py:106-118`
- Modify: `src/industrial_reliability/runtime_messages.py:241-287`
- Test: `tests/test_phase1b_contracts.py`, `tests/test_phase1b_data.py`, `tests/test_runtime_messages.py`
- Modify: `docs/DATA_CARD.md`

**Interfaces:**
- Produces: `AnalogSignalContract(name, unit, hard_min, hard_max)`.
- Contract becomes `phase1b-contract-v2`; full-data output uses `phase1c`.

- [ ] **Step 1: Write hard-envelope tests**

~~~python
@pytest.mark.parametrize(
    "field,value",
    [
        ("tp2", 21.0),
        ("tp3", -2.0),
        ("oil_temperature", 151.0),
        ("motor_current", 51.0),
    ],
)
def test_runtime_rejects_hard_physical_envelope(field: str, value: float) -> None:
    payload = valid_telemetry_payload()
    payload[field] = value
    with pytest.raises(ValidationError, match=field):
        TelemetryEventV1.model_validate(payload)
~~~

Add offline preparation coverage:

~~~python
@pytest.mark.parametrize(
    "source_column,value",
    [
        ("TP2", 21.0),
        ("TP3", -2.0),
        ("Oil_temperature", 151.0),
        ("Motor_current", 51.0),
    ],
)
def test_preparation_rejects_hard_physical_envelope(
    tmp_path: Path,
    source_column: str,
    value: float,
) -> None:
    frame = pd.read_csv(io.BytesIO(_create_synthetic_csv()))
    frame.loc[0, source_column] = value
    archive = tmp_path / "invalid.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("MetroPT3(AirCompressor).csv", frame.to_csv(index=False))
    contract = replace(PHASE1B, archive_sha256=sha256_file(archive), expected_rows=10)
    with pytest.raises(MetroPT3ContractError, match=source_column.lower().split("_")[0]):
        prepare_metropt3(archive, tmp_path / "out", contract)


def test_official_observed_extrema_are_inside_hard_envelopes() -> None:
    observed = {
        "tp2": (-0.032, 10.676),
        "tp3": (0.7300000000000004, 10.302),
        "h1": (-0.0360000000000013, 10.288),
        "dv_pressure": (-0.032, 9.844),
        "reservoirs": (0.7119999999999997, 10.3),
        "oil_temperature": (15.400000000000006, 89.05000000000001),
        "motor_current": (0.0199999999999995, 9.295),
    }
    for name, (minimum, maximum) in observed.items():
        assert validate_analog_value(name, minimum) == minimum
        assert validate_analog_value(name, maximum) == maximum
~~~

- [ ] **Step 2: Run RED**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase1b_contracts.py tests/test_phase1b_data.py tests/test_runtime_messages.py -v
~~~

Expected: FAIL because finite but impossible magnitudes pass.

- [ ] **Step 3: Add explicit signal contracts**

~~~python
@dataclass(frozen=True, slots=True)
class AnalogSignalContract:
    name: str
    unit: str
    hard_min: float
    hard_max: float


ANALOG_SIGNAL_CONTRACTS = (
    AnalogSignalContract("tp2", "bar", -1.0, 20.0),
    AnalogSignalContract("tp3", "bar", -1.0, 20.0),
    AnalogSignalContract("h1", "bar", -1.0, 20.0),
    AnalogSignalContract("dv_pressure", "bar", -1.0, 20.0),
    AnalogSignalContract("reservoirs", "bar", -1.0, 20.0),
    AnalogSignalContract("oil_temperature", "degC", -40.0, 150.0),
    AnalogSignalContract("motor_current", "A", 0.0, 50.0),
)
~~~

Add `timestamp_semantics="timezone-naive source clock"`, `nominal_cadence_seconds=10`, and bump `contract_version`.

- [ ] **Step 4: Reuse one validator offline and online**

~~~python
def validate_analog_value(name: str, value: float) -> float:
    contract = ANALOG_SIGNAL_BY_NAME[name]
    if not math.isfinite(value) or not contract.hard_min <= value <= contract.hard_max:
        raise ValueError(
            f"{name} outside hard {contract.unit} envelope "
            f"[{contract.hard_min}, {contract.hard_max}]: {value}"
        )
    return value
~~~

Call from preparation and `TelemetryEventV1.validate_telemetry`. Never clip.

- [ ] **Step 5: Run GREEN and document**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase1b_contracts.py tests/test_phase1b_data.py tests/test_runtime_messages.py -v
~~~

Expected: PASS. Add this exact note to `docs/DATA_CARD.md`:

~~~markdown
### Executable physical contract

The executable contract records each analog unit and a conservative hard ingestion
envelope. Values outside the envelope are rejected or quarantined, never clipped.
These bounds detect clear unit/sensor contract violations; they are not anomaly
thresholds. Source timestamps remain timezone-naive because the dataset supplies no
offset. Nominal cadence is 10 seconds. Contract-v2 full-data output is published as
Phase 1C and does not overwrite Phase 1B evidence.
~~~

- [ ] **Step 6: Commit**

~~~powershell
git add src/industrial_reliability/phase1b_contracts.py src/industrial_reliability/phase1b_data.py src/industrial_reliability/runtime_messages.py tests/test_phase1b_contracts.py tests/test_phase1b_data.py tests/test_runtime_messages.py docs/DATA_CARD.md
git commit -m "feat: version sensor data contracts"
~~~

### Task 14: Publish versioned evidence and truthful docs

**Files:**
- Modify: `README.md`
- Modify: `docs/RUNBOOK.md`
- Create: `docs/results/phase-1c-metropt3-validation.md`
- Create: `docs/results/phase-1c-metrics.json`
- Generate: `artifacts/certification/<git-sha>/`

**Interfaces:**
- Consumes: Tasks 1-13.
- Produces: versioned offline evidence and exact-SHA dependency receipts without changing Phase 1B files.

- [ ] **Step 1: Run the complete local quality gate**

~~~powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -m "not slow and not integration" --cov
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
~~~

Expected: every command exits 0 and coverage is at least 80%.

- [ ] **Step 2: Run dependency-backed integration**

~~~powershell
docker compose up -d postgres kafka db-migrate
$env:REQUIRE_INTEGRATION_SERVICES='true'
$env:DATABASE_URL='postgresql://irp:irp_password@localhost:5432/irp'
$env:KAFKA_BOOTSTRAP_SERVERS='localhost:29092'
.\.venv\Scripts\python.exe -m pytest -m integration -v
~~~

Expected: PASS with zero required-service skips.

- [ ] **Step 3: Build new contract/data artifacts**

~~~powershell
.\.venv\Scripts\python.exe -m industrial_reliability.phase1b_data --archive data/raw/metropt3/metropt+3+dataset.zip --output-dir data/processed/phase1c/metropt3
.\.venv\Scripts\python.exe -m industrial_reliability.phase1b_features --prepared-dir data/processed/phase1c/metropt3 --output data/processed/phase1c/features.parquet
.\.venv\Scripts\python.exe -m industrial_reliability.phase1b_benchmark --prepared-dir data/processed/phase1c/metropt3 --features data/processed/phase1c/features.parquet --artifact-dir artifacts/phase1c --publish-dir docs/results/phase1c
Copy-Item -LiteralPath docs/results/phase1c/phase-1b-metrics.json -Destination docs/results/phase-1c-metrics.json
Copy-Item -LiteralPath docs/results/phase1c/phase-1b-metropt3-fresh-validation.md -Destination docs/results/phase-1c-metropt3-validation.md
~~~

Expected: new run ID and hashes in the declared `phase-1c-*` files; `git diff -- docs/results/phase-1b-*` is empty.

- [ ] **Step 4: Run recovery and certification**

~~~powershell
.\scripts\test_postgres_restore.ps1
.\scripts\run_phase8_live_fault_drills.ps1
.\scripts\run_phase9_live_gate.ps1
$sha = git rev-parse HEAD
.\.venv\Scripts\python.exe -m industrial_reliability.release_certification --artifact-dir "artifacts/certification/$sha" --git-sha $sha
~~~

Expected: certification passes only with the receipts required by Task 8. Without a configured provider, Phase 9 remains fallback/in-process and the release states that limitation.

- [ ] **Step 5: Update README and runbook from evidence**

Add this status block to `README.md`, substituting only values read from the generated Phase 1C JSON:

~~~markdown
## Data-pipeline evidence status

- Phase 1B remains immutable historical evidence with verdict `NOT FEASIBLE`.
- Phase 1C is the contract-v2/split-containment rerun. Verdict, run ID, dataset SHA,
  feature SHA, contract SHA, and exact code SHA are recorded in
  `docs/results/phase-1c-metrics.json`.
- `UNIT` proves isolated code behavior; `IN_PROCESS` permits doubles;
  `INTEGRATION` requires Kafka/PostgreSQL/HTTP receipts; `LIVE` requires an actual
  provider/deployment response; `RELEASE` requires passing exact-SHA evidence.
- The project must not claim production readiness while any remediation gate is open.
~~~

Add the exact commands from Tasks 10-14 to `docs/RUNBOOK.md` under Migration, Integration, Backup/Restore, Drift Reference, and Certification headings.

- [ ] **Step 6: Verify report hashes and repository state**

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_report_hashes.py tests/test_release_certification.py tests/test_portfolio_claims.py -v
git diff --check
git status --short
~~~

Expected: tests PASS, diff check exits 0, and status lists only intended remediation/evidence files.

- [ ] **Step 7: Commit**

~~~powershell
git add README.md docs/RUNBOOK.md docs/DATA_CARD.md docs/DATA_RETENTION.md docs/results/phase-1c-metropt3-validation.md docs/results/phase-1c-metrics.json
git commit -m "docs: publish corrected data pipeline evidence"
~~~

---

## Audit Finding Coverage

| Audit finding | Task |
|---|---|
| Pre-alert streak is lost | 1 |
| Runtime lineage can relabel bytes | 2-4 |
| Replay START recovery is not durable | 5 |
| Calibration boundary overlap | 6 |
| Promotion bypasses reproduction/feasibility | 7 |
| Synthetic evidence relabeling | 8 |
| Invalid score lacks durable quarantine | 9 |
| CI lacks a complete data path | 10 |
| Database migration/recovery/retention gaps | 11 |
| Lag/drift/alerts are unwired | 12 |
| Units/ranges/time semantics are absent | 13 |
| Published evidence is stale/overstated | 8, 10, 14 |

## Final Review Gates

- [ ] Request spec-compliance review against every finding in `docs/data-pipeline-audit-2026-08-29.md`.
- [ ] Request code-quality review; block on identity, transaction, promotion, destructive-data, or evidence-level defects.
- [ ] Re-run every Task 14 verification command after review fixes.
- [ ] Confirm each commit is independently recoverable and no historical evidence was overwritten.
- [ ] Use `finishing-a-development-branch` to present merge, PR, or worktree cleanup options.
