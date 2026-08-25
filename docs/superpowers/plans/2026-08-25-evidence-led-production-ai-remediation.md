# Evidence-Led Production AI Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Phase 7-11 branch into an honest, runnable negative-research Production AI case study with a gated research-only scorer, real local fault drills, separately identified live OpenAI evidence, and exact-SHA release artifacts.

**Architecture:** Preserve the permanent Phase 1/1B `NOT FEASIBLE` result and add a separate `RESEARCH_CANDIDATE` scoring-package role that is disabled unless explicitly allowed. Complete the missing local runtime wiring before adding live Phase 8 and Phase 9 gates; keep mock checks as unit/contract evidence and generate live evidence only from real Docker, Kafka, PostgreSQL, HTTP, UI, and provider interactions. Generate certification artifacts under `artifacts/certification/<git-sha>/` so a report can name the already-committed source SHA without creating a self-referential commit.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, aiokafka, PostgreSQL 17, Docker Compose, React/Vite/Playwright, OpenAI Responses structured outputs, pytest, Ruff, Mypy.

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Preserve the Phase 1 and Phase 1B `NOT FEASIBLE` results; never regenerate or tune against either viewed holdout.
- Never call a non-feasible model a champion, production model, or production-ready detector.
- The fixed demo model is `research-candidate-statistical-v1`; do not select another model from holdout results.
- A research candidate is loadable only when `ALLOW_RESEARCH_CANDIDATE=true`; otherwise the API and worker fail closed.
- Keep the existing feasible-champion packaging path hard-gated and backward compatible.
- Evidence levels are exact: `UNIT` uses mocks, `INTEGRATION` uses real local dependencies, and `LIVE` uses the complete real interaction named by the gate.
- A missing Docker engine, dataset, scoring package, database, Kafka broker, or provider credential fails or blocks its live gate; it never downgrades to a pass.
- Read OpenAI credentials only from `RCA_OPENAI_API_KEY`; never print, persist, attach, or include the key in a command line.
- Revoke the key disclosed in chat and use a newly created key before any live-provider execution.
- Keep all services bound to `127.0.0.1`; public deployment, authentication, TLS, multi-tenancy, and cloud hosting remain out of scope.
- Do not add dependencies; use installed Python packages and the standard library.
- Keep raw data, model binaries, generated scoring packages, and live certification reports under git-ignored `data/` and `artifacts/`.
- Preserve existing user changes and the empty root `AGENTS.md`; do not reset, stash, overwrite, or rewrite the public branch.
- Execute in an isolated worktree created with `superpowers:using-git-worktrees` from `origin/feat/phase-9-grounded-rca` at `45b636cecc31be37273ce7a33ccdf687b0694978` or its reviewed descendant.
- Use one reviewable commit per task. If GitHub execution is authorized later, open child PRs against `feat/phase-9-grounded-rca`; do not merge PR #15 to `main` until its CI and the required local evidence gates pass.
- Backend branch coverage remains at least 80%; frontend branch coverage remains at least 80%.

## File Responsibility Map

### Existing files to modify

- `src/industrial_reliability/ml_lifecycle.py` — restore version-independent strict Mypy success.
- `src/industrial_reliability/package_champion.py` — retain hard champion packaging and define the shared signed scoring-package manifest.
- `src/industrial_reliability/champion.py` — verify scoring-package role and enforce the research-only runtime switch.
- `src/industrial_reliability/api.py` — publish replay commands through a real Kafka bridge and use package identity instead of zero hashes.
- `src/industrial_reliability/worker.py` — parse the signed manifest and enforce the same research-only switch.
- `src/industrial_reliability/alert_policy.py` — load and verify a persisted alert policy.
- `src/industrial_reliability/fault_report.py` — relabel the current mock exercise as `UNIT`, not live certification.
- `src/industrial_reliability/phase9_gate.py` — relabel mock provider checks as contract evidence.
- `src/industrial_reliability/release_certification.py` — validate exact SHA, artifact schemas, self-hashes, verdicts, and evidence levels.
- `compose.yaml` — mount the research package, pass non-secret provider settings, and run the missing alert service.
- `.env.example` — document empty secret/config inputs and the explicit research-only switch.
- `.github/workflows/ci.yml` — retain deterministic unit/static gates and upload no live or secret-bearing artifacts.
- `README.md`, `docs/RUNBOOK.md`, `docs/ARCHITECTURE_DIAGRAMS.md`, `docs/MODEL_CARD.md`, `task.md` — present the final evidence truthfully.

### New files to create

- `src/industrial_reliability/package_research_candidate.py` — build the fixed statistical research package from the immutable Phase 1B run.
- `src/industrial_reliability/runtime_kafka.py` — own the API process's Kafka command producer and console-feed consumer lifecycle.
- `src/industrial_reliability/alert_service.py` — run the score consumer and transactional outbox dispatcher as a real service.
- `src/industrial_reliability/phase8_live_gate.py` — orchestrate and verify three real local fault drills without deleting volumes.
- `src/industrial_reliability/phase9_live_gate.py` — verify fallback and live-provider RCA separately against a persisted real alert.
- `scripts/build_research_candidate.ps1` — build the local research package and write its manifest hash to the current process output.
- `scripts/run_phase8_live_fault_drills.ps1` — perform Docker/data preflight and invoke the live Phase 8 gate.
- `scripts/run_phase9_live_gate.ps1` — require the rotated environment credential and invoke the live Phase 9 gate.
- `scripts/run_portfolio_demo.ps1` — run the ordered local demo and certification commands without embedding secrets.
- `tests/test_runtime_kafka.py`, `tests/test_alert_service.py`, `tests/test_phase8_live_gate.py`, `tests/test_phase9_live_gate.py` — deterministic unit tests for the new orchestration boundaries.
- `tests/integration/test_phase8_live_stack.py`, `tests/integration/test_phase9_live_provider.py` — explicitly opted-in real-dependency checks.

---

### Task 1: Restore CI and freeze evidence vocabulary

**Files:**
- Modify: `src/industrial_reliability/ml_lifecycle.py:69-78`
- Modify: `src/industrial_reliability/fault_report.py:52-65,206-410`
- Modify: `src/industrial_reliability/phase9_gate.py:48-326`
- Modify: `tests/test_fault_report.py`
- Modify: `tests/test_phase9_gate.py`

**Interfaces:**
- Consumes: existing `FaultReportV1`, `Phase9CertificationGate`, and GitHub CI command `mypy src`.
- Produces: reports whose `evidence_level` is exactly `UNIT` and whose filenames contain `contract` or `unit`, never `live`.

- [ ] **Step 1: Reproduce the strict Mypy failure**

Run:

```powershell
python -m mypy src
```

Expected: FAIL at `ml_lifecycle.py:76-77` with two `unused-ignore` errors under Mypy 1.20.2.

- [ ] **Step 2: Remove only the two obsolete ignore comments**

Use this exact import fallback:

```python
try:
    import mlflow
    import mlflow.pyfunc
    from mlflow import MlflowClient as MlflowClient
except ImportError:
    mlflow = None
    MlflowClient = None
```

- [ ] **Step 3: Write failing evidence-level assertions**

Add these assertions before changing the report schemas:

```python
def test_fault_report_is_unit_evidence(tmp_path: Path) -> None:
    drills = asyncio.run(execute_in_process_drills())
    assert all(result.passed for result in drills)
    published = publish_drill_report(
        drills,
        json_path=tmp_path / "report.json",
        md_path=tmp_path / "report.md",
        git_sha="a" * 40,
    )
    assert published.evidence_level == "UNIT"


def test_phase9_contract_gate_never_claims_live() -> None:
    gate = Phase9CertificationGate()
    assert gate.run_all_checks() is True
    report = gate.generate_report(git_sha="a" * 40)
    assert report["evidence_level"] == "UNIT"
    assert report["provider_mode"] == "MOCKED_CONTRACT"
```

- [ ] **Step 4: Run the focused tests and confirm RED**

Run:

```powershell
python -m pytest tests/test_fault_report.py tests/test_phase9_gate.py -q
```

Expected: FAIL because the current report types do not expose `evidence_level`, `git_sha`, or `provider_mode`.

- [ ] **Step 5: Add exact unit-evidence fields and rename generated files**

Extend `FaultReportV1` with immutable fields and validate the SHA at the `publish_drill_report` boundary:

```python
evidence_level: Literal["UNIT"]
git_sha: str
```

Change the publisher signature to `publish_drill_report(drills: list[DrillResultV1], json_path: Path, md_path: Path, git_sha: str) -> FaultReportV1`; reject any SHA that is not 40 lowercase hexadecimal characters or is all zeros.

Change the Phase 8 in-process CLI defaults to:

```python
Path("artifacts/certification/unit/phase-8-unit-fault-drills.json")
Path("artifacts/certification/unit/phase-8-unit-fault-drills.md")
```

Add to the Phase 9 contract report:

```python
"schema_version": "phase-9-rca-contract-v1",
"evidence_level": "UNIT",
"provider_mode": "MOCKED_CONTRACT",
"git_sha": git_sha,
```

Change `generate_report` to `generate_report(git_sha: str) -> dict[str, Any]` and add required CLI argument `--git-sha`. Write it to `artifacts/certification/unit/phase-9-contract-gate.{json,md}` unless `--output-dir` is supplied. Keep the mock checks; change only what they claim.

- [ ] **Step 6: Run static and focused verification**

Run:

```powershell
python -m mypy src
python -m pytest tests/test_fault_report.py tests/test_phase9_gate.py -q
```

Expected: both commands PASS.

- [ ] **Step 7: Commit the truthful baseline**

```powershell
git add src/industrial_reliability/ml_lifecycle.py src/industrial_reliability/fault_report.py src/industrial_reliability/phase9_gate.py tests/test_fault_report.py tests/test_phase9_gate.py
git commit -m "fix: distinguish unit checks from live certification"
```

### Task 2: Build and gate a research-only scoring package

**Files:**
- Create: `src/industrial_reliability/package_research_candidate.py`
- Create: `scripts/build_research_candidate.ps1`
- Modify: `src/industrial_reliability/package_champion.py:33-69,142-263`
- Modify: `src/industrial_reliability/champion.py:36-147`
- Modify: `src/industrial_reliability/api.py:500-513`
- Modify: `src/industrial_reliability/worker.py:60-108`
- Modify: `.env.example`
- Modify: `compose.yaml`
- Modify: `tests/test_package_champion.py`
- Modify: `tests/test_champion.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_worker.py`

**Interfaces:**
- Consumes: immutable `phase1b-run-v1`, `feature_manifest.json`, `features.parquet`, `scores.parquet`, `evidence-baseline.npz`, and `models/statistical.joblib`.
- Produces: `build_research_candidate_package(run_dir: Path, features_path: Path, feature_manifest_path: Path, output_dir: Path) -> ChampionPackageResult` and a signed `champion-package-v1` manifest with `package_role="RESEARCH_CANDIDATE"`.

- [ ] **Step 1: Write failing manifest-role tests**

Add to `tests/test_package_champion.py`:

```python
def test_research_candidate_is_explicitly_non_feasible(tmp_path: Path) -> None:
    run_dir, features, feature_manifest = _create_mock_infeasible_phase1b_run(tmp_path)
    result = build_research_candidate_package(
        run_dir=run_dir,
        features_path=features,
        feature_manifest_path=feature_manifest,
        output_dir=tmp_path / "research-candidate",
    )
    assert result.manifest.package_role == "RESEARCH_CANDIDATE"
    assert result.manifest.evaluation_verdict == "NOT_FEASIBLE"
    assert result.manifest.operational_status == "RESEARCH_ONLY"
    assert result.manifest.model_version == "research-candidate-statistical-v1"
```

Add to `tests/test_champion.py`:

```python
def test_research_candidate_requires_explicit_runtime_opt_in(tmp_path: Path) -> None:
    pkg_dir, manifest_sha = _build_mock_research_package(tmp_path)
    with pytest.raises(ChampionIntegrityError, match="ALLOW_RESEARCH_CANDIDATE"):
        load_champion(pkg_dir, manifest_sha, allow_research_candidate=False)
    scorer = load_champion(pkg_dir, manifest_sha, allow_research_candidate=True)
    assert scorer.manifest.operational_status == "RESEARCH_ONLY"
```

- [ ] **Step 2: Run the new tests and confirm RED**

```powershell
python -m pytest tests/test_package_champion.py tests/test_champion.py -q
```

Expected: FAIL because the package-role fields, builder, and loader argument do not exist.

- [ ] **Step 3: Extend the existing manifest without weakening champion rules**

In `ChampionManifest`, add:

```python
package_role: Literal["CHAMPION", "RESEARCH_CANDIDATE"] = "CHAMPION"
evaluation_verdict: Literal["FEASIBLE", "NOT_FEASIBLE"] = "FEASIBLE"
operational_status: Literal["PRODUCTION_CANDIDATE", "RESEARCH_ONLY"] = "PRODUCTION_CANDIDATE"
source_champion_schema: Literal["phase1b-champion-v1", "phase1b-run-v1"]
```

Add a `model_validator(mode="after")` enforcing both valid combinations:

```python
@model_validator(mode="after")
def validate_package_role(self) -> ChampionManifest:
    champion = (
        self.package_role == "CHAMPION"
        and self.evaluation_verdict == "FEASIBLE"
        and self.operational_status == "PRODUCTION_CANDIDATE"
        and self.source_champion_schema == "phase1b-champion-v1"
    )
    research = (
        self.package_role == "RESEARCH_CANDIDATE"
        and self.evaluation_verdict == "NOT_FEASIBLE"
        and self.operational_status == "RESEARCH_ONLY"
        and self.source_champion_schema == "phase1b-run-v1"
    )
    if not (champion or research):
        raise ValueError("invalid package role and evaluation verdict combination")
    return self
```

Change artifact validation to require the three existing files and allow `scores.parquet` only as an additional signed artifact:

```python
required = {DETECTOR_FILENAME, BASELINE_FILENAME, GOLDEN_CASES_FILENAME}
allowed = required | {"scores.parquet"}
if not required <= set(v) or not set(v) <= allowed:
    raise ValueError(f"artifact_sha256 must contain {required} and only allow {allowed}")
```

Rename `_select_golden_cases` to `select_golden_cases` and `_serialize_golden_cases` to `serialize_golden_cases`; update the existing champion builder call sites.

- [ ] **Step 4: Add the fixed research-candidate builder**

Create `package_research_candidate.py` with this public boundary and fail-closed checks:

```python
def build_research_candidate_package(
    *,
    run_dir: Path,
    features_path: Path,
    feature_manifest_path: Path,
    output_dir: Path,
) -> ChampionPackageResult:
    run = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    features = json.loads(feature_manifest_path.read_text(encoding="utf-8"))
    if run.get("schema_version") != "phase1b-run-v1":
        raise ChampionPackageError("phase1b-run-v1 manifest required")
    if run.get("verdict") != "NOT FEASIBLE" or run.get("selected_model") is not None:
        raise ChampionPackageError("research package requires the immutable NOT FEASIBLE run")
    if sha256_file(features_path) != run["feature_output_sha256"]:
        raise ChampionPackageError("features.parquet SHA-256 mismatch")
    if features.get("output_sha256") != run["feature_output_sha256"]:
        raise ChampionPackageError("feature manifest does not match the Phase 1B run")

    model_id = "statistical"
    model_path = run_dir / "models" / "statistical.joblib"
    scores_path = run_dir / "scores.parquet"
    baseline_path = run_dir / "evidence-baseline.npz"
    for path in (model_path, scores_path, baseline_path):
        if not path.is_file():
            raise ChampionPackageError(f"required research artifact missing: {path.name}")

    source = {
        "run_id": run["run_id"],
        "model_id": model_id,
        "threshold": run["models"][model_id]["threshold"],
        "active_feature_names": features["active_feature_names"],
    }
    golden = select_golden_cases(scores_path, features_path, source, baseline_path)
    if output_dir.exists():
        raise FileExistsError(f"destination already exists: {output_dir}")
    temp_output = output_dir.parent / f"{output_dir.name}.tmp.{os.getpid()}"
    temp_output.mkdir(parents=True, exist_ok=False)
    try:
        published_model = temp_output / "detector.joblib"
        published_baseline = temp_output / "evidence-baseline.npz"
        published_golden = temp_output / "golden-cases.json"
        published_scores = temp_output / "scores.parquet"
        shutil.copy2(model_path, published_model)
        shutil.copy2(baseline_path, published_baseline)
        shutil.copy2(scores_path, published_scores)
        published_golden.write_text(
            json.dumps(serialize_golden_cases(golden), indent=2),
            encoding="utf-8",
        )
        manifest = ChampionManifest(
            source_champion_schema="phase1b-run-v1",
            source_run_id=run["run_id"],
            package_role="RESEARCH_CANDIDATE",
            evaluation_verdict="NOT_FEASIBLE",
            operational_status="RESEARCH_ONLY",
            model_id="statistical",
            model_version="research-candidate-statistical-v1",
            contract_sha256=run["contract_sha256"],
            source_dataset_sha256=run["source_dataset_sha256"],
            feature_names=tuple(features["active_feature_names"]),
            threshold=float(run["models"]["statistical"]["threshold"]),
            threshold_provenance=ThresholdProvenance(),
            artifact_sha256={
                "detector.joblib": sha256_file(published_model),
                "evidence-baseline.npz": sha256_file(published_baseline),
                "golden-cases.json": sha256_file(published_golden),
                "scores.parquet": sha256_file(published_scores),
            },
        )
        published_manifest = temp_output / "manifest.json"
        published_manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        lock_alert_policy(published_manifest, temp_output / "alert-policy.json")
        manifest_sha256 = sha256_file(published_manifest)
        temp_output.replace(output_dir)
    except Exception:
        shutil.rmtree(temp_output, ignore_errors=True)
        raise
    return ChampionPackageResult(output_dir, manifest, manifest_sha256)
```

The manifest values written by the atomic block must be exactly:

```python
ChampionManifest(
    source_champion_schema="phase1b-run-v1",
    source_run_id=run["run_id"],
    package_role="RESEARCH_CANDIDATE",
    evaluation_verdict="NOT_FEASIBLE",
    operational_status="RESEARCH_ONLY",
    model_id="statistical",
    model_version="research-candidate-statistical-v1",
    contract_sha256=run["contract_sha256"],
    source_dataset_sha256=run["source_dataset_sha256"],
    feature_names=tuple(features["active_feature_names"]),
    threshold=float(run["models"]["statistical"]["threshold"]),
    threshold_provenance=ThresholdProvenance(),
    artifact_sha256={
        "detector.joblib": sha256_file(published_model),
        "evidence-baseline.npz": sha256_file(published_baseline),
        "golden-cases.json": sha256_file(published_golden),
        "scores.parquet": sha256_file(published_scores),
    },
)
```

Add a `main()` parser with required `--run-dir`, `--features`, `--feature-manifest`, and `--output-dir` `Path` arguments; call `build_research_candidate_package` with keyword arguments and print only the output directory and manifest SHA-256.

- [ ] **Step 5: Enforce runtime opt-in in the shared loader**

Change the signature and add this check immediately after manifest parsing:

```python
def load_champion(
    package_dir: Path,
    expected_manifest_sha256: str,
    *,
    allow_research_candidate: bool = False,
) -> ChampionScorer:
    resolved_pkg = package_dir.resolve()
    manifest_path = (resolved_pkg / "manifest.json").resolve()
    if not manifest_path.is_file():
        raise ChampionIntegrityError(f"manifest.json missing in {resolved_pkg}")
    actual_manifest_sha = sha256_file(manifest_path)
    if actual_manifest_sha != expected_manifest_sha256:
        raise ChampionIntegrityError("manifest SHA-256 mismatch")
    manifest = ChampionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.operational_status == "RESEARCH_ONLY" and not allow_research_candidate:
        raise ChampionIntegrityError("research-only package requires ALLOW_RESEARCH_CANDIDATE=true")
```

Parse `ALLOW_RESEARCH_CANDIDATE` as exactly `true` in both `create_app_from_env()` and `WorkerSettings.from_env()`; reject every other non-empty value.

- [ ] **Step 6: Add the local build wrapper without reading `.env`**

`scripts/build_research_candidate.ps1` must invoke:

```powershell
$ErrorActionPreference = "Stop"
$manifest = "artifacts/research-candidate/manifest.json"
if (-not (Test-Path -LiteralPath $manifest)) {
  python -m industrial_reliability.package_research_candidate `
    --run-dir artifacts/phase1b/phase1b-run-6050e71c7543 `
    --features data/processed/phase1b/features.parquet `
    --feature-manifest data/processed/phase1b/feature_manifest.json `
    --output-dir artifacts/research-candidate
}
(Get-FileHash -Algorithm SHA256 -LiteralPath $manifest).Hash.ToLowerInvariant()
```

The CLI must refuse to overwrite an existing output directory. The wrapper reuses an existing package, prints only its manifest hash as the last output line, and relies on the scorer's signed-child verification during startup.

- [ ] **Step 7: Update environment and Compose names**

Use these non-secret variables:

```dotenv
SCORING_PACKAGE_DIR=artifacts/research-candidate
SCORING_MANIFEST_SHA256=
ALLOW_RESEARCH_CANDIDATE=false
```

Compose must mount `./artifacts/research-candidate:/runtime/scoring-package:ro` and pass the same variables to `scoring-api` and `streaming-worker`. Keep temporary fallback reads of `CHAMPION_PACKAGE_DIR` and `CHAMPION_MANIFEST_SHA256` for existing feasible-package users.

- [ ] **Step 8: Verify the package and runtime guard**

```powershell
python -m pytest tests/test_package_champion.py tests/test_champion.py tests/test_api.py tests/test_worker.py -q
python -m mypy src
python -m ruff check src tests
```

Expected: all commands PASS.

- [ ] **Step 9: Commit the research-only boundary**

```powershell
git add src/industrial_reliability/package_research_candidate.py src/industrial_reliability/package_champion.py src/industrial_reliability/champion.py src/industrial_reliability/api.py src/industrial_reliability/worker.py scripts/build_research_candidate.ps1 .env.example compose.yaml tests/test_package_champion.py tests/test_champion.py tests/test_api.py tests/test_worker.py
git commit -m "feat: gate an explicit research-only scoring package"
```

### Task 3: Wire replay commands and console events to real Kafka

**Files:**
- Create: `src/industrial_reliability/runtime_kafka.py`
- Create: `tests/test_runtime_kafka.py`
- Modify: `src/industrial_reliability/api.py:135-142,145-513`
- Modify: `src/industrial_reliability/persistence.py:130-158`
- Modify: `tests/test_console_api.py`
- Modify: `tests/test_persistence.py`

**Interfaces:**
- Consumes: `RuntimeStore`, `ConsoleEventBroker`, `ConsoleFeed`, `REPLAY_COMMANDS_TOPIC`, and the four console source topics.
- Produces: `RuntimeKafkaBridge.send_and_wait(topic: str, value: bytes, key: bytes) -> None`, `RuntimeKafkaBridge.lifespan(app: FastAPI) -> AsyncIterator[None]`, and `RuntimeStore.record_replay_status(status: ReplayStatusV1, model_version: str) -> None`.

- [ ] **Step 1: Write failing async publishing and identity tests**

Add:

```python
class FakeAsyncProducer:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bytes, bytes]] = []

    async def send_and_wait(self, topic: str, value: bytes, key: bytes) -> None:
        self.messages.append((topic, key, value))


def test_start_replay_uses_signed_package_identity() -> None:
    scorer = FakeScorer()
    scorer.source_dataset_sha256 = "a" * 64
    scorer.contract_sha256 = "b" * 64
    producer = FakeAsyncProducer()
    client = TestClient(create_app(scorer=scorer, producer=producer))
    response = client.post(
        "/v1/replays",
        json={
            "range_start": "2020-05-29T21:00:00",
            "range_end": "2020-05-29T22:00:00",
            "speed": 1000,
        },
    )
    assert response.status_code == 202
    command = decode_message(producer.messages[0][2], ReplayCommandV1)
    assert command.source_dataset_sha256 == "a" * 64
    assert command.contract_sha256 == "b" * 64


def test_record_replay_status_uses_runtime_model_version() -> None:
    store = RuntimeStore("postgresql://test:test@localhost:5432/test")
    status = ReplayStatusV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 2, 25, 0, 0),
        emitted_at=datetime.now(UTC),
        state="CREATED",
    )
    connection = MagicMock()
    cursor = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    with patch("psycopg.connect", return_value=connection):
        store.record_replay_status(status, "research-candidate-statistical-v1")
    assert "research-candidate-statistical-v1" in cursor.execute.call_args.args[1]
```

Add lifecycle assertions to `tests/test_runtime_kafka.py` using mocked `AIOKafkaProducer` and `AIOKafkaConsumer`: start both clients once, process one score record through `ConsoleFeed`, then stop both clients and cancel the pump task.

- [ ] **Step 2: Run the tests and confirm RED**

```powershell
python -m pytest tests/test_console_api.py tests/test_runtime_kafka.py -q
```

Expected: FAIL because replay commands currently use zero hashes and no runtime Kafka bridge exists.

- [ ] **Step 3: Create the single-process Kafka bridge**

The new class must own one producer, one console consumer, one broker, and one pump task:

```python
class RuntimeKafkaBridge:
    def __init__(self, bootstrap_servers: str, store: RuntimeStore) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.broker = ConsoleEventBroker()
        self.feed = ConsoleFeed(store=store, broker=self.broker)
        self.producer: AIOKafkaProducer | None = None
        self.consumer: AIOKafkaConsumer | None = None
        self.task: asyncio.Task[None] | None = None

    async def send_and_wait(self, topic: str, value: bytes, key: bytes) -> None:
        if self.producer is None:
            raise RuntimeError("Kafka command producer is not ready")
        await self.producer.send_and_wait(topic, value=value, key=key)

    @asynccontextmanager
    async def lifespan(self, _app: FastAPI) -> AsyncIterator[None]:
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            client_id="irp-api-command-producer-v1",
            acks="all",
            enable_idempotence=True,
        )
        self.consumer = AIOKafkaConsumer(
            REPLAY_STATUS_TOPIC,
            TELEMETRY_TOPIC,
            SCORES_TOPIC,
            ALERT_EVENTS_TOPIC,
            bootstrap_servers=self.bootstrap_servers,
            client_id="irp-api-console-feed-v1",
            group_id="irp-api-console-feed-v1",
            enable_auto_commit=True,
            auto_offset_reset="latest",
        )
        await self.producer.start()
        await self.consumer.start()
        self.task = asyncio.create_task(self._pump())
        try:
            yield
        finally:
            if self.task is not None:
                self.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.task
            await self.consumer.stop()
            await self.producer.stop()

    async def _pump(self) -> None:
        assert self.consumer is not None
        async for record in self.consumer:
            if record.topic == REPLAY_STATUS_TOPIC:
                status = decode_message(record.value, ReplayStatusV1)
                self.feed.store.record_replay_status(status, self.model_version)
            self.feed.process(record)
```

Pass `model_version` into `RuntimeKafkaBridge.__init__`. Change `RuntimeStore.record_replay_status` to accept that value and remove the hardcoded `champion-statistical-v1` database value.

- [ ] **Step 4: Make command publication awaitable and fail clearly**

Replace `_publish_command` with:

```python
async def _publish_command(producer: Any, topic: str, key: str, cmd: ReplayCommandV1) -> None:
    if producer is None or not hasattr(producer, "send_and_wait"):
        raise RuntimeError("Kafka command producer is not configured")
    await producer.send_and_wait(
        topic,
        value=encode_message(cmd),
        key=key.encode("utf-8"),
    )
```

Make both replay command endpoints `async def`, await the function, and populate identity from `scorer.source_dataset_sha256` and `scorer.contract_sha256`.

When `store` is configured, `start_replay` must persist a `ReplayStatusV1(state="CREATED")` with `scorer.model_version` before publishing the command. This establishes the foreign-key parent before console score/alert events can be stored.

- [ ] **Step 5: Attach bridge lifespan only in the environment factory**

`create_app_from_env()` must create `RuntimeStore`, `RuntimeKafkaBridge`, and then call:

```python
return create_app(
    scorer,
    store,
    producer=bridge,
    broker=bridge.broker,
    lifespan=bridge.lifespan,
)
```

Add an optional `lifespan` parameter to `create_app` and pass it to `FastAPI(title="Industrial Reliability Scoring and Alert API", version="1.0", lifespan=lifespan)`. Unit tests continue injecting `FakeAsyncProducer` and no live Kafka lifespan.

- [ ] **Step 6: Run focused API and console verification**

```powershell
python -m pytest tests/test_console_api.py tests/test_runtime_kafka.py tests/test_console_stream.py -q
python -m mypy src
```

Expected: PASS.

- [ ] **Step 7: Commit the real command/control bridge**

```powershell
git add src/industrial_reliability/runtime_kafka.py src/industrial_reliability/api.py src/industrial_reliability/persistence.py tests/test_runtime_kafka.py tests/test_console_api.py tests/test_persistence.py
git commit -m "feat: connect replay controls and console feed to kafka"
```

### Task 4: Run alert lifecycle and outbox as a real service

**Files:**
- Create: `src/industrial_reliability/alert_service.py`
- Create: `tests/test_alert_service.py`
- Modify: `src/industrial_reliability/alert_policy.py:38-55,195-294`
- Modify: `db/migrations/003_rca_reports.sql:1-14`
- Modify: `compose.yaml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: signed `alert-policy.json`, `SCORES_TOPIC`, `RuntimeStore`, `AlertConsumer`, and `AlertOutboxDispatcher`.
- Produces: `load_alert_policy(path: Path) -> LockedAlertPolicyV1`, `AlertRuntimeService.process_record(record: object) -> ProcessOutcome`, and `AlertRuntimeService.run() -> None`.

- [ ] **Step 1: Write failing policy hash and service commit tests**

```python
def write_policy_fixture(tmp_path: Path) -> Path:
    payload = {
        "schema_version": "alert-policy-v1",
        "source_split": "calibration",
        "source_scores_sha256": "a" * 64,
        "source_dataset_sha256": "b" * 64,
        "contract_sha256": "c" * 64,
        "model_id": "statistical",
        "model_version": "research-candidate-statistical-v1",
        "threshold": 1.0,
        "stride_seconds": 300,
        "persistence_decisions": 2,
        "cooldown_decisions": 2,
        "merge_gap_seconds": 300,
        "calibration_false_episodes_per_day": 0.1,
        "calibration_time_in_alert": 0.01,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    payload["policy_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path = tmp_path / "alert-policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_alert_policy_rejects_tamper(tmp_path: Path) -> None:
    path = write_policy_fixture(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["threshold"] = payload["threshold"] + 1.0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="policy SHA-256 mismatch"):
        load_alert_policy(path)


@pytest.mark.asyncio
async def test_alert_service_commits_only_processed_score() -> None:
    consumer = AsyncMock()
    alert_consumer = AsyncMock()
    alert_consumer.process.return_value = ProcessOutcome.COMMITTED
    service = AlertRuntimeService(
        alert_consumer=alert_consumer,
        dispatcher=Mock(),
        consumer=consumer,
        producer=AsyncMock(),
    )
    outcome = await service.process_record(object())
    assert outcome == ProcessOutcome.COMMITTED
    consumer.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_alert_service_does_not_commit_failed_session() -> None:
    consumer = AsyncMock()
    alert_consumer = AsyncMock()
    alert_consumer.process.return_value = ProcessOutcome.SESSION_FAILED
    service = AlertRuntimeService(
        alert_consumer=alert_consumer,
        dispatcher=Mock(),
        consumer=consumer,
        producer=AsyncMock(),
    )
    outcome = await service.process_record(object())
    assert outcome == ProcessOutcome.SESSION_FAILED
    consumer.commit.assert_not_awaited()
```

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/test_alert_service.py tests/test_alert_policy.py -q
```

Expected: FAIL because the policy loader and runtime service do not exist.

- [ ] **Step 3: Add exact policy self-hash verification**

```python
def load_alert_policy(path: Path) -> LockedAlertPolicyV1:
    data = json.loads(path.read_text(encoding="utf-8"))
    claimed = data.pop("policy_sha256", "")
    actual = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    if claimed != actual:
        raise ValueError("policy SHA-256 mismatch")
    return LockedAlertPolicyV1(**data, policy_sha256=claimed)
```

- [ ] **Step 4: Add the alert runtime loop**

`AlertRuntimeService.from_env()` must require `DATABASE_URL`, `KAFKA_BOOTSTRAP_SERVERS`, and `ALERT_POLICY_PATH`. Its `run()` method must:

```python
await producer.start()
await consumer.start()
dispatcher_task = asyncio.create_task(dispatcher.run_loop())
try:
    async for record in consumer:
        outcome = await alert_consumer.process(record)
        if outcome in {
            ProcessOutcome.COMMITTED,
            ProcessOutcome.SKIPPED,
            ProcessOutcome.QUARANTINED,
        }:
            await consumer.commit()
finally:
    dispatcher.stop()
    await dispatcher_task
    await consumer.stop()
await producer.stop()
```

`process_record()` must call `AlertConsumer.process(record)`, await `consumer.commit()` only for `COMMITTED`, `SKIPPED`, or `QUARANTINED`, and return the exact `ProcessOutcome`.

Subscribe the consumer only to `SCORES_TOPIC`, disable auto commit, and use group `irp-alert-consumer-v1`.

- [ ] **Step 5: Add the Compose service**

```yaml
  alert-service:
    build: .
    command: ["python", "-m", "industrial_reliability.alert_service"]
    volumes:
      - "./artifacts/research-candidate:/runtime/scoring-package:ro"
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      DATABASE_URL: postgresql://irp:irp_password@postgres:5432/irp
      ALERT_POLICY_PATH: /runtime/scoring-package/alert-policy.json
    depends_on:
      kafka:
        condition: service_healthy
      postgres:
        condition: service_healthy
```

The research-package build must call `lock_alert_policy(published_manifest, output_dir / "alert-policy.json")` after publishing its signed `scores.parquet`.

- [ ] **Step 6: Add an idempotent migration service and correct the RCA foreign-key type**

Change `rca_reports.alert_id` from `uuid` to `text` so it matches `alerts.alert_id`. Add this one-shot service:

```yaml
  migrate:
    image: postgres:17-alpine
    environment:
      PGPASSWORD: irp_password
    volumes:
      - "./db/migrations:/migrations:ro"
    command:
      - /bin/sh
      - -c
      - for f in /migrations/*.sql; do psql -h postgres -U irp -d irp -v ON_ERROR_STOP=1 -f "$$f"; done
    depends_on:
      postgres:
        condition: service_healthy
```

Make `scoring-api` and `alert-service` depend on `migrate` with `condition: service_completed_successfully`. This applies the `CREATE TABLE IF NOT EXISTS` migrations to existing volumes without deleting data.

- [ ] **Step 7: Verify service, migration, and Compose configuration**

```powershell
python -m pytest tests/test_alert_service.py tests/test_alert_policy.py tests/test_alert_consumer.py -q
docker compose config --quiet
```

Expected: both commands PASS when the Docker CLI is installed; the second command does not require the Docker engine.

- [ ] **Step 8: Commit the missing alert runtime**

```powershell
git add src/industrial_reliability/alert_service.py src/industrial_reliability/alert_policy.py src/industrial_reliability/package_research_candidate.py tests/test_alert_service.py db/migrations/003_rca_reports.sql compose.yaml .env.example
git commit -m "feat: run alert persistence and outbox delivery"
```

### Task 5: Replace Phase 8 mock certification with three live fault drills

**Files:**
- Create: `src/industrial_reliability/phase8_live_gate.py`
- Create: `tests/test_phase8_live_gate.py`
- Create: `tests/integration/test_phase8_live_stack.py`
- Create: `scripts/run_phase8_live_fault_drills.ps1`
- Modify: `docs/results/phase-8-observability-reliability.md`

**Interfaces:**
- Consumes: running Compose stack, the research candidate, Kafka topics, API port `8000`, worker metrics port `9102`, and the fixed MetroPT-3 telemetry file.
- Produces: `DrillObservation(drill_type: str, classification: FaultClass, passed: bool, replay_session_id: str | None, alert_id: str | None, error_code: str | None, details: dict[str, JSONScalar])`, plus `run_live_phase8_gate(output_dir: Path, git_sha: str) -> LivePhase8Report` under `artifacts/certification/<git-sha>/phase-8-live-fault-drills.json`.

Define `JSONScalar = str | int | float | bool | None` in `phase8_live_gate.py`; report details must not contain arbitrary objects or raw telemetry.

- [ ] **Step 1: Write failing report and cleanup tests**

```python
def test_live_report_requires_all_three_real_observations() -> None:
    report = LivePhase8Report.build(
        git_sha="a" * 40,
        service_outage=DrillObservation(
            "scoring-outage", "SERVICE", False, "session-1", None, "SCORING_RETRY_EXHAUSTED", {}
        ),
        machine_replay=DrillObservation(
            "known-abnormal-replay", "MACHINE", True, "session-2", "alert-1", None, {}
        ),
        malformed_telemetry=DrillObservation(
            "malformed-telemetry", "DATA", True, None, None, "INVALID_TELEMETRY_PAYLOAD", {}
        ),
    )
    assert report.verdict == "FAIL"
    assert report.evidence_level == "LIVE"


@pytest.mark.asyncio
async def test_runner_restores_stopped_services_on_failure() -> None:
    compose = Mock()
    kafka = AsyncMock()
    kafka.publish_replay_command.side_effect = RuntimeError("broker write failed")
    runner = LivePhase8Runner(compose=compose, kafka=kafka, http=Mock())
    with pytest.raises(RuntimeError, match="broker write failed"):
        await runner.run()
    compose.start.assert_any_call("scoring-api")
    compose.restart.assert_any_call("streaming-worker")
```

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/test_phase8_live_gate.py -q
```

Expected: FAIL because the live gate does not exist.

- [ ] **Step 3: Add fail-closed preflight**

The gate must verify, without printing environment values:

```python
required_files = (
    Path("data/processed/phase1b/metropt3/telemetry.parquet"),
    Path("artifacts/research-candidate/manifest.json"),
    Path("artifacts/research-candidate/alert-policy.json"),
)
for path in required_files:
    if not path.is_file():
        raise LiveGateBlocked(f"required file missing: {path}")
subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], check=True)
subprocess.run(["docker", "compose", "config", "--quiet"], check=True)
```

Also verify the supplied SHA equals `git rev-parse HEAD`, contains 40 lowercase hex characters, and is not all zeros.

- [ ] **Step 4: Implement the service-outage drill with real Kafka**

The exact sequence is:

```python
compose.stop("scoring-api")
session_id = uuid4()
await kafka.publish_replay_command(
    session_id=session_id,
    start=datetime(2020, 2, 25, 0, 0),
    end=datetime(2020, 2, 25, 1, 0),
    speed=1000,
)
failed = await kafka.wait_for_status(session_id, state="FAILED", timeout_seconds=90)
assert failed.error_code == "SCORING_RETRY_EXHAUSTED"
compose.start("scoring-api")
compose.restart("streaming-worker")
http.wait_ready("http://127.0.0.1:8000/readyz", timeout_seconds=60)
```

Do not substitute a mocked `ScoringClient`; the evidence is the consumed real `ReplayStatusV1`.

- [ ] **Step 5: Implement the known-abnormal machine replay**

Use the fixed interval and wait for a persisted alert:

```python
session_id = uuid4()
await kafka.publish_replay_command(
    session_id=session_id,
    start=datetime(2020, 5, 29, 21, 0),
    end=datetime(2020, 5, 30, 6, 30),
    speed=1000,
)
completed = await kafka.wait_for_status(session_id, state="COMPLETED", timeout_seconds=120)
alerts = http.wait_for_non_empty_alerts(session_id, timeout_seconds=60)
assert completed.replay_session_id == session_id
assert alerts[0]["state"] in {"OPEN", "RESOLVED"}
```

Record the real `replay_session_id`, `alert_id`, model version, source interval, decision count, and relevant message IDs in the report. Label the model `RESEARCH_ONLY` in the Markdown output.

- [ ] **Step 6: Implement malformed telemetry last**

Publish `b"NOT_A_VALID_JSON_RECORD{{{"` to `irp.telemetry.v1`, then consume one `QuarantineRecordV1` from `irp.quarantine.v1` and require `error_code == "INVALID_TELEMETRY_PAYLOAD"`. This drill runs last because the current worker intentionally blocks a poisoned partition; the `finally` block restarts `streaming-worker` afterward.

- [ ] **Step 7: Add atomic live report publishing**

The JSON fields must include:

```python
{
    "schema_version": "phase8-live-fault-report-v1",
    "evidence_level": "LIVE",
    "git_sha": git_sha,
    "verdict": "PASS" if all(item.passed for item in drills) else "FAIL",
    "research_model_status": "RESEARCH_ONLY",
    "drills": [item.to_dict() for item in drills],
    "report_sha256": self_hash,
}
```

Write through a same-directory temporary file and `Path.replace()`.

- [ ] **Step 8: Add the opt-in real-stack integration check**

```python
@pytest.mark.integration
@pytest.mark.slow
def test_phase8_live_stack() -> None:
    if os.environ.get("RUN_LIVE_PHASE8") != "1":
        pytest.skip("set RUN_LIVE_PHASE8=1 for the local Docker fault campaign")
    report = run_live_phase8_gate(Path(os.environ["CERTIFICATION_OUTPUT_DIR"]), current_git_sha())
    assert report.verdict == "PASS"
```

Skipping this pytest check must never create a PASS report; only `run_live_phase8_gate` writes certification evidence.

- [ ] **Step 9: Add the PowerShell wrapper**

```powershell
$ErrorActionPreference = "Stop"
docker version --format '{{.Server.Version}}' | Out-Null
$env:SCORING_MANIFEST_SHA256 = (.\scripts\build_research_candidate.ps1 | Select-Object -Last 1)
$env:ALLOW_RESEARCH_CANDIDATE = "true"
docker compose up -d --build postgres kafka scoring-api replay-producer streaming-worker alert-service operator-console prometheus grafana
$gitSha = git rev-parse HEAD
$outputDir = Join-Path "artifacts/certification" $gitSha
python -m industrial_reliability.phase8_live_gate --git-sha $gitSha --output-dir $outputDir
```

- [ ] **Step 10: Verify unit checks, then run the real campaign when Docker is available**

```powershell
python -m pytest tests/test_phase8_live_gate.py tests/test_fault_report.py -q
.\scripts\run_phase8_live_fault_drills.ps1
```

Expected: unit tests PASS; the live command fails immediately while Docker Desktop is stopped and produces a `LIVE/PASS` report only after all three real observations succeed.

- [ ] **Step 11: Commit the Phase 8 live gate**

```powershell
git add src/industrial_reliability/phase8_live_gate.py tests/test_phase8_live_gate.py tests/integration/test_phase8_live_stack.py scripts/run_phase8_live_fault_drills.ps1 docs/results/phase-8-observability-reliability.md
git commit -m "feat: certify phase 8 with live local fault drills"
```

### Task 6: Separate Phase 9 fallback evidence from live OpenAI evidence

**Files:**
- Create: `src/industrial_reliability/phase9_live_gate.py`
- Create: `tests/test_phase9_live_gate.py`
- Create: `tests/integration/test_phase9_live_provider.py`
- Create: `scripts/run_phase9_live_gate.ps1`
- Modify: `compose.yaml`
- Modify: `.env.example`
- Modify: `docs/results/phase-9-grounded-rca.md`

**Interfaces:**
- Consumes: a real `alert_id` from the Phase 8 live report and `POST /v1/alerts/{alert_id}/rca`.
- Produces: `run_live_phase9_gate(api_base_url: str, alert_id: UUID, git_sha: str, output_dir: Path) -> LivePhase9Report` with `provider_mode` exactly `LIVE_OPENAI` or `EVIDENCE_ONLY_FALLBACK`.

- [ ] **Step 1: Write failing response-classification tests**

```python
def test_complete_response_is_live_provider_evidence() -> None:
    payload = {
        "status": "COMPLETE",
        "provider_model": "configured-provider-model",
        "observations": [{"claim": "score exceeded threshold", "evidence_ids": ["evidence-1"]}],
        "evidence_ids": ["evidence-1"],
        "uncertainty": ["Anomaly evidence does not prove a mechanical root cause."],
        "evidence_bundle_sha256": "b" * 64,
    }
    report = classify_rca_response(payload, git_sha="a" * 40)
    assert report.provider_mode == "LIVE_OPENAI"
    assert report.evidence_level == "LIVE"
    assert report.verdict == "PASS"


def test_unavailable_response_is_not_live_provider_evidence() -> None:
    payload = {
        "status": "UNAVAILABLE",
        "provider_model": None,
        "observations": [{"claim": "persisted evidence only", "evidence_ids": ["evidence-1"]}],
        "evidence_ids": ["evidence-1"],
        "uncertainty": ["Anomaly evidence does not prove a mechanical root cause."],
        "evidence_bundle_sha256": "b" * 64,
    }
    report = classify_rca_response(payload, git_sha="a" * 40)
    assert report.provider_mode == "EVIDENCE_ONLY_FALLBACK"
    assert report.evidence_level == "INTEGRATION"
    assert report.verdict == "PASS"
```

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/test_phase9_live_gate.py -q
```

Expected: FAIL because the live gate and provider-mode distinction do not exist.

- [ ] **Step 3: Pass provider configuration into only the API container**

Add to `scoring-api.environment`:

```yaml
      RCA_OPENAI_API_KEY: ${RCA_OPENAI_API_KEY:-}
      RCA_OPENAI_MODEL: ${RCA_OPENAI_MODEL:-}
      RCA_TIMEOUT_SECONDS: ${RCA_TIMEOUT_SECONDS:-20}
```

Do not pass these values to Kafka, PostgreSQL, workers, frontend builds, test output, or certification JSON.

- [ ] **Step 4: Validate the real response without storing prompt or provider payload**

For `COMPLETE`, require:

```python
assert data["status"] == "COMPLETE"
assert data["provider_model"]
assert data["observations"]
allowed = set(data["evidence_ids"])
assert all(set(item["evidence_ids"]) <= allowed for item in data["observations"])
assert any("does not prove a mechanical root cause" in item.lower() for item in data["uncertainty"])
```

For `UNAVAILABLE`, require `provider_model is None`, retained evidence IDs, and the same non-causal uncertainty. Record only status, model name, evidence IDs, hashes, timestamps, and HTTP status.

- [ ] **Step 5: Add the provider/fallback wrapper with secret-safe preflight**

```powershell
$ErrorActionPreference = "Stop"
$keySet = -not [string]::IsNullOrWhiteSpace($env:RCA_OPENAI_API_KEY)
$modelSet = -not [string]::IsNullOrWhiteSpace($env:RCA_OPENAI_MODEL)
if ($keySet -ne $modelSet) { throw "RCA_OPENAI_API_KEY and RCA_OPENAI_MODEL must be set together" }
$gitSha = git rev-parse HEAD
$phase8 = Get-Content -Raw "artifacts/certification/$gitSha/phase-8-live-fault-drills.json" | ConvertFrom-Json
$alertId = $phase8.drills | Where-Object { $_.drill_type -eq "known-abnormal-replay" } | Select-Object -ExpandProperty alert_id
docker compose up -d scoring-api
python -m industrial_reliability.phase9_gate --git-sha $gitSha --output-dir "artifacts/certification/$gitSha"
python -m industrial_reliability.phase9_live_gate --git-sha $gitSha --alert-id $alertId --output-dir "artifacts/certification/$gitSha"
```

The script checks presence only and never prints the key.

- [ ] **Step 6: Add opt-in real-provider integration coverage**

```python
@pytest.mark.integration
@pytest.mark.slow
def test_phase9_live_provider() -> None:
    if os.environ.get("RUN_LIVE_PHASE9") != "1":
        pytest.skip("set RUN_LIVE_PHASE9=1 with a rotated provider key")
    report = run_live_phase9_gate(
        api_base_url="http://127.0.0.1:8000",
        alert_id=UUID(os.environ["LIVE_ALERT_ID"]),
        git_sha=current_git_sha(),
        output_dir=Path(os.environ["CERTIFICATION_OUTPUT_DIR"]),
    )
    assert report.provider_mode == "LIVE_OPENAI"
    assert report.verdict == "PASS"
```

- [ ] **Step 7: Verify both fallback and live modes**

Run fallback without provider variables:

```powershell
Remove-Item Env:RCA_OPENAI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:RCA_OPENAI_MODEL -ErrorAction SilentlyContinue
python -m pytest tests/test_phase9_live_gate.py tests/test_rca_openai.py -q
```

After rotating the disclosed key, set the new values outside command history and run:

```powershell
.\scripts\run_phase9_live_gate.ps1
```

Expected: unit/fallback checks PASS; the second command writes `provider_mode: LIVE_OPENAI` only after a real `COMPLETE` response.

- [ ] **Step 8: Commit the Phase 9 live evidence boundary**

```powershell
git add src/industrial_reliability/phase9_live_gate.py tests/test_phase9_live_gate.py tests/integration/test_phase9_live_provider.py scripts/run_phase9_live_gate.ps1 compose.yaml .env.example docs/results/phase-9-grounded-rca.md
git commit -m "feat: separate live openai evidence from fallback checks"
```

### Task 7: Make release certification exact-SHA and fail closed

**Files:**
- Modify: `src/industrial_reliability/release_certification.py:11-215`
- Modify: `src/industrial_reliability/package_release.py:10-77`
- Modify: `tests/test_release_certification.py`
- Modify: `tests/test_package_release.py`
- Modify: `.github/workflows/ci.yml`
- Remove: `docs/results/release-certification.json`
- Remove: `docs/results/release-certification.md`
- Remove: `docs/results/release-manifest.json`

**Interfaces:**
- Consumes: committed source SHA plus Phase 1B, Phase 8 live, Phase 9 contract, and Phase 9 provider/fallback reports.
- Produces: `ReleaseCertificationValidator(artifact_dir: Path, phase1b_metrics_path: Path).evaluate(git_sha: str) -> ReleaseCertificationReportV2` under `artifacts/certification/<git-sha>/release-certification.json`.

- [ ] **Step 1: Write failing exact-SHA and artifact-verdict tests**

```python
def write_minimum_artifacts(
    root: Path,
    *,
    phase8_verdict: str,
    provider_mode: str = "EVIDENCE_ONLY_FALLBACK",
) -> None:
    def write_report(name: str, payload: dict[str, Any]) -> None:
        payload["report_sha256"] = ""
        payload["report_sha256"] = hashlib.sha256(_canonical_json(payload)).hexdigest()
        (root / name).write_text(json.dumps(payload), encoding="utf-8")

    root.mkdir(parents=True, exist_ok=True)
    (root / "phase-1b-metrics.json").write_text(
        json.dumps({"verdict": "NOT FEASIBLE", "selected_model": None}),
        encoding="utf-8",
    )
    write_report(
        "phase-8-live-fault-drills.json",
        {
            "schema_version": "phase8-live-fault-report-v1",
            "evidence_level": "LIVE",
            "git_sha": "a" * 40,
            "verdict": phase8_verdict,
            "drills": [],
        },
    )
    write_report(
        "phase-9-contract-gate.json",
        {
            "schema_version": "phase-9-rca-contract-v1",
            "evidence_level": "UNIT",
            "git_sha": "a" * 40,
            "verdict": "PASS",
        },
    )
    write_report(
        "phase-9-live-rca.json",
        {
            "schema_version": "phase-9-live-rca-v1",
            "evidence_level": "LIVE" if provider_mode == "LIVE_OPENAI" else "INTEGRATION",
            "provider_mode": provider_mode,
            "git_sha": "a" * 40,
            "verdict": "PASS",
        },
    )


@pytest.mark.parametrize("git_sha", ["0" * 40, "abc", "G" * 40])
def test_release_rejects_invalid_git_sha(tmp_path: Path, git_sha: str) -> None:
    write_minimum_artifacts(tmp_path, phase8_verdict="PASS")
    report = ReleaseCertificationValidator(
        tmp_path,
        tmp_path / "phase-1b-metrics.json",
    ).evaluate(git_sha=git_sha)
    assert report.verdict == "INVALID"
    assert report.is_certified is False


def test_release_rejects_phase8_file_with_fail_verdict(tmp_path: Path) -> None:
    write_minimum_artifacts(tmp_path, phase8_verdict="FAIL")
    report = ReleaseCertificationValidator(
        tmp_path,
        tmp_path / "phase-1b-metrics.json",
    ).evaluate(git_sha="a" * 40)
    assert report.is_certified is False
    assert "phase8_live_fault_drills" not in report.phases_passed


def test_negative_research_release_preserves_provider_mode(tmp_path: Path) -> None:
    write_minimum_artifacts(tmp_path, phase8_verdict="PASS", provider_mode="LIVE_OPENAI")
    report = ReleaseCertificationValidator(
        tmp_path,
        tmp_path / "phase-1b-metrics.json",
    ).evaluate(git_sha="a" * 40)
    assert report.verdict == "NEGATIVE_RESEARCH_RELEASE"
    assert report.provider_mode == "LIVE_OPENAI"
    assert report.is_certified is True
```

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/test_release_certification.py tests/test_package_release.py -q
```

Expected: FAIL because the current validator accepts zero SHA and file presence alone.

- [ ] **Step 3: Validate every required artifact semantically**

Create helpers with exact boundaries:

```python
def validate_git_sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value) or value == "0" * 40:
        raise ValueError("git_sha must be a non-zero lowercase 40-character SHA")
    return value


def verify_self_hash(data: dict[str, Any], field: str = "report_sha256") -> bool:
    claimed = data.get(field, "")
    candidate = dict(data)
    candidate[field] = ""
    return claimed == hashlib.sha256(_canonical_json(candidate)).hexdigest()
```

Require:

```python
phase1b["verdict"] == "NOT FEASIBLE"
phase1b["selected_model"] is None
phase8["schema_version"] == "phase8-live-fault-report-v1"
phase8["evidence_level"] == "LIVE"
phase8["verdict"] == "PASS"
phase8["git_sha"] == git_sha
phase9_contract["evidence_level"] == "UNIT"
phase9_contract["verdict"] == "PASS"
phase9_provider["provider_mode"] in {"LIVE_OPENAI", "EVIDENCE_ONLY_FALLBACK"}
phase9_provider["verdict"] == "PASS"
```

Every failed condition adds a limitation and keeps `is_certified=False`.

- [ ] **Step 4: Resolve the current SHA automatically and keep artifacts untracked**

Change the CLI default from zeros to:

```python
git_sha = (
    args.git_sha
    or subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
)
```

Add CLI argument `--phase1b-metrics` with default `docs/results/phase-1b-metrics.json`. Default output becomes `artifacts/certification/<git-sha>/release-certification.json`. Remove the three tracked dynamic release files listed above; do not delete immutable Phase 1/1B benchmark evidence.

- [ ] **Step 5: Keep CI and live certification separate**

CI continues to run Ruff, format, Mypy, pytest, build, frontend tests, and frontend build. Add a final step that verifies tracked files contain neither `RCA_OPENAI_API_KEY=sk-` nor `"git_sha": "0000000000000000000000000000000000000000"`; do not add provider calls to pull-request CI.

- [ ] **Step 6: Run release tests and full local quality gates**

```powershell
python -m pytest tests/test_release_certification.py tests/test_package_release.py -q
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest -m "not slow"
python -m build
```

Expected: all commands PASS with branch coverage at least 80%.

- [ ] **Step 7: Commit the release truth gate**

```powershell
git add src/industrial_reliability/release_certification.py src/industrial_reliability/package_release.py tests/test_release_certification.py tests/test_package_release.py .github/workflows/ci.yml docs/results/release-certification.json docs/results/release-certification.md docs/results/release-manifest.json
git commit -m "fix: certify releases from exact-sha live evidence"
```

### Task 8: Align the portfolio demo, documentation, and Business Review inputs

**Files:**
- Create: `scripts/run_portfolio_demo.ps1`
- Create: `apps/operator-console/e2e/operator-console.live.spec.ts`
- Modify: `README.md`
- Modify: `docs/RUNBOOK.md`
- Modify: `docs/ARCHITECTURE_DIAGRAMS.md`
- Modify: `docs/MODEL_CARD.md`
- Modify: `task.md`
- Final artifact during execution: `docs/portfolio/industrial-reliability-business-review.pptx`

**Interfaces:**
- Consumes: exact-SHA release report and Phase 1B/8/9 evidence artifacts.
- Produces: one ordered demo command, truthful hiring-team landing page, and the source inputs for the retained Business Review template.

- [ ] **Step 1: Add documentation assertions before rewriting prose**

Extend `tests/test_portfolio_claims.py` or add a focused Markdown test:

```python
def test_portfolio_docs_do_not_overclaim() -> None:
    combined = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("README.md", "docs/RUNBOOK.md", "docs/MODEL_CARD.md")
    )
    assert "research-candidate-statistical-v1" in combined
    assert "NOT FEASIBLE" in combined
    assert "production-ready detector" not in combined.lower()
    assert "http://127.0.0.1:5173" in combined
    assert "db/migrations/001_alert_lifecycle.sql" in combined
    assert "db/migrations/002_console_stream.sql" in combined
```

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/test_portfolio_claims.py -q
```

Expected: FAIL on current port, migration, model-role, or status wording.

- [ ] **Step 3: Rewrite README around evidence rather than phases**

The first screen must contain exactly these facts:

```markdown
> **Portfolio status:** Negative-research Production AI case study.
> Phase 1B did not produce a feasible anomaly detector. The local runtime uses
> `research-candidate-statistical-v1` only when explicitly enabled and must not
> be used for autonomous maintenance or shutdown decisions.
```

Then present four sections in this order: measured ML result, five-step live demo, evidence-level table, architecture/deep-dive links. Move the Phase 7-10 chronology below the hiring-team summary.

- [ ] **Step 4: Correct runbook/runtime drift**

Use these exact local endpoints:

```text
API              http://127.0.0.1:8000
Operator console http://127.0.0.1:5173
Grafana          http://127.0.0.1:3001
Prometheus       http://127.0.0.1:9090
MLflow           http://127.0.0.1:5000
Kafka            127.0.0.1:29092
PostgreSQL       127.0.0.1:5432
```

Reference only the real migration filenames `001_alert_lifecycle.sql`, `002_console_stream.sql`, and `003_rca_reports.sql`. Explain that Docker's init directory applies automatically only when PostgreSQL initializes a new volume.

- [ ] **Step 5: Add the ordered demo wrapper**

```powershell
$ErrorActionPreference = "Stop"
$env:SCORING_MANIFEST_SHA256 = (.\scripts\build_research_candidate.ps1 | Select-Object -Last 1)
$env:ALLOW_RESEARCH_CANDIDATE = "true"
docker compose up -d --build
.\scripts\run_phase8_live_fault_drills.ps1
.\scripts\run_phase9_live_gate.ps1
$gitSha = git rev-parse HEAD
python -m industrial_reliability.release_certification --git-sha $gitSha --artifact-dir "artifacts/certification/$gitSha" --phase1b-metrics docs/results/phase-1b-metrics.json
$phase8 = Get-Content -Raw "artifacts/certification/$gitSha/phase-8-live-fault-drills.json" | ConvertFrom-Json
$phase9 = Get-Content -Raw "artifacts/certification/$gitSha/phase-9-live-rca.json" | ConvertFrom-Json
$env:RUN_LIVE_UI = "1"
$env:LIVE_REPLAY_SESSION_ID = ($phase8.drills | Where-Object { $_.drill_type -eq "known-abnormal-replay" }).replay_session_id
$env:EXPECT_LIVE_RCA = if ($phase9.provider_mode -eq "LIVE_OPENAI") { "1" } else { "0" }
Push-Location apps/operator-console
npx playwright test e2e/operator-console.live.spec.ts
Pop-Location
```

If provider variables are absent, the wrapper must run and record the fallback path rather than claim `LIVE_OPENAI`.

- [ ] **Step 6: Update architecture and task status**

Architecture diagrams must show `alert-service` and the API's Kafka bridge. `task.md` must state that implementation is complete only for code merged through the current branch, while live Phase 8, live Phase 9, and exact-SHA release status are read from the current artifact directory rather than hardcoded as complete.

- [ ] **Step 7: Add an opt-in Playwright test with real clicks and no route mocks**

Create `operator-console.live.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

test.skip(process.env.RUN_LIVE_UI !== '1', 'set RUN_LIVE_UI=1 for the running local stack');

test('starts a real replay from the operator console', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Start Time').fill('2020-05-29T21:00');
  await page.getByLabel('End Time').fill('2020-05-29T22:00');
  await page.getByLabel('Speed').selectOption('1000');
  await page.getByTestId('start-replay-btn').click();
  await expect(page.getByTestId('session-id-input')).not.toHaveValue('');
  await expect(page.getByTestId('replay-state-badge')).toBeVisible({ timeout: 30000 });
});

test('opens a persisted real alert and requests RCA', async ({ page }) => {
  const sessionId = process.env.LIVE_REPLAY_SESSION_ID;
  if (!sessionId) throw new Error('LIVE_REPLAY_SESSION_ID is required');
  await page.goto('/');
  await page.getByTestId('session-id-input').fill(sessionId);
  await page.getByTestId('connect-session-btn').click();
  const alert = page.locator('[data-row-id^="alert-row-"]').first();
  await expect(alert).toBeVisible({ timeout: 60000 });
  await alert.click();
  await expect(page.getByTestId('evidence-table')).toBeVisible();
  await page.getByTestId('generate-rca-btn').click();
  const expected = process.env.EXPECT_LIVE_RCA === '1' ? 'COMPLETE' : 'UNAVAILABLE';
  await expect(page.getByTestId('rca-status-badge')).toHaveText(expected, { timeout: 60000 });
  await expect(page.getByTestId('rca-uncertainty')).toContainText(
    'does not prove a mechanical root cause',
  );
});
```

Do not call `page.route()` in this file. In `run_portfolio_demo.ps1`, read the Phase 8 report, set `RUN_LIVE_UI=1`, set `LIVE_REPLAY_SESSION_ID` to the machine-drill session, set `EXPECT_LIVE_RCA=1` only when the Phase 9 report says `LIVE_OPENAI`, and run `npx playwright test e2e/operator-console.live.spec.ts`.

- [ ] **Step 8: Define the Business Review deck from verified evidence only**

After the exact-SHA report passes, use the retained Business Review template to create eight slides:

1. Project objective and Production AI hiring audience.
2. MetroPT-3 data and leakage-safe evaluation contract.
3. Negative model result: detection versus false-alarm trade-off.
4. Runtime architecture and research-only safety boundary.
5. Phase 8 real service/data/machine fault evidence.
6. Phase 9 contract, fallback, and live-provider evidence level.
7. Engineering decisions: MLflow adopted; Airflow, Spark, and OpenVINO rejected or N/A.
8. Remaining limitations and interview discussion points.

Every number must come from the exact-SHA artifacts; every external claim must have a `[Sources]` notes block. Render and inspect every slide before delivery.

- [ ] **Step 9: Run documentation and full verification**

```powershell
python -m pytest tests/test_portfolio_claims.py -q
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest -m "not slow"
docker compose config --quiet
```

Expected: all commands PASS. Live certification remains a separate explicit run.

- [ ] **Step 10: Commit portfolio alignment**

```powershell
git add README.md docs/RUNBOOK.md docs/ARCHITECTURE_DIAGRAMS.md docs/MODEL_CARD.md task.md scripts/run_portfolio_demo.ps1 apps/operator-console/e2e/operator-console.live.spec.ts tests/test_portfolio_claims.py
git commit -m "docs: present an evidence-led production ai case study"
```

## Final Execution Gate

After Tasks 1-8 are committed:

```powershell
git status --short --branch
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest -m "not slow"
python -m build
Push-Location apps/operator-console
npm ci
npm run test:coverage
npm run build
Pop-Location
docker compose config --quiet
```

Then, with Docker Desktop running and a rotated provider key available outside command history:

```powershell
.\scripts\run_portfolio_demo.ps1
```

Done means all of the following are true:

- PR CI is green; local results are not substituted for GitHub status.
- The Phase 1B result remains `NOT FEASIBLE` with no champion.
- The scorer reports `RESEARCH_ONLY` and refuses startup without explicit opt-in.
- Phase 8 has a `LIVE/PASS` report containing three real observations and exact Git SHA.
- Phase 9 reports `LIVE_OPENAI` only after a real provider response; fallback remains separately labeled.
- Release certification verifies semantic verdicts and self-hashes, not file presence.
- Dynamic certification artifacts remain outside git under `artifacts/certification/<git-sha>/`.
- README, runbook, model card, architecture, demo, and Business Review use only verified claims.
- PR #15 remains unmerged until the remote checks and the required evidence gate are reviewed.
