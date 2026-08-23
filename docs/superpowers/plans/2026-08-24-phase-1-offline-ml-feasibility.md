# Phase 1 Offline ML Feasibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine, with a reproducible leakage-safe benchmark, whether abnormal periods around the three known MetroPT events are detectable by a robust statistical baseline, Isolation Forest, and a simple dense PyTorch autoencoder.

**Architecture:** Convert the verified local CSV into gap-bounded Parquet segments, derive right-aligned causal window features, assign whole windows to fixed chronological train/calibration/holdout partitions, fit every transform/model on train only, choose thresholds on calibration only, and evaluate the locked ladder once on holdout. Keep raw/derived telemetry and model artifacts local; commit only code, tests, contracts, aggregate metrics, and limitations.

**Tech Stack:** Python 3.12, standard library, NumPy, pandas, PyArrow, scikit-learn, PyTorch, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md`

**Research inputs:**

- `docs/research/research-readiness-review.md`
- `docs/research/metropt-dataset-investigation.md`
- `docs/research/metropt-dataset-profile.json`
- `docs/research/domain-knowledge-report.md`
- `docs/research/github-reference-map.md`

## Global Constraints

- Use only `data/raw/metropt/dataset_train.csv`, identified locally by 1,646,201,046 bytes, 10,773,588 rows, and SHA-256 `3fd0788c1b8fb7753ac0a2047f487c87f59b8b36af2f5553e4990354ed86d168`; never call this checksum official or redistribute the dataset while its authoritative license remains unknown.
- Preserve raw bytes unchanged and never commit raw CSV, derived Parquet/features, model weights, checkpoints, or per-window scores.
- Treat timestamps as naive/unspecified; never label them UTC.
- Never use random row/window splitting. The fixed order is train, calibration, then future holdout.
- A window belongs to a split only when its complete raw lookback lies inside that split; purge the full 30-minute lookback at boundaries.
- A feature at time `t` may use only `(t - 30 minutes, t]`; reject any window crossing a timestamp delta greater than one second. Never backfill, use centered rolling operations, interpolate gaps, or share raw observations across splits.
- Primary predictors are `TP2`, `TP3`, `H1`, `DV_pressure`, `Reservoirs`, `Oil_temperature`, `Flowmeter`, `Motor_current`, `COMP`, `DV_eletric`, `Towers`, `MPG`, and `Caudal_impulses`.
- Keep `timestamp` as index/provenance only. Preserve but exclude `LPS` from preprocessing, feature selection, fitting, and threshold calibration; use it only as separately labeled evaluation evidence.
- Preserve but exclude `Pressure_switch`, `Oil_level`, `gpsLong`, `gpsLat`, `gpsSpeed`, and `gpsQuality` from the primary benchmark. Do not encode physical polarity for `H1`, `COMP`, or `MPG`.
- Preserve the three paper event intervals and their minute precision. Keep the incompatible Failure 3 paper count as a separate source fact; do not invent a corrected label count.
- Fit feature filtering, scalers, baseline parameters, Isolation Forest, and autoencoder only on train. Select each score threshold only from calibration. Do not retune after holdout results.
- Fixed partitions are train `[2022-01-01 06:00:00, 2022-02-01 00:00:00)`, calibration `[2022-02-01 00:00:00, 2022-02-21 00:00:00)`, and holdout `[2022-02-21 00:00:00, 2022-06-02 15:49:54)`.
- Use 1,800-second right-aligned windows with a 300-second stride. A valid window contains exactly 1,800 consecutive one-second observations. Anchor each segment at its first timestamp: the first decision occurs at `segment_start + 1,799 seconds`, then every 300 seconds.
- Analog features are `last`, `mean`, population `std`, `min`, `max`, and `delta = last - first`. Digital features are `last`, `active_ratio`, and `transition_count`.
- Statistical score is the maximum absolute robust z-score over train-nonconstant features, using train median and `1.4826 * MAD`. Isolation Forest uses `n_estimators=200`, `max_samples="auto"`, `contamination="auto"`, `random_state=42`, and `n_jobs=1`; use `-score_samples` as the anomaly score.
- Dense autoencoder uses train-only `StandardScaler`, widths `[input, 64, 16, 64, input]`, ReLU hidden layers, MSE, Adam `lr=0.001`, batch size 256, 20 epochs, CPU, seed 42, deterministic algorithms, and Windows-safe `num_workers=0`.
- Threshold is the calibration score 99.5th percentile with NumPy `method="higher"`; a decision is anomalous when `score >= threshold`. Merge adjacent anomalous decisions into one evaluation episode when consecutive `window_end` timestamps differ by at most the 300-second stride. Do not implement Phase 4 persistence/cooldown/storage.
- Detection time is the first anomalous `window_end`, never `window_start`. A holdout episode matches an event when its detection time lies in `[event_start - 2 hours, event_end)` or its decision interval overlaps `[event_start, event_end)`. Lead time is `event_start - first_detection_time` and may be negative; report LPS-relative lead time separately where local LPS evidence exists.
- Report absolute event detections, per-event first detection/lead time, false episodes per valid normal-exposure day, window PR-AUC, and time in alert. Label a holdout decision positive when `window_end` lies in `[event_start - 2 hours, event_end)`. Normal exposure days are `normal_valid_decision_count * 300 / 86,400`; time in alert is `anomalous_valid_decision_count / valid_holdout_decision_count`. Accuracy is not a primary metric.
- Predeclared feasibility gate: at least 2 of 3 holdout events detected, no more than 1 false episode per valid normal-exposure day, and no more than 5% time in alert. If no model meets all three, Phase 1 concludes `NOT FEASIBLE` without moving the goalposts.
- Choose the simplest model meeting the gate. For ties, prefer statistical baseline, then Isolation Forest, then autoencoder.
- Do not add Kafka, Spark, replay, FastAPI, operational alerting, Airflow, MLflow infrastructure, monitoring, LLM/RCA, OpenVINO, supervised failure classification, or copied reference-repository code in Phase 1.
- Use the project Python 3.12 venv explicitly on Windows: `.\.venv\Scripts\python.exe`; bare `python` resolves to Python 3.9 in this workspace.
- Preserve the owner-controlled untracked `.codex/` directory and never stage it.
- Every task uses strict RED-GREEN-REFACTOR, maintains at least 80% branch coverage, passes focused tests, and creates one logical conventional commit.

## Frozen Phase 1 Decision Record

This plan is the approved Phase 1 decision record. Approval provenance is the user's 2026-08-24 instruction to commit/push the research, plan phase by phase, then execute continuously. The local CSV is approved for private feasibility analysis only; official-release equivalence and license remain explicitly unknown.

The exact ordered source schema is:

```text
timestamp, TP2, TP3, H1, DV_pressure, Reservoirs, Oil_temperature,
Flowmeter, Motor_current, COMP, DV_eletric, Towers, MPG, LPS,
Pressure_switch, Oil_level, Caudal_impulses, gpsLong, gpsLat,
gpsSpeed, gpsQuality
```

The exact event literals are:

| ID | Type | Source interval `[start,end)` | Precision | Paper count | Local LPS evidence | Preserved disagreement |
|---|---|---|---|---:|---|---|
| `failure-1` | clients air leak | `2022-02-28 21:53:00` to `2022-03-01 02:00:00` | minute | 14,820 | first `LPS=1` at `2022-02-28 22:50:43` | paper time is minute-level, not exact `:00` activation |
| `failure-2` | air-dryer leak | `2022-03-23 14:54:00` to `2022-03-23 15:24:00` | minute | 1,800 | no `LPS=1` inside the closed local interval | 2022 narrative conflicts with 2026 table and local interval |
| `failure-3` | compressor oil leak | `2022-05-30 12:00:00` to `2022-06-02 06:18:00` | minute | 281,800 | first `LPS=1` at `2022-06-02 06:18:33` | paper count exceeds its stated gap-free interval and local coverage has 43,197 absent seconds |

The ordered feature names are generated sensor-major, then statistic-major:

```python
FEATURE_COLUMNS = tuple(
    f"{column}__{statistic}"
    for column in ANALOG_COLUMNS
    for statistic in ("last", "mean", "std", "min", "max", "delta")
) + tuple(
    f"{column}__{statistic}"
    for column in DIGITAL_COLUMNS
    for statistic in ("last", "active_ratio", "transition_count")
)
```

`ANALOG_COLUMNS` and `DIGITAL_COLUMNS` preserve the predictor order stated in Global Constraints. These 63 names, all split/window/model/evaluation settings, the dataset identity, limitations, approval provenance, and event literals are members of `Phase1Contract` and therefore covered by its hash.

Canonical contract hashing uses:

```python
payload = json.dumps(
    manifest_without_hash,
    sort_keys=True,
    ensure_ascii=True,
    allow_nan=False,
    separators=(",", ":"),
).encode("utf-8")
contract_sha256 = hashlib.sha256(payload).hexdigest()
```

All datetimes serialize with `datetime.isoformat(timespec="seconds")` and no timezone suffix.

## Project Phase Sequence

| Phase | Gate to begin | Deliverable | Status after this plan |
|---|---|---|---|
| 1. Offline ML feasibility | Research verdict `READY WITH OPEN QUESTIONS` and this frozen contract | Reproducible actual metrics and feasibility verdict | Implemented by Tasks 1-8 |
| 2. Productionize selected model | Phase 1 selects a justified model and artifact contract | Saved-model scoring API | Deferred; create a dedicated plan from Phase 1 evidence |
| 3. Historical replay/streaming | Stable offline feature/scoring contracts | Replay through Kafka/Spark | Deferred |
| 4. Operational alerting | Stable online scores and measured threshold behavior | Traceable persisted alert | Deferred |
| 5. MLOps | Stable training/scoring workflow | MLflow/Airflow reproducibility | Deferred |
| 6. Monitoring | Running services and data contracts | Service/data/model observability | Deferred |
| 7. RCA assistant | Traceable alert/evidence APIs | Grounded alert explanation | Deferred |
| 8. OpenVINO | Selected PyTorch artifact and baseline benchmark | Measured PyTorch/OpenVINO comparison | Deferred |

---

### Task 1: Freeze the executable Phase 1 contract

**Files:**

- Create: `src/industrial_reliability/contracts.py`
- Create: `tests/test_contracts.py`

**Interfaces:**

- Produces: immutable `Phase1Contract`, `Event`, `Split`, `PHASE1`, and `contract_manifest()` used by every later task.
- Consumes: no implementation code; exact values come from Global Constraints.

- [ ] **Step 1: Write the failing contract tests**

```python
from industrial_reliability.contracts import PHASE1, contract_manifest


def test_contract_excludes_leakage_columns() -> None:
    assert "LPS" not in PHASE1.predictor_columns
    assert not set(PHASE1.predictor_columns) & {
        "timestamp",
        "Pressure_switch",
        "Oil_level",
        "gpsLong",
        "gpsLat",
        "gpsSpeed",
        "gpsQuality",
    }


def test_contract_is_chronological_and_hashable() -> None:
    assert PHASE1.train.end <= PHASE1.calibration.start
    assert PHASE1.calibration.end <= PHASE1.holdout.start
    manifest = contract_manifest(PHASE1)
    assert manifest["contract_version"] == "phase1-v1"
    assert len(manifest["contract_sha256"]) == 64


def test_contract_freezes_dataset_schema_and_events() -> None:
    assert PHASE1.dataset_rows == 10_773_588
    assert PHASE1.source_columns[0] == "timestamp"
    assert PHASE1.source_columns[-1] == "gpsQuality"
    assert len(PHASE1.source_columns) == 21
    assert [event.paper_count for event in PHASE1.events] == [14_820, 1_800, 281_800]
    assert PHASE1.events[2].disagreement is not None
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_contracts.py -q`

Expected: FAIL because `industrial_reliability.contracts` does not exist.

- [ ] **Step 3: Implement the immutable contract with standard library only**

```python
@dataclass(frozen=True)
class Split:
    name: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Event:
    event_id: str
    failure_type: str
    source_start: datetime
    source_end: datetime
    source_precision: str
    paper_count: int
    local_lps_transition: datetime | None
    disagreement: str | None


@dataclass(frozen=True)
class Phase1Contract:
    contract_version: str
    approval_provenance: str
    dataset_license_status: str
    dataset_sha256: str
    dataset_bytes: int
    dataset_rows: int
    source_columns: tuple[str, ...]
    predictor_columns: tuple[str, ...]
    analog_columns: tuple[str, ...]
    digital_columns: tuple[str, ...]
    analog_statistics: tuple[str, ...]
    digital_statistics: tuple[str, ...]
    analog_std_ddof: int
    feature_columns: tuple[str, ...]
    train: Split
    calibration: Split
    holdout: Split
    events: tuple[Event, ...]
    window_seconds: int = 1800
    stride_seconds: int = 300
    event_horizon_seconds: int = 7200
    threshold_quantile: float = 0.995
    threshold_method: str = "higher"
    min_detected_events: int = 2
    max_false_episodes_per_day: float = 1.0
    max_time_in_alert: float = 0.05
    random_seed: int = 42
    benchmark_policy_version: str = "phase1-policy-v1"
    robust_mad_scale: float = 1.4826
    statistical_aggregation: str = "max_abs_robust_z"
    anomaly_inclusive: bool = True
    segment_anchor_policy: str = "first_complete_window_then_segment_relative_stride"
    isolation_forest_estimators: int = 200
    isolation_forest_max_samples: str = "auto"
    isolation_forest_contamination: str = "auto"
    isolation_forest_n_jobs: int = 1
    isolation_forest_score_rule: str = "negative_score_samples"
    autoencoder_hidden_width: int = 64
    autoencoder_bottleneck_width: int = 16
    autoencoder_activation: str = "relu"
    autoencoder_loss: str = "mse"
    autoencoder_optimizer: str = "adam"
    autoencoder_learning_rate: float = 0.001
    autoencoder_batch_size: int = 256
    autoencoder_epochs: int = 20
    autoencoder_scaler: str = "standard_scaler_train_only"
    autoencoder_device: str = "cpu"
    autoencoder_deterministic: bool = True
    autoencoder_num_workers: int = 0
    episode_interval_policy: str = "first_window_end_to_last_window_end_plus_stride"
    event_label_policy: str = "window_end_in_prewarning_horizon_or_episode_overlap"
    normal_exposure_policy: str = "normal_valid_decisions_times_stride"
```

`PHASE1` must populate every field from Global Constraints and the Frozen Phase 1 Decision Record. `contract_manifest()` must serialize dataclasses with the canonical JSON procedure above and append a SHA-256 of the payload excluding the hash field.

- [ ] **Step 4: Run focused tests and quality checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_contracts.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m ruff check src\industrial_reliability\contracts.py tests\test_contracts.py
.\.venv\Scripts\python.exe -m mypy src\industrial_reliability\contracts.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/industrial_reliability/contracts.py tests/test_contracts.py
git commit -m "feat: freeze Phase 1 benchmark contract"
```

### Task 2: Prepare bounded, source-faithful Parquet segments

**Files:**

- Create: `src/industrial_reliability/data.py`
- Create: `tests/helpers.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_data.py`

**Interfaces:**

- Consumes: `Phase1Contract` and exact source schema from Task 1.
- Produces: `sha256_file(path: Path) -> str`, `SegmentManifest`, `PreparationManifest`, and `prepare_dataset(source: Path, output_dir: Path, contract: Phase1Contract = PHASE1) -> PreparationManifest`.
- Output layout: `output_dir/segments/segment-0000.parquet` and `output_dir/manifest.json`; all are ignored local artifacts.
- Test-only helpers produced for later tasks: `write_sample_csv(path, timestamps)`, `sample_contract(source)`, `sample_policy(**overrides)`, `make_segment(seconds)`, `make_segment_around_split_boundary()`, `sample_contract_for_frame(frame)`, `seeded_training_matrix(rows, columns)`, and `score_frame(offsets, scores)`.

`SegmentManifest` fields are `segment_id`, relative `path`, `start`, `end`, `rows`, and `sha256`. `PreparationManifest` fields are `dataset_sha256`, `dataset_bytes`, `dataset_rows`, `contract_sha256`, `source_columns`, `total_rows`, `gap_count`, `segments`, and `manifest_sha256`.

- [ ] **Step 1: Add deterministic test-data helpers and a sample fixture**

`write_sample_csv()` writes the exact 21-column source header and deterministic synthetic rows for caller-supplied timestamps. Analog values are simple counters and digital values alternate 0/1. GPS-unavailable rows set `gpsLong`, `gpsLat`, and `gpsQuality` to zero; `gpsSpeed` is validated independently, and fixtures include valid coordinates with speed zero. `sample_contract()` uses `dataclasses.replace(PHASE1, ...)` to replace fixture identity, `window_seconds=60`, `stride_seconds=10`, and `event_horizon_seconds=120`. For a 7,200-second benchmark fixture it uses train `[start,start+2,400s)`, calibration `[start+2,400s,start+4,800s)`, holdout `[start+4,800s,start+7,200s)`, and three 60-second synthetic events starting 600, 1,200, and 1,800 seconds into holdout. This leaves nonzero normal exposure before/between events. For shorter ingestion-only fixtures, split/event times may extend beyond the rows because Task 2 does not evaluate windows. `tests/conftest.py` exposes `sample_csv`, containing six rows and one missing second between rows three and four. No production row is copied.

- [ ] **Step 2: Write failing tests for identity, schema, and gap segmentation**

```python
def test_prepare_dataset_splits_at_gap(tmp_path: Path, sample_csv: Path) -> None:
    contract = sample_contract(sample_csv)
    manifest = prepare_dataset(sample_csv, tmp_path, contract=contract)
    assert [segment.rows for segment in manifest.segments] == [3, 3]
    assert manifest.gap_count == 1
    assert manifest.total_rows == 6


def test_prepare_dataset_rejects_hash_mismatch(tmp_path: Path, sample_csv: Path) -> None:
    with pytest.raises(DataContractError, match="SHA-256"):
        prepare_dataset(sample_csv, tmp_path, contract=replace(PHASE1, dataset_sha256="0" * 64))
```

Also cover wrong header/order, wrong row count, malformed timestamp, non-binary digital value, non-monotonic timestamp, coordinate/quality sentinel disagreement, and valid coordinates with `gpsSpeed=0`.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_data.py -q`

Expected: FAIL because `industrial_reliability.data` does not exist.

- [ ] **Step 4: Implement one bounded preparation path**

Use `hashlib.file_digest`, `pyarrow.csv.open_csv` with explicit types, NumPy timestamp deltas inside each record batch, and one open `pyarrow.parquet.ParquetWriter` per current segment. Stream record-batch slices directly to that writer; close it at each gap before opening the next. Carry the final row/timestamp across record-batch boundaries. Write into a unique empty sibling temporary directory, close every handle, then atomically rename it to an absent destination. Reject an existing destination, including a nonempty directory without a manifest. Never call `pandas.read_csv` on the full file and never modify the source.

```python
def prepare_dataset(
    source: Path,
    output_dir: Path,
    contract: Phase1Contract = PHASE1,
) -> PreparationManifest:
    """Validate source identity and write one Parquet file per 1 Hz segment."""
```

The function must write to a new output directory, fail if it already contains a manifest, close all readers/writers before returning, and record source hash/size, schema, row count, gap count, segment bounds/counts, and contract hash.

- [ ] **Step 5: Run focused tests and quality checks**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_data.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m ruff check src\industrial_reliability\data.py tests\test_data.py
.\.venv\Scripts\python.exe -m mypy src\industrial_reliability\data.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/industrial_reliability/data.py tests/helpers.py tests/conftest.py tests/test_data.py
git commit -m "feat: prepare gap-bounded MetroPT segments"
```

### Task 3: Build causal features and chronological split assignment

**Files:**

- Create: `src/industrial_reliability/features.py`
- Create: `tests/test_features.py`

**Interfaces:**

- Consumes: Task 2 segment files and Task 1 contract.
- Produces: `FeatureManifest`, `extract_segment_features(frame: pd.DataFrame, contract: Phase1Contract) -> pd.DataFrame`, and `build_features(prepared_dir: Path, output_path: Path, contract: Phase1Contract = PHASE1) -> FeatureManifest`.
- Feature table columns: `window_start`, `window_end`, `split`, then the exact 63 predictors (48 analog features and 15 digital features).

`FeatureManifest` fields are `contract_sha256`, `data_manifest_sha256`, ordered `feature_columns`, `total_windows`, `windows_by_split`, `rejected_windows_by_reason`, relative `output_path`, `output_sha256`, and `manifest_sha256`.

- [ ] **Step 1: Write failing causal-window tests**

```python
def test_future_change_does_not_change_prior_feature() -> None:
    original = make_segment(seconds=2100)
    changed = original.copy()
    changed.loc[changed.index[-1], "TP2"] = 9999.0
    contract = sample_contract_for_frame(original)
    before = extract_segment_features(original, contract)
    after = extract_segment_features(changed, contract)
    pd.testing.assert_series_equal(before.iloc[0], after.iloc[0])


def test_windows_never_cross_gap_or_split_boundary() -> None:
    frame = make_segment_around_split_boundary()
    contract = sample_contract_for_frame(frame)
    result = extract_segment_features(frame, contract)
    assert (result["window_end"] - result["window_start"]).dt.total_seconds().eq(1799).all()
    for row in result.itertuples():
        split = getattr(contract, row.split)
        assert row.window_start >= split.start
        assert row.window_end < split.end
```

Also assert `tuple(result.columns[3:]) == contract.feature_columns`, no LPS/GPS/excluded columns, first valid end exactly at `segment_start + window_seconds - 1`, every later end aligned to the segment anchor modulo `stride_seconds`, and train/calibration/holdout ordering.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_features.py -q`

Expected: FAIL because `industrial_reliability.features` does not exist.

- [ ] **Step 3: Implement segment-local feature extraction**

Read one Parquet segment at a time. For each eligible 1,800-row window ending every 300 rows, compute:

```text
analog: last, mean, std(ddof=0), min, max, delta
digital: last, active_ratio, transition_count
```

Assign a split only when `window_start >= split.start` and `window_end < split.end`; windows crossing a split boundary are omitted, which supplies the full-lookback purge. Write features incrementally with `pyarrow.parquet.ParquetWriter` and record counts per segment/split plus rejected-window reasons.

- [ ] **Step 4: Run focused tests and quality checks**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_features.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m ruff check src\industrial_reliability\features.py tests\test_features.py
.\.venv\Scripts\python.exe -m mypy src\industrial_reliability\features.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/industrial_reliability/features.py tests/test_features.py
git commit -m "feat: build causal MetroPT window features"
```

### Task 4: Lock calibration and event evaluation semantics

**Files:**

- Create: `src/industrial_reliability/evaluation.py`
- Create: `tests/test_evaluation.py`

**Interfaces:**

- Produces: `calibrate_threshold(calibration_scores, contract: Phase1Contract) -> float`, `build_episodes(scores, threshold, contract: Phase1Contract) -> tuple[Episode, ...]`, and `evaluate(holdout_scores, episodes, threshold, events, contract: Phase1Contract) -> EvaluationResult`.
- Consumes: model-independent score frames with `window_start`, `window_end`, and `score`.

`Episode` fields are `detection_time` (first anomalous `window_end`), `last_detection_time`, and `decision_count`; its evaluation interval is `[detection_time, last_detection_time + contract.stride_seconds)`. `EventResult` fields are `event_id`, `evaluable`, `matching_horizon_valid_decisions`, `source_interval_valid_decisions`, `source_interval_coverage_seconds`, `detected`, `first_detection_time`, `lead_seconds_to_source_start`, and optional `lead_seconds_to_local_lps`. `EvaluationResult` fields are `threshold`, `valid_holdout_decisions`, `positive_decisions`, `anomalous_decisions`, `normal_valid_decisions`, `normal_exposure_days`, `time_in_alert`, `pr_auc`, `detected_events`, `total_events`, `false_episodes`, `false_episodes_per_day`, `event_results`, and `feasible`.

- [ ] **Step 1: Write failing calibration-isolation tests**

```python
def test_threshold_uses_higher_calibration_quantile() -> None:
    calibration = np.array([0.0, 1.0, 2.0, 3.0])
    assert calibrate_threshold(calibration, sample_policy()) == 3.0


def test_adjacent_anomalies_form_one_episode() -> None:
    contract = sample_policy(stride_seconds=300)
    episodes = build_episodes(score_frame([0, 300, 600], [2.0, 3.0, 0.0]), 1.0, contract)
    assert len(episodes) == 1
    assert episodes[0].detection_time == score_frame([0], [2.0]).iloc[0]["window_end"]
```

Add exact arithmetic cases for `score == threshold` being anomalous, minute-precision events, positive/negative lead time from `window_end`, separate LPS lead time, `normal_exposure_days = normal_valid_decisions * stride / 86_400`, zero-exposure rejection, `time_in_alert = anomalous_decisions / valid_holdout_decisions`, PR-AUC, and the 2-of-3 feasibility gate.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_evaluation.py -q`

Expected: FAIL because `industrial_reliability.evaluation` does not exist.

- [ ] **Step 3: Implement the smallest model-independent evaluator**

Use the contract's quantile/method, horizon, stride, inclusive threshold flag, and feasibility-gate fields; use `sklearn.metrics.average_precision_score`, immutable event/episode result dataclasses, and discrete valid exposure from holdout windows outside `[event_start - contract.event_horizon_seconds, event_end)`. Use the same horizons as PR-AUC positives. Compute each event's valid matching-horizon decisions and valid source-interval decisions/seconds, and mark it evaluable only when its matching horizon has at least one valid decision. Reject empty calibration, non-finite scores, non-monotonic windows, unevaluable events, and zero normal exposure.

- [ ] **Step 4: Run focused tests and quality checks**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_evaluation.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m ruff check src\industrial_reliability\evaluation.py tests\test_evaluation.py
.\.venv\Scripts\python.exe -m mypy src\industrial_reliability\evaluation.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/industrial_reliability/evaluation.py tests/test_evaluation.py
git commit -m "feat: evaluate Phase 1 anomaly episodes"
```

### Task 5: Implement statistical and Isolation Forest scorers

**Files:**

- Create: `src/industrial_reliability/models.py`
- Create: `tests/test_models.py`

**Interfaces:**

- Produces concrete `RobustStatisticalDetector` and `IsolationForestDetector`, each with `fit(train: NDArray[np.float64]) -> Self` and `score(values: NDArray[np.float64]) -> NDArray[np.float64]`.
- No factory, registry, base class, or serialization layer in Phase 1.

- [ ] **Step 1: Write failing deterministic model tests**

```python
def test_robust_detector_scores_outlier_higher() -> None:
    train = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    model = RobustStatisticalDetector().fit(train)
    assert model.score(np.array([[100.0, 100.0]]))[0] > model.score(train).max()


def test_isolation_forest_is_deterministic() -> None:
    train = seeded_training_matrix()
    first = IsolationForestDetector().fit(train).score(train)
    second = IsolationForestDetector().fit(train).score(train)
    np.testing.assert_allclose(first, second)
```

Also cover fit-before-score errors, non-finite input rejection, train-zero-MAD feature removal, unchanged caller arrays, and rejection with `ValueError("all training features have zero MAD")` when no statistical feature remains.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_models.py -q`

Expected: FAIL because `industrial_reliability.models` does not exist.

- [ ] **Step 3: Implement the two concrete detectors**

The statistical detector stores train medians/MADs and a nonconstant-feature mask. The forest wraps exactly one configured `sklearn.ensemble.IsolationForest` and returns `-model.score_samples(values)`. Copy inputs only when a dependency requires mutation protection.

- [ ] **Step 4: Run focused tests and quality checks**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_models.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m ruff check src\industrial_reliability\models.py tests\test_models.py
.\.venv\Scripts\python.exe -m mypy src\industrial_reliability\models.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/industrial_reliability/models.py tests/test_models.py
git commit -m "feat: add Phase 1 classical detectors"
```

### Task 6: Add the minimal deterministic dense autoencoder

**Files:**

- Modify: `pyproject.toml`
- Create: `requirements-phase1.txt`
- Create: `src/industrial_reliability/autoencoder.py`
- Create: `tests/test_autoencoder.py`

**Interfaces:**

- Produces: `DenseAutoencoderDetector.fit(train) -> Self` and `.score(values) -> NDArray[np.float64]` with per-row MSE; `.contributions(values) -> NDArray[np.float64]` returns per-feature squared errors.
- Produces read-only `scaler_mean` and `scaler_scale` copies for provenance/testing; scoring never refits them.
- Consumes: the same 2-D feature matrix as Task 5.

- [ ] **Step 1: Add PyTorch as the only new Phase 1 dependency**

Add `torch>=2.7,<3` to runtime dependencies. Keep CPU as the default; do not add Lightning, Optuna, MLflow, CUDA-specific packages, or a model framework. CI already installs project runtime dependencies, so leave the workflow unchanged.

- [ ] **Step 2: Write failing shape, determinism, and train-only-scaler tests**

```python
def test_autoencoder_scores_and_contributions_have_expected_shapes() -> None:
    train = seeded_training_matrix(rows=512, columns=6)
    model = DenseAutoencoderDetector(epochs=2).fit(train)
    assert model.score(train).shape == (512,)
    assert model.contributions(train).shape == train.shape


def test_autoencoder_does_not_mutate_training_data() -> None:
    train = seeded_training_matrix(rows=64, columns=4)
    original = train.copy()
    DenseAutoencoderDetector(epochs=1).fit(train)
    np.testing.assert_array_equal(train, original)


def test_autoencoder_is_deterministic_and_scoring_does_not_refit() -> None:
    train = seeded_training_matrix(rows=128, columns=4)
    first = DenseAutoencoderDetector(epochs=2).fit(train)
    second = DenseAutoencoderDetector(epochs=2).fit(train)
    np.testing.assert_allclose(first.score(train), second.score(train), rtol=0, atol=1e-7)
    mean_before = first.scaler_mean.copy()
    first.score(train + 10_000.0)
    np.testing.assert_array_equal(first.scaler_mean, mean_before)
```

- [ ] **Step 3: Run the focused test and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_autoencoder.py -q
```

Expected: FAIL because `industrial_reliability.autoencoder` does not exist.

- [ ] **Step 4: Implement one dense CPU model**

Fit `StandardScaler` on train only. Seed Python, NumPy, and PyTorch with 42; call `torch.use_deterministic_algorithms(True)`. Use a `TensorDataset` and `DataLoader(batch_size=256, shuffle=True, num_workers=0, generator=seeded_generator)`. Build `Linear(input,64) -> ReLU -> Linear(64,16) -> ReLU -> Linear(16,64) -> ReLU -> Linear(64,input)`, train for the fixed epoch budget, and return evaluation-mode reconstruction errors.

- [ ] **Step 5: Run focused tests and quality checks**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_autoencoder.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m ruff check src\industrial_reliability\autoencoder.py tests\test_autoencoder.py
.\.venv\Scripts\python.exe -m mypy src\industrial_reliability\autoencoder.py
.\.venv\Scripts\python.exe -m pip check
```

Expected: PASS.

- [ ] **Step 6: Record the exact benchmark environment**

Run: `.\.venv\Scripts\python.exe -m pip freeze --exclude-editable | Sort-Object | Set-Content -Encoding ascii requirements-phase1.txt`

Expected: the file includes exact NumPy, pandas, PyArrow, scikit-learn, PyTorch, and test/build tool versions used by this branch. The benchmark manifest must also record Python, platform, and imported library versions.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml requirements-phase1.txt src/industrial_reliability/autoencoder.py tests/test_autoencoder.py
git commit -m "feat: add deterministic dense autoencoder"
```

### Task 7: Wire one reproducible benchmark command

**Files:**

- Create: `src/industrial_reliability/benchmark.py`
- Create: `tests/test_benchmark.py`

**Interfaces:**

- Command: `.\.venv\Scripts\python.exe -m industrial_reliability.benchmark --dataset data\raw\metropt\dataset_train.csv --work-dir data\interim\phase1 --artifact-dir artifacts\phase1`
- Produces `run_benchmark(dataset: Path, work_dir: Path, artifact_dir: Path, contract: Phase1Contract = PHASE1, autoencoder_epochs: int | None = None, require_clean_git: bool = True) -> BenchmarkResult` and `publish_aggregate_results(run_dir: Path, output_dir: Path) -> tuple[Path, Path]`.
- Produces one local run directory: `artifact_dir/run-{contract_sha12}-{git_sha12}/manifest.json`, `data_manifest.json`, `feature_manifest.json`, `scores.parquet`, `episodes.json`, `event_results.json`, `metrics.json`, and `limitations.md`.
- Consumes Tasks 1-6 only; no network, service, database, or reference-repository runtime.

`scores.parquet` columns are `window_start`, `window_end`, `split`, `model_id`, `raw_score`, `threshold`, and `is_anomaly`. `episodes.json` maps each model ID to `Episode` objects. `event_results.json` maps each model ID to its ordered `EventResult` objects. `metrics.json` maps each model ID to every `EvaluationResult` field plus `fit_seconds`, `score_seconds`, and model parameters.

`manifest.json` fields are `schema_version`, `run_id`, `dataset_sha256`, `contract_sha256`, `git_sha`, `tracked_tree_clean`, `python_version`, `platform`, `dependencies`, `split_bounds`, `window_seconds`, `stride_seconds`, `feature_columns`, `model_parameters`, `threshold_provenance`, `holdout_evaluations` (mapping each model ID to integer `1`), `artifact_sha256`, and `limitations`. `data_manifest.json` and `feature_manifest.json` are exact serializations of their Task 2/3 manifests, not competing summary formats.

The publisher reads only those hashed artifacts. Its committed JSON allowlist is `schema_version`, `dataset_sha256`, `contract_sha256`, `git_sha`, environment versions, split/window/feature identity, per-model parameters/thresholds/metrics/timings, valid/positive/anomalous window counts, normal-exposure days, event coverage/results, feasibility-gate booleans, selected model, limitations, and source artifact hashes. It rejects any unknown key that could carry raw rows, feature matrices, per-window scores, weights, or filesystem secrets, and generates Markdown from the same allowlisted object.

- [ ] **Step 1: Write a failing tiny end-to-end benchmark test**

```python
def test_benchmark_writes_complete_manifest(tmp_path: Path) -> None:
    timestamps = pd.date_range("2022-01-01 06:00:00", periods=7_200, freq="s")
    sample_csv = write_sample_csv(tmp_path / "benchmark.csv", timestamps)
    result = run_benchmark(
        dataset=sample_csv,
        work_dir=tmp_path / "work",
        artifact_dir=tmp_path / "artifacts",
        contract=sample_contract(sample_csv),
        autoencoder_epochs=1,
        require_clean_git=False,
    )
    assert set(result.metrics) == {"statistical", "isolation_forest", "autoencoder"}
    assert result.manifest["contract_sha256"]
    assert result.manifest["git_sha"]
    assert result.manifest["holdout_evaluations"] == {
        "statistical": 1,
        "isolation_forest": 1,
        "autoencoder": 1,
    }
```

`sample_contract()` must replace the real events with three synthetic minute-precision events inside its miniature holdout and leave enough earlier/later holdout decisions for nonzero normal exposure. Also assert identical classical metrics for two same-seed runs, no raw rows in JSON outputs, publisher allowlist enforcement, and failure before full execution when free disk is below 10 GiB (mock `shutil.disk_usage`). Use spies/monkeypatches to prove model `.fit()` receives only train rows, `calibrate_threshold()` receives only calibration scores, and changing holdout values cannot change fitted scaler parameters or thresholds.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_benchmark.py -q`

Expected: FAIL because `industrial_reliability.benchmark` does not exist.

- [ ] **Step 3: Implement orchestration and manifest provenance**

Use `argparse`, `pathlib`, `time.perf_counter`, `importlib.metadata.version`, `platform.platform`, `subprocess.run`, and SHA-256 artifact hashing. Before a real run, parse `git status --porcelain --untracked-files=all`: reject every tracked change and every untracked path except `.codex/` or descendants; standard Git-ignored work/artifact paths do not appear. Add tests proving an untracked `src/rogue.py` is rejected while `.codex/rules/local.md` is allowed. Fit each model once, calibrate once, evaluate holdout once, and emit the exact artifacts above. The runner must refuse hash mismatch, stale nonempty output directories, insufficient disk, missing train/calibration/holdout windows, or any full-run epoch override differing from the contract. Record installed dependency versions and the execution-tree cleanliness result.

- [ ] **Step 4: Add a slow full-data smoke marker without running it in normal CI**

```python
@pytest.mark.slow
def test_full_dataset_contract() -> None:
    source = Path("data/raw/metropt/dataset_train.csv")
    if not source.exists():
        pytest.skip("local MetroPT dataset unavailable")
    assert sha256_file(source) == PHASE1.dataset_sha256
```

- [ ] **Step 5: Run all non-slow local quality gates**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
```

Expected: all commands PASS and branch coverage remains at least 80%.

- [ ] **Step 6: Commit**

```powershell
git add src/industrial_reliability/benchmark.py tests/test_benchmark.py
git commit -m "feat: add reproducible Phase 1 benchmark"
```

### Task 8: Run the locked full benchmark and publish aggregate evidence

**Files:**

- Create: `docs/results/phase-1-offline-ml-feasibility.md`
- Create: `docs/results/phase-1-metrics.json`
- Modify: `README.md`

**Interfaces:**

- Consumes: the exact command and locked contract from Task 7.
- Produces: committed aggregate metrics/limitations only; local detailed artifacts remain ignored.

- [ ] **Step 1: Verify source identity and clean execution branch**

```powershell
Get-FileHash -Algorithm SHA256 data\raw\metropt\dataset_train.csv
git status --short --branch
git check-ignore data\raw\metropt\dataset_train.csv data\interim\phase1 artifacts\phase1
```

Expected hash: `3fd0788c1b8fb7753ac0a2047f487c87f59b8b36af2f5553e4990354ed86d168`; ignored local paths must remain untracked.

- [ ] **Step 2: Run the full-data contract check and locked benchmark once**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov -m slow -q
.\.venv\Scripts\python.exe -m industrial_reliability.benchmark --dataset data\raw\metropt\dataset_train.csv --work-dir data\interim\phase1 --artifact-dir artifacts\phase1 --publish-dir docs\results
```

Expected: one completed run containing all three model metrics and one holdout evaluation per model.

- [ ] **Step 3: Create aggregate result artifacts from the completed manifest**

The tested Task 7 publisher must create both files; do not hand-copy metric values. `docs/results/phase-1-metrics.json` must contain dataset/contract/code hashes, environment versions, split/window/feature identity, model parameters, thresholds, the five required metrics, valid/positive/anomalous decision counts, normal-exposure days, per-event coverage/results, feasibility gate results, selected model or `null`, runtimes, and source artifact hashes—never raw rows or weights.

`docs/results/phase-1-offline-ml-feasibility.md` must state `FEASIBLE` or `NOT FEASIBLE` strictly from the predeclared gate, compare all three models, explain whether added complexity helped, and disclose: one APU, three uncertain events, 152 gaps, unspecified timezone, unofficial local checksum, unknown canonical-release equivalence/license, paper/file row-count mismatch, Failure 2 LPS contradiction, Failure 3 count inconsistency/coverage, absence of physical causal proof, and the assumption that train/calibration contain no documented failures but are not independently proven healthy.

Update README status to the measured Phase 1 outcome and link the result report; do not claim production readiness.

- [ ] **Step 4: Run final local verification**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
git diff --check
git status --short
git ls-files data artifacts checkpoints
```

Expected: all quality gates PASS; the final `git ls-files` command returns no raw/derived/model artifacts; only intended source/tests/docs changes are present before the following staging step.

- [ ] **Step 5: Commit**

```powershell
git add docs/results/phase-1-offline-ml-feasibility.md docs/results/phase-1-metrics.json README.md
git commit -m "docs: publish Phase 1 feasibility evidence"
```

## Whole-Phase Review and Merge Gate

After Task 8, generate one whole-branch review package from the branch merge base. The final reviewer must verify spec compliance, source/data leakage controls, deterministic tests, raw-data exclusion, metric arithmetic, limitations, and absence of later-phase infrastructure. Fix Critical/Important findings through the SDD fix loop before integration.

Phase 1 is complete only when:

1. all eight task reviews are clean or explicitly adjudicated at the five-round cap;
2. the whole-branch review is clean;
3. every local quality command passes;
4. remote `CI / quality` succeeds on the implementation branch/PR;
5. aggregate metrics and a `FEASIBLE` or `NOT FEASIBLE` verdict are committed without changing the predeclared gate;
6. `.codex/`, raw data, Parquet, feature matrices, scores, weights, checkpoints, and reference code remain uncommitted;
7. Phase 2 does not begin until its own design and implementation plan use the measured Phase 1 result.
