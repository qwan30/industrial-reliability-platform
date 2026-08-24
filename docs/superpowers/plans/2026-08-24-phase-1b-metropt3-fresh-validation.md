# Phase 1B MetroPT-3 Fresh Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the one permitted fresh MetroPT-3 validation without changing the permanent Phase 1 `NOT FEASIBLE` evidence, and either publish a `FEASIBLE` champion manifest or stop the platform roadmap.

**Architecture:** Add a separate Phase 1B contract, source preflight, causal five-minute-bin feature path, and benchmark entry point while reusing the Phase 1 detector ladder and evaluation arithmetic. Raw data, fitted models, per-window scores, and manifests stay under ignored local artifact directories; only aggregate Phase 1B evidence is published.

**Tech Stack:** Python 3.12, stdlib `hashlib`/`zipfile`, NumPy, pandas, PyArrow, scikit-learn, PyTorch, pytest

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Phase 1 at `ba703a3aae130522b7628d5db4813c804d8d4213` remains permanent `NOT FEASIBLE` evidence; Phase 1B writes new files and never rewrites Phase 1 results.
- Commit `ba703a3aae130522b7628d5db4813c804d8d4213` must be an ancestor of the Phase 1B worktree `HEAD`; otherwise implementation stops before any file change or data access.
- The source DOI is `10.24432/C5VW3R`, URL is `https://archive.ics.uci.edu/static/public/791/metropt%2B3%2Bdataset.zip`, archive SHA-256 is `aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a`, normalized row count is `1,516,948`, and the locally recorded license is `CC BY 4.0`.
- Any URL, DOI, license, archive checksum, CSV member, schema, or normalized-row mismatch fails closed and requires a new design decision.
- `lps` is evaluation evidence only; timestamp is provenance only; neither can enter feature selection, fitting, calibration, or scoring.
- Use right-closed five-minute bins with at least 24 observations, six consecutive valid bins per 30-minute causal window, and a five-minute stride; never fill, interpolate, center, or cross an invalid bin, timestamp regression, or split boundary.
- Fit transforms and models on train only, choose thresholds on calibration only, and evaluate the frozen ladder once on holdout.
- The gate is at least 3/4 detected events, at most 1 false episode per valid normal-exposure day, and at most 5% time in alert; ties prefer statistical, then Isolation Forest, then autoencoder.
- Raw, derived, score, and model artifacts remain local and git-ignored. Committed evidence contains only source attribution, contracts, aggregate metrics, limitations, code, and tests.
- Every quality pass runs Ruff, Ruff formatting, mypy, pytest with at least 80% branch coverage, `pip check`, and package build.

---

### Task 1: Freeze the independent MetroPT-3 contract

**Files:**
- Create: `src/industrial_reliability/phase1b_contracts.py`
- Create: `tests/test_phase1b_contracts.py`
- Create: `docs/data/metropt3-source-attribution.md`

**Interfaces:**
- Consumes: approved literals in the roadmap spec.
- Produces: immutable `PHASE1B: Phase1BContract`, `phase1b_contract_manifest() -> dict[str, object]`, and `phase1b_evaluation_events() -> tuple[Event, ...]`.

- [ ] **Step 1: Write the failing contract tests**

```python
from industrial_reliability.phase1b_contracts import (
    PHASE1B,
    phase1b_contract_manifest,
    phase1b_evaluation_events,
)


def test_phase1b_freezes_source_and_leakage_boundaries() -> None:
    assert PHASE1B.source_doi == "10.24432/C5VW3R"
    assert PHASE1B.archive_sha256 == "aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a"
    assert PHASE1B.expected_rows == 1_516_948
    assert PHASE1B.license == "CC BY 4.0"
    assert PHASE1B.csv_member == "MetroPT3(AirCompressor).csv"
    assert "lps" not in PHASE1B.predictor_columns
    assert "timestamp" not in PHASE1B.predictor_columns
    assert PHASE1B.min_bin_observations == 24
    assert PHASE1B.lookback_bins == 6


def test_phase1b_events_normalize_minute_precision_half_open() -> None:
    events = phase1b_evaluation_events()
    assert len(events) == 4
    assert events[0].source_start.isoformat(timespec="minutes") == "2020-04-18T00:00"
    assert events[0].source_end.isoformat(timespec="minutes") == "2020-04-19T00:00"
    assert phase1b_contract_manifest()["contract_sha256"]
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_phase1b_contracts.py -q`

Expected: FAIL with `ModuleNotFoundError: industrial_reliability.phase1b_contracts`.

- [ ] **Step 3: Implement the frozen contract and canonical hash**

```python
@dataclass(frozen=True, slots=True)
class MetroPT3Event:
    event_id: str
    source_start_minute: datetime
    source_end_minute: datetime
    condition: str

    @property
    def normalized_end(self) -> datetime:
        return self.source_end_minute + timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class Phase1BContract:
    contract_version: str
    source_url: str
    source_doi: str
    license: str
    archive_sha256: str
    csv_member: str
    expected_rows: int
    source_columns: tuple[str, ...]
    canonical_columns: tuple[str, ...]
    analog_columns: tuple[str, ...]
    digital_columns: tuple[str, ...]
    predictor_columns: tuple[str, ...]
    train: Split
    calibration: Split
    holdout: Split
    events: tuple[MetroPT3Event, ...]
    bin_seconds: int = 300
    min_bin_observations: int = 24
    lookback_bins: int = 6
    stride_seconds: int = 300
    event_horizon_seconds: int = 7_200
    threshold_quantile: float = 0.995
    threshold_method: str = "higher"
    anomaly_inclusive: bool = True
    min_detected_events: int = 3
    max_false_episodes_per_day: float = 1.0
    max_time_in_alert: float = 0.05


def phase1b_evaluation_events() -> tuple[Event, ...]:
    return tuple(
        Event(
            event_id=item.event_id,
            failure_type=item.condition,
            source_start=item.source_start_minute,
            source_end=item.normalized_end,
            source_precision="minute",
            paper_count=0,
            local_lps_transition=None,
            disagreement=None,
        )
        for item in PHASE1B.events
    )
```

Freeze the raw member header as `Unnamed: 0`, `timestamp`, `TP2`, `TP3`, `H1`, `DV_pressure`, `Reservoirs`, `Oil_temperature`, `Motor_current`, `COMP`, `DV_eletric`, `Towers`, `MPG`, `LPS`, `Pressure_switch`, `Oil_level`, `Caudal_impulses`; normalize it to the 16 lowercase canonical names in the spec and validate the discarded index as contiguous `0..1_516_947`.

- [ ] **Step 4: Add attribution and run focused checks**

Write `docs/data/metropt3-source-attribution.md` with the exact URL, DOI, archive hash, member, row count, `CC BY 4.0`, access date `2026-08-24`, local-only data rule, and the four original minute literals. Then run:

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_phase1b_contracts.py -q`

Expected: PASS; the manifest hash is stable across repeated calls and the event conversion preserves original literals while using half-open arithmetic.

- [ ] **Step 5: Commit the contract slice**

```powershell
git add src/industrial_reliability/phase1b_contracts.py tests/test_phase1b_contracts.py docs/data/metropt3-source-attribution.md
git commit -m "feat: freeze MetroPT-3 validation contract"
```

Expected: one commit containing only the executable Phase 1B contract, tests, and source attribution.

### Task 2: Validate and normalize the archive fail closed

**Files:**
- Create: `src/industrial_reliability/phase1b_data.py`
- Create: `tests/test_phase1b_data.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `PHASE1B`, `phase1b_contract_manifest()`, and a local UCI ZIP.
- Produces: `prepare_metropt3(archive: Path, output_dir: Path, contract: Phase1BContract = PHASE1B) -> MetroPT3PreparationManifest` and normalized `telemetry.parquet` plus hashed `manifest.json`.

- [ ] **Step 1: Write source-identity and schema rejection tests**

```python
@pytest.mark.parametrize(
    (mutation, message),
    [
        ("hash", "archive SHA-256"),
        ("member", "CSV member"),
        ("header", "source header"),
        ("rows", "normalized row count"),
        ("license", "license"),
    ],
)
def test_prepare_metropt3_fails_closed_on_identity_mismatch(
    tmp_path: Path, metropt3_zip: Path, mutation: str, message: str
) -> None:
    contract = mutated_contract(mutation)
    with pytest.raises(MetroPT3ContractError, match=message):
        prepare_metropt3(metropt3_zip, tmp_path / "prepared", contract)


def test_conflicting_duplicate_timestamp_is_rejected(tmp_path: Path) -> None:
    archive = synthetic_archive(tmp_path, duplicate="conflicting")
    with pytest.raises(MetroPT3ContractError, match="conflicting duplicate"):
        prepare_metropt3(archive, tmp_path / "prepared", sample_contract(archive))
```

The fixtures must also prove byte-identical duplicate rows are collapsed, timestamps remain naive, `lps` remains in Parquet, and the normalized column order exactly matches the contract.

- [ ] **Step 2: Run tests and verify the missing implementation failure**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_phase1b_data.py -q`

Expected: FAIL because `industrial_reliability.phase1b_data` does not exist.

- [ ] **Step 3: Implement bounded ZIP extraction and validation**

```python
@dataclass(frozen=True, slots=True)
class MetroPT3PreparationManifest:
    archive_sha256: str
    contract_sha256: str
    output_sha256: str
    normalized_rows: int
    canonical_columns: tuple[str, ...]
    identical_duplicates_removed: int
    first_timestamp: datetime
    last_timestamp: datetime
    manifest_sha256: str


def prepare_metropt3(
    archive: Path,
    output_dir: Path,
    contract: Phase1BContract = PHASE1B,
) -> MetroPT3PreparationManifest:
    if output_dir.exists():
        raise FileExistsError(f"destination already exists: {output_dir}")
    if sha256_file(archive) != contract.archive_sha256:
        raise MetroPT3ContractError("archive SHA-256 does not match the frozen contract")
    if contract.license != "CC BY 4.0" or contract.source_doi != "10.24432/C5VW3R":
        raise MetroPT3ContractError("license or DOI does not match the frozen contract")
    with ZipFile(archive) as bundle:
        members = tuple(item.filename for item in bundle.infolist() if not item.is_dir())
        if members != (contract.csv_member,):
            raise MetroPT3ContractError(f"CSV member mismatch: {members}")
        if Path(contract.csv_member).name != contract.csv_member:
            raise MetroPT3ContractError("CSV member must not escape the archive root")
        with bundle.open(contract.csv_member) as source:
            frame = pd.read_csv(source)
    return _validate_and_publish(frame, archive, output_dir, contract)
```

`_validate_and_publish` must require exact raw header order, finite analog values, binary state values, contiguous source index, naive parseable timestamps, and sorted non-regressing output. Compare complete duplicate rows before dropping identical copies; reject conflicts. Rename only by the explicit source-to-canonical mapping, require exactly `1_516_948` normalized rows, and atomically publish Parquet and a canonical-JSON manifest containing the archive, contract, output, row, and schema hashes.

- [ ] **Step 4: Protect local evidence and run focused tests**

Add `data/raw/metropt3/`, `data/processed/phase1b/`, and `artifacts/phase1b/` to `.gitignore`, preserving existing rules. Run:

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_phase1b_data.py -q`

Expected: PASS, including cleanup after parse failure and rejection of any pre-existing destination.

- [ ] **Step 5: Commit the source preparation slice**

```powershell
git add .gitignore src/industrial_reliability/phase1b_data.py tests/test_phase1b_data.py
git commit -m "feat: validate MetroPT-3 source fail closed"
```

Expected: no ZIP, CSV, Parquet, or local manifest is staged.

### Task 3: Build shared causal five-minute features

**Files:**
- Create: `src/industrial_reliability/causal_features.py`
- Create: `src/industrial_reliability/phase1b_features.py`
- Create: `tests/test_causal_features.py`
- Create: `tests/test_phase1b_features.py`

**Interfaces:**
- Consumes: normalized canonical telemetry and `Phase1BContract`.
- Produces: `TelemetrySample`, `CoverageEvidence`, `compute_feature_values(samples, feature_names) -> tuple[float, ...]`, `iter_phase1b_windows(frame, contract) -> Iterator[Phase1BWindow]`, and `build_phase1b_features(prepared_dir, output_path, contract) -> Phase1BFeatureManifest`.

- [ ] **Step 1: Write causal-window and leakage tests**

```python
def test_six_valid_right_closed_bins_make_one_causal_window() -> None:
    samples = samples_for_bins(counts=(24, 24, 24, 24, 24, 24))
    windows = tuple(iter_phase1b_windows(samples, SAMPLE_CONTRACT))
    assert len(windows) == 1
    assert windows[0].coverage.observations_by_bin == (24, 24, 24, 24, 24, 24)


def test_invalid_bin_closes_segment_without_filling() -> None:
    samples = samples_for_bins(counts=(24, 24, 23, 24, 24, 24, 24, 24, 24))
    assert tuple(iter_phase1b_windows(samples, SAMPLE_CONTRACT)) == ()


def test_lps_and_future_rows_cannot_change_features() -> None:
    baseline = one_window_frame()
    changed = baseline.copy()
    changed.loc[:, "lps"] = 1 - changed["lps"]
    changed.loc[changed.index[-1] + 1] = future_outlier()
    assert window_values(baseline) == window_values(changed)
```

Also test that a timestamp regression, missing five-minute bin, or partition boundary resets the segment; analog standard deviation uses `ddof=0`; digital transition counts include only transitions inside the 30-minute window.

- [ ] **Step 2: Run tests and verify the missing modules fail**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_causal_features.py tests\test_phase1b_features.py -q`

Expected: FAIL because the causal feature modules do not exist.

- [ ] **Step 3: Implement the shared pure feature math**

```python
@dataclass(frozen=True, slots=True)
class TelemetrySample:
    timestamp: datetime
    analog: tuple[float, ...]
    digital: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CoverageEvidence:
    bin_ends: tuple[datetime, ...]
    observations_by_bin: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Phase1BWindow:
    split: Literal["train", "calibration", "holdout"]
    window_start: datetime
    window_end: datetime
    feature_names: tuple[str, ...]
    feature_values: tuple[float, ...]
    coverage: CoverageEvidence


def compute_feature_values(
    samples: Sequence[TelemetrySample], feature_names: Sequence[str]
) -> tuple[float, ...]:
    analog = np.asarray([sample.analog for sample in samples], dtype=np.float64)
    digital = np.asarray([sample.digital for sample in samples], dtype=np.int8)
    values = _all_candidate_statistics(analog, digital)
    return tuple(float(values[name]) for name in feature_names)
```

Implement `_all_candidate_statistics` for analog `last`, `mean`, population `std`, `min`, `max`, `delta` and digital `last`, `active_ratio`, `transition_count`. The caller supplies the exact ordered active feature names, so this function is the only math used later by offline and online paths.

- [ ] **Step 4: Implement split-safe window iteration and train-only constant removal**

```python
def fit_active_feature_names(train: pd.DataFrame, candidates: tuple[str, ...]) -> tuple[str, ...]:
    constant = train.loc[:, candidates].nunique(dropna=False).eq(1)
    active = tuple(name for name in candidates if not bool(constant[name]))
    if not active:
        raise FeatureContractError("train contains no non-constant predictive features")
    return active
```

Define immutable `Phase1BFeatureManifest` with `contract_sha256`, `data_manifest_sha256`, `candidate_feature_names`, `active_feature_names`, `removed_train_constant_names`, per-split window counts, rejection counts, output SHA-256, and manifest SHA-256. Store maps as sorted tuples of `(name, count)` pairs so the frozen manifest has no mutable members.

Anchor five-minute bins to midnight with right-closed intervals `(end - 5 minutes, end]`; accept a bin only at 24 or more observations. `iter_phase1b_windows` keeps six adjacent accepted bins from one split and emits a five-minute-stride window; any invalid/missing bin, non-increasing timestamp, or split change clears the buffer. Build all candidate columns first, derive `active_feature_names` from train only, apply that frozen order to calibration and holdout, and write the removed names plus per-split/rejection counts to the hashed feature manifest.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_causal_features.py tests\test_phase1b_features.py -q`

Expected: PASS; a holdout-only constant change cannot alter the active schema, and `lps` never appears in candidate or active names.

- [ ] **Step 5: Commit the feature slice**

```powershell
git add src/industrial_reliability/causal_features.py src/industrial_reliability/phase1b_features.py tests/test_causal_features.py tests/test_phase1b_features.py
git commit -m "feat: build causal MetroPT-3 feature windows"
```

Expected: one independently reviewable feature commit with no dataset artifact.

### Task 4: Generalize evaluation typing and run the frozen ladder

**Files:**
- Modify: `src/industrial_reliability/evaluation.py`
- Create: `src/industrial_reliability/phase1b_benchmark.py`
- Modify: `tests/test_evaluation.py`
- Create: `tests/test_phase1b_benchmark.py`

**Interfaces:**
- Consumes: active Phase 1B feature Parquet, existing `RobustStatisticalDetector`, `IsolationForestDetector`, `DenseAutoencoderDetector`, and evaluation functions.
- Produces: `fit_phase1b_candidate(*, model_id: ModelId, train_features: NDArray[np.float64], calibration_features: NDArray[np.float64], contract: Phase1BContract = PHASE1B) -> FittedCandidate`, `run_phase1b_benchmark(*, prepared_dir: Path, feature_path: Path, artifact_dir: Path) -> Phase1BBenchmarkResult`, local `scores.parquet`, `champion-manifest.json` only on a feasible run, and `publish_phase1b_results(run_dir: Path, output_dir: Path) -> tuple[Path, Path]`.

- [ ] **Step 1: Write compatibility and gate tests before refactoring**

```python
def test_phase1_evaluation_result_is_unchanged_by_policy_protocol() -> None:
    assert evaluate(sample_phase1_scores(), (), 99.0, sample_events(), PHASE1) == EXPECTED_RESULT


def test_phase1b_champion_requires_every_gate(tmp_path: Path) -> None:
    result = publish_fixture_run(tmp_path, detected=2, false_rate=0.0, time_in_alert=0.0)
    assert result.selected_model is None
    assert not (result.run_dir / "champion-manifest.json").exists()


def test_phase1b_selects_simplest_passing_model(tmp_path: Path) -> None:
    result = publish_fixture_run(tmp_path, passing=("statistical", "autoencoder"))
    champion = json.loads((result.run_dir / "champion-manifest.json").read_text())
    assert champion["schema_version"] == "phase1b-champion-v1"
    assert champion["verdict"] == "FEASIBLE"
    assert champion["model_id"] == "statistical"
```

Also assert the threshold provenance is `calibration`, `0.995`, `higher`; `scores.parquet` has exact columns `model_id`, `split`, `window_start`, `window_end`, `score`, `threshold`, `is_anomaly`; and the original `docs/results/phase-1-metrics.json` remains `selected_model: null`.

- [ ] **Step 2: Run focused tests and verify the new benchmark failure**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_evaluation.py tests\test_phase1b_benchmark.py -q`

Expected: existing evaluation tests PASS and Phase 1B tests FAIL because `phase1b_benchmark` does not exist.

- [ ] **Step 3: Replace the concrete evaluation type with a structural policy**

```python
class EvaluationPolicy(Protocol):
    stride_seconds: int
    event_horizon_seconds: int
    threshold_quantile: float
    threshold_method: str
    anomaly_inclusive: bool
    min_detected_events: int
    max_false_episodes_per_day: float
    max_time_in_alert: float
```

Change only the annotations of `calibrate_threshold`, `build_episodes`, `evaluate`, and their private helpers from `Phase1Contract` to `EvaluationPolicy`. Do not alter arithmetic. Run the existing evaluation suite immediately after the annotation refactor.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_evaluation.py -q`

Expected: PASS with byte-for-byte equal fixture results.

- [ ] **Step 4: Implement one locked Phase 1B benchmark command**

```python
type ModelId = Literal["statistical", "isolation_forest", "autoencoder"]
MODEL_IDS: tuple[ModelId, ...] = ("statistical", "isolation_forest", "autoencoder")


@dataclass(frozen=True, slots=True)
class LockedThreshold:
    split: Literal["calibration"] = "calibration"
    quantile: float = 0.995
    method: Literal["higher"] = "higher"


@dataclass(frozen=True, slots=True)
class FittedCandidate:
    model_id: ModelId
    detector: RobustStatisticalDetector | IsolationForestDetector | DenseAutoencoderDetector
    threshold: float
    threshold_provenance: LockedThreshold


@dataclass(frozen=True, slots=True)
class Phase1BBenchmarkResult:
    run_dir: Path
    verdict: Literal["FEASIBLE", "NOT FEASIBLE"]
    selected_model: ModelId | None
    contract_sha256: str
    source_dataset_sha256: str


def fit_phase1b_candidate(
    *,
    model_id: ModelId,
    train_features: NDArray[np.float64],
    calibration_features: NDArray[np.float64],
    contract: Phase1BContract = PHASE1B,
) -> FittedCandidate:
    detector = detector_for(model_id).fit(train_features)
    threshold = calibrate_threshold(detector.score(calibration_features), contract)
    return FittedCandidate(
        model_id=model_id,
        detector=detector,
        threshold=threshold,
        threshold_provenance=LockedThreshold(),
    )


def run_phase1b_benchmark(
    *, prepared_dir: Path, feature_path: Path, artifact_dir: Path
) -> Phase1BBenchmarkResult:
    contract = PHASE1B
    feature_manifest = verify_phase1b_inputs(prepared_dir, feature_path, contract)
    frames = load_locked_splits(feature_path, feature_manifest.active_feature_names)
    fitted = tuple(
        fit_phase1b_candidate(
            model_id=model_id,
            train_features=frames.train.values,
            calibration_features=frames.calibration.values,
            contract=contract,
        )
        for model_id in MODEL_IDS
    )
    results = tuple(evaluate_holdout_once(item, frames.holdout, contract) for item in fitted)
    selected = next((item for item in results if item.evaluation.feasible), None)
    return write_private_run(artifact_dir, feature_manifest, results, selected, contract)
```

`fit_phase1b_candidate` is the public reproducible refit surface for Phase 7 and must never accept or load holdout rows. `evaluate_holdout_once` is called once per fitted candidate, scores holdout without mutation, and records all splits in `scores.parquet`. Persist fitted detectors as `models/{model_id}.joblib`, plus `evidence-baseline.npz` containing exact arrays `feature_names`, train `median`, and train `mad`. A feasible `champion-manifest.json` must include schema `phase1b-champion-v1`, verdict, run ID, model ID/version, threshold provenance, split bounds, ordered active feature names, contract/source/data/feature/git hashes, and an `artifact_sha256` mapping for `scores.parquet`, the selected model, and evidence baseline. Do not create that manifest on an infeasible run.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_evaluation.py tests\test_phase1b_benchmark.py -q`

Expected: PASS; test fixtures prove exactly one holdout evaluation per model and no post-holdout threshold/model mutation.

- [ ] **Step 5: Commit the benchmark slice**

```powershell
git add src/industrial_reliability/evaluation.py src/industrial_reliability/phase1b_benchmark.py tests/test_evaluation.py tests/test_phase1b_benchmark.py
git commit -m "feat: run locked Phase 1B benchmark"
```

Expected: existing Phase 1 evaluation behavior is preserved and the new command writes only Phase 1B artifact names.

### Task 5: Execute once, publish aggregate evidence, and enforce the terminal branch

**Files:**
- Create from the publisher: `docs/results/phase-1b-metrics.json`
- Create from the publisher: `docs/results/phase-1b-metropt3-fresh-validation.md`
- Create: `tests/test_phase1b_published_results.py`
- Create: `requirements-phase1b.txt`

**Interfaces:**
- Consumes: exact UCI archive and the locked Phase 1B command.
- Produces: immutable aggregate verdict plus either a private non-null champion manifest or an explicit roadmap stop.

- [ ] **Step 1: Add published-artifact schema tests before the full run**

```python
@pytest.mark.slow
def test_published_phase1b_artifacts_are_aggregate_and_separate() -> None:
    phase1 = json.loads(Path("docs/results/phase-1-metrics.json").read_text())
    phase1b = json.loads(Path("docs/results/phase-1b-metrics.json").read_text())
    assert phase1["selected_model"] is None
    assert phase1b["schema_version"] == "phase1b-benchmark-v1"
    assert "scores" not in phase1b
    assert "model_weights" not in phase1b
    assert phase1b["verdict"] in {"FEASIBLE", "NOT FEASIBLE"}
```

- [ ] **Step 2: Capture the exact environment and run all preflight gates**

```powershell
git merge-base --is-ancestor ba703a3aae130522b7628d5db4813c804d8d4213 HEAD
if ($LASTEXITCODE -ne 0) { throw "Phase 1 evidence commit is not an ancestor of HEAD" }
.\.venv\Scripts\python.exe -m pip freeze --exclude-editable | Sort-Object | Set-Content -Encoding ascii requirements-phase1b.txt
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -m "not slow" --cov=industrial_reliability --cov-branch --cov-fail-under=80
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
```

Expected: every command exits 0 before holdout is evaluated; `git status --short` shows no raw/derived/model artifact.

- [ ] **Step 3: Prepare and execute the locked full-data run exactly once**

```powershell
.\.venv\Scripts\python.exe -m industrial_reliability.phase1b_data --archive data/raw/metropt3/metropt+3+dataset.zip --output-dir data/processed/phase1b/metropt3
.\.venv\Scripts\python.exe -m industrial_reliability.phase1b_features --prepared-dir data/processed/phase1b/metropt3 --output data/processed/phase1b/features.parquet
.\.venv\Scripts\python.exe -m industrial_reliability.phase1b_benchmark --prepared-dir data/processed/phase1b/metropt3 --features data/processed/phase1b/features.parquet --artifact-dir artifacts/phase1b --publish-dir docs/results
```

Expected: preflight validates every frozen source literal before processing; the benchmark writes one new hashed local run and the two Phase 1B aggregate files without altering either Phase 1 result file.

- [ ] **Step 4: Run the terminal gate and complete validation**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests/test_phase1b_published_results.py -q
.\.venv\Scripts\python.exe -m pytest --cov=industrial_reliability --cov-branch --cov-fail-under=80
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
git diff --check
git status --short
```

Expected on `FEASIBLE`: the aggregate selects one passing model and the referenced local run contains a valid non-null `champion-manifest.json`. Expected on `NOT FEASIBLE`: no champion manifest exists, Phases 2-10 remain blocked, and work moves only to Phase 11 negative-research release planning.

- [ ] **Step 5: Commit only aggregate evidence and environment provenance**

```powershell
git add requirements-phase1b.txt tests/test_phase1b_published_results.py docs/results/phase-1b-metrics.json docs/results/phase-1b-metropt3-fresh-validation.md
git commit -m "docs: publish Phase 1B validation verdict"
git ls-files data artifacts
```

Expected: the commit contains no private data, scores, model weights, or local manifests; `git ls-files data artifacts` returns no Phase 1B raw or private artifact. Stop here if the verdict is not `FEASIBLE`.

## Whole-Phase Review and Merge Gate

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest --cov=industrial_reliability --cov-branch --cov-fail-under=80
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
git diff --check
git status --short --branch
```

Merge only with exact command evidence and a reviewed aggregate verdict. A `FEASIBLE` merge must identify the exact private champion manifest and all hashes; an infeasible merge permanently blocks Phase 2 and preserves both negative results as honest research evidence.
