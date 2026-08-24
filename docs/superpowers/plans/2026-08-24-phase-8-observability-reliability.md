# Phase 8 Observability and Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add measurable service, data-quality, model, and machine-condition observability plus repeatable fault drills that prove an operator can tell those conditions apart.

**Architecture:** Each existing runtime process exposes a small shared Prometheus metric vocabulary; Prometheus scrapes the processes and Grafana provisions three focused dashboards. A train-only drift profile supplies an indicator, never a failure label. A real-dependency drill runner injects one service outage, one malformed telemetry record, and one known abnormal replay and publishes an allowlisted exact-SHA result.

**Tech Stack:** Python 3.12, FastAPI, prometheus-client, NumPy, Kafka, PostgreSQL, Prometheus, Grafana, Docker Compose, pytest, PowerShell.

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Start only after Phases 1B-7 have passed and the Phase 7 `champion` alias resolves to the same `model_version`, `contract_sha256`, and `source_dataset_sha256` as `artifacts/champion/manifest.json`.
- Preserve Kafka at-least-once delivery; metrics and dashboards must never describe the system as exactly-once.
- Prometheus labels are bounded enums or dependency names; never use message, replay, window, decision, alert, machine, or feature IDs as labels.
- The drift reference is built from train features only. Calibration, holdout, replay outcomes, alerts, and `lps` never influence its bins or thresholds.
- Drift is an operating-distribution indicator, not a machine-failure conclusion. An anomaly decision remains the champion model's decision and an alert remains the locked Phase 5 policy's output.
- Raw telemetry, feature matrices, per-window scores, credentials, and full Prometheus data remain local and git-ignored. Only aggregate drill results and configuration are committed.
- Runtime ports published by Compose bind to `127.0.0.1`; container-internal metric listeners may bind to `0.0.0.0` only for the private Compose network.
- Use `.\.venv\Scripts\python.exe` on Windows. Every task follows RED-GREEN-REFACTOR, preserves at least 80% branch coverage, and ends in one logical conventional commit.
- Final phase checks are `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -m "not slow"`, `pip check`, and `python -m build` through the project venv.

---

### Task 1: Define and instrument the bounded runtime metric contract

**Files:**
- Modify: `pyproject.toml`
- Create: `src/industrial_reliability/metrics.py`
- Modify: `src/industrial_reliability/api.py`
- Modify: `src/industrial_reliability/replay.py`
- Modify: `src/industrial_reliability/worker.py`
- Create: `tests/test_metrics.py`

**Interfaces:**
- Consumes: Phase 2 `POST /v1/score`; Phase 3 replay producer; Phase 4 worker loops and `ScoreDecisionV1`; Phase 5 alert transitions and replay failure states.
- Produces: immutable `RuntimeMetrics`, `build_runtime_metrics(registry: CollectorRegistry) -> RuntimeMetrics`, `mount_api_metrics(app: FastAPI, metrics: RuntimeMetrics) -> None`, and `start_process_metrics(port: int, registry: CollectorRegistry) -> HTTPServer`.
- Produces these exact metric families: `irp_dependency_ready{dependency}`, `irp_replay_session_failures_total{error_code}`, `irp_kafka_consumer_lag`, `irp_telemetry_events_total{outcome}`, `irp_segment_breaks_total{reason}`, `irp_valid_windows_total`, `irp_window_coverage_ratio`, `irp_score_requests_total{outcome}`, `irp_score_latency_seconds`, `irp_anomaly_score`, `irp_anomaly_decisions_total`, `irp_alert_events_total{action}`, `irp_alerts_active`, and `irp_feature_psi_max`.

- [ ] **Step 1: Add the failing metric-contract tests**

```python
from prometheus_client import CollectorRegistry, generate_latest

from industrial_reliability.metrics import build_runtime_metrics


def test_metric_contract_has_only_bounded_labels() -> None:
    registry = CollectorRegistry()
    metrics = build_runtime_metrics(registry)
    metrics.telemetry_events.labels(outcome="quarantined").inc()
    metrics.segment_breaks.labels(reason="gap").inc()
    metrics.dependency_ready.labels(dependency="postgres").set(0)

    text = generate_latest(registry).decode()
    assert 'irp_telemetry_events_total{outcome="quarantined"} 1.0' in text
    assert 'irp_segment_breaks_total{reason="gap"} 1.0' in text
    assert 'irp_dependency_ready{dependency="postgres"} 0.0' in text
    assert "replay_session_id=" not in text
    assert "alert_id=" not in text


def test_metric_contract_rejects_unknown_enum_values() -> None:
    metrics = build_runtime_metrics(CollectorRegistry())
    try:
        metrics.record_telemetry("made-up")
    except ValueError as exc:
        assert str(exc) == "unsupported telemetry outcome: made-up"
    else:
        raise AssertionError("unknown label value was accepted")
```

- [ ] **Step 2: Run the focused test and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_metrics.py -q`

Expected: FAIL because `industrial_reliability.metrics` does not exist.

- [ ] **Step 3: Add the direct dependency and minimal immutable wrapper**

Add `prometheus-client>=0.22,<1` to project dependencies. Implement `RuntimeMetrics` as a frozen dataclass containing Prometheus collectors plus small validated methods. Use these exact bounded values:

```python
TELEMETRY_OUTCOMES = frozenset({"accepted", "duplicate", "quarantined"})
SEGMENT_BREAK_REASONS = frozenset({"gap", "ordering"})
SCORE_OUTCOMES = frozenset({"ok", "invalid_contract", "invalid_model", "unavailable"})
ALERT_ACTIONS = frozenset({"opened", "updated", "resolved", "reopened"})


def _require(value: str, allowed: frozenset[str], kind: str) -> str:
    if value not in allowed:
        raise ValueError(f"unsupported {kind}: {value}")
    return value
```

Create collectors with the exact names in **Interfaces** and inject a `CollectorRegistry`; do not use the global registry in unit tests.

- [ ] **Step 4: Instrument existing success and failure boundaries once**

Mount a registry-backed `/metrics` ASGI app in `api.py`. In `replay.py`, increment accepted/quarantined/duplicate events and set producer dependency readiness. In `worker.py`, record gap/order segment breaks, valid windows, coverage, scoring duration/outcome, anomaly decisions, alert actions, consumer lag, and exhausted session failures at the shared code paths used by every caller.

Use a monotonic timer around scoring:

```python
started = time.perf_counter()
try:
    decision = scoring_client.score(feature_vector)
except ScoringUnavailable:
    metrics.score_requests.labels(outcome="unavailable").inc()
    raise
else:
    metrics.score_requests.labels(outcome="ok").inc()
    return decision
finally:
    metrics.score_latency.observe(time.perf_counter() - started)
```

Start replay and worker metric servers from existing process entrypoints using `METRICS_PORT`; Compose will set `9101` and `9102`. Do not add another process supervisor.

- [ ] **Step 5: Prove instrumentation does not alter durable behavior**

Extend `tests/test_metrics.py` with the existing fake repository/client fixtures. Assert a duplicate increments `outcome="duplicate"` while leaving stored decisions unchanged, and a scoring outage increments `outcome="unavailable"` while leaving the Kafka offset uncommitted.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_metrics.py tests\test_worker.py tests\test_replay.py -q
.\.venv\Scripts\python.exe -m ruff check src\industrial_reliability\metrics.py tests\test_metrics.py
.\.venv\Scripts\python.exe -m mypy src\industrial_reliability\metrics.py
```

Expected: PASS; the pre-existing idempotence and offset assertions remain unchanged.

- [ ] **Step 6: Commit the metric contract**

```powershell
git add pyproject.toml src/industrial_reliability/metrics.py src/industrial_reliability/api.py src/industrial_reliability/replay.py src/industrial_reliability/worker.py tests/test_metrics.py tests/test_worker.py tests/test_replay.py
git commit -m "feat: instrument bounded runtime metrics"
```

### Task 2: Build a train-only drift reference and pure PSI indicator

**Files:**
- Create: `src/industrial_reliability/drift.py`
- Create: `tests/test_drift.py`

**Interfaces:**
- Consumes: Phase 1B train feature Parquet plus `artifacts/champion/manifest.json`; hashes must match the serving champion.
- Produces: immutable `DriftReferenceV1`, `build_reference(train_features: np.ndarray, feature_names: tuple[str, ...], bins: int = 10) -> DriftReferenceV1`, `save_reference(reference: DriftReferenceV1, path: Path) -> str`, `load_reference(path: Path, expected_contract_sha256: str) -> DriftReferenceV1`, and `max_population_stability_index(reference: DriftReferenceV1, recent_features: np.ndarray) -> float`.
- Produces local `artifacts/phase8/drift-reference.json`; the document contains aggregate bin edges/proportions, contract/data/champion hashes, and the literal source split `train`, never rows.

- [ ] **Step 1: Write failing leakage, hash, and arithmetic tests**

```python
import numpy as np
import pytest

from industrial_reliability.drift import build_reference, load_reference, max_population_stability_index, save_reference


def test_reference_is_train_only_and_hash_checked(tmp_path) -> None:
    reference = build_reference(
        np.array([[0.0], [1.0], [2.0], [3.0]], dtype=np.float64),
        ("tp2_mean",),
        bins=2,
    )
    assert reference.source_split == "train"
    path = tmp_path / "reference.json"
    digest = save_reference(reference, path)
    assert len(digest) == 64
    with pytest.raises(ValueError, match="contract hash mismatch"):
        load_reference(path, expected_contract_sha256="0" * 64)


def test_psi_is_zero_for_reference_shape_and_positive_for_shift() -> None:
    train = np.arange(100, dtype=np.float64).reshape(-1, 1)
    reference = build_reference(train, ("tp2_mean",), bins=10)
    assert max_population_stability_index(reference, train) < 1e-12
    shifted = np.arange(100, 200, dtype=np.float64).reshape(-1, 1)
    assert max_population_stability_index(reference, shifted) > 0.2
```

- [ ] **Step 2: Run the focused test and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_drift.py -q`

Expected: FAIL because `industrial_reliability.drift` does not exist.

- [ ] **Step 3: Implement the smallest stable histogram calculation**

Use `np.quantile(column, np.linspace(0, 1, bins + 1), method="linear")`, collapse duplicate internal edges, and add `-inf`/`inf` outer edges. Reject non-finite inputs, empty matrices, name/column mismatches, fewer than two distinct edges, any source split other than the hard-coded `train`, and contract/data/champion hash mismatches. Compute PSI with epsilon `1e-6`:

```python
def _psi(expected: np.ndarray, actual: np.ndarray) -> float:
    left = np.clip(expected, 1e-6, None)
    right = np.clip(actual, 1e-6, None)
    return float(np.sum((right - left) * np.log(right / left)))
```

Canonicalize JSON with `sort_keys=True`, separators `(",", ":")`, UTF-8, and SHA-256. Return the maximum per-feature PSI for the metric; retain per-feature values only in process memory and local Prometheus samples.

- [ ] **Step 4: Add the reference-builder CLI and worker update**

Add `python -m industrial_reliability.drift build-reference --train-features <path> --champion-manifest artifacts/champion/manifest.json --output artifacts/phase8/drift-reference.json`. The command must read the train partition recorded by Phase 1B, refuse calibration/holdout paths and mismatched hashes, and print only output path plus digest.

Load the reference once in `worker.py`; every 12 valid five-minute feature vectors compute PSI, set `irp_feature_psi_max`, and reset the 12-vector tuple after a gap/order segment break. The dashboard labels `PSI >= 0.2` as `distribution shift indicator`, never `failure`.

- [ ] **Step 5: Run focused and full non-slow checks**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_drift.py tests\test_worker.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m ruff check src\industrial_reliability\drift.py tests\test_drift.py
.\.venv\Scripts\python.exe -m mypy src\industrial_reliability\drift.py
```

Expected: PASS with branch coverage at least 80%; tests prove a gap clears the recent PSI window.

- [ ] **Step 6: Commit the drift indicator**

```powershell
git add src/industrial_reliability/drift.py src/industrial_reliability/worker.py tests/test_drift.py tests/test_worker.py
git commit -m "feat: add train-only drift indicator"
```

### Task 3: Provision three minimal operator dashboards

**Files:**
- Modify: `compose.yaml`
- Create: `ops/prometheus/prometheus.yml`
- Create: `ops/grafana/provisioning/datasources/prometheus.yml`
- Create: `ops/grafana/provisioning/dashboards/dashboards.yml`
- Create: `ops/grafana/dashboards/system.json`
- Create: `ops/grafana/dashboards/data-quality.json`
- Create: `ops/grafana/dashboards/model-machine.json`
- Create: `tests/test_observability_config.py`

**Interfaces:**
- Consumes: Task 1 metric names and private Compose DNS names `scoring-api`, `replay-producer`, and `streaming-worker`.
- Produces: Prometheus at `http://127.0.0.1:9090`, Grafana at `http://127.0.0.1:3001`, and provisioned dashboard UIDs `irp-system`, `irp-data-quality`, and `irp-model-machine`.

- [ ] **Step 1: Write a failing provisioning contract test**

```python
import json
from pathlib import Path


def test_dashboards_are_provisioned_and_keep_conditions_separate() -> None:
    root = Path("ops/grafana/dashboards")
    dashboards = {json.loads(path.read_text(encoding="utf-8"))["uid"]: path.read_text() for path in root.glob("*.json")}
    assert set(dashboards) == {"irp-system", "irp-data-quality", "irp-model-machine"}
    assert "irp_dependency_ready" in dashboards["irp-system"]
    assert "irp_telemetry_events_total" in dashboards["irp-data-quality"]
    assert "irp_feature_psi_max" in dashboards["irp-model-machine"]
    assert "Drift is not a failure diagnosis" in dashboards["irp-model-machine"]


def test_prometheus_scrapes_every_runtime_process() -> None:
    config = Path("ops/prometheus/prometheus.yml").read_text(encoding="utf-8")
    assert "scoring-api:8000" in config
    assert "replay-producer:9101" in config
    assert "streaming-worker:9102" in config
```

- [ ] **Step 2: Run the focused test and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_observability_config.py -q`

Expected: FAIL because the provisioning files do not exist.

- [ ] **Step 3: Add private scrape targets and pinned monitoring services**

Use this scrape layout:

```yaml
global:
  scrape_interval: 5s
scrape_configs:
  - job_name: scoring-api
    static_configs: [{targets: ["scoring-api:8000"]}]
  - job_name: replay-producer
    static_configs: [{targets: ["replay-producer:9101"]}]
  - job_name: streaming-worker
    static_configs: [{targets: ["streaming-worker:9102"]}]
```

Add pinned Prometheus and Grafana image tags to Compose, read-only config mounts, named data volumes, health checks, and host bindings `127.0.0.1:9090:9090` and `127.0.0.1:3001:3000`. Set local demo-only Grafana credentials through `.env`; do not commit a password or enable anonymous admin access.

- [ ] **Step 4: Create dashboards with exact condition panels**

The system dashboard must contain dependency readiness, consumer lag, p95 scoring latency, and exhausted session failures. The data-quality dashboard must contain quarantine rate, duplicates, gap/order breaks, valid windows, and window coverage. The model/machine dashboard must contain anomaly score versus threshold, anomaly decision rate, active alerts, alert lifecycle counts, and max PSI with the text `Drift is not a failure diagnosis`.

Use these PromQL expressions verbatim where applicable:

```text
min by (dependency) (irp_dependency_ready)
histogram_quantile(0.95, sum by (le) (rate(irp_score_latency_seconds_bucket[5m])))
sum by (outcome) (rate(irp_telemetry_events_total[5m]))
sum by (reason) (increase(irp_segment_breaks_total[15m]))
max(irp_feature_psi_max)
sum(irp_alerts_active)
```

- [ ] **Step 5: Validate provisioning and a live scrape**

```powershell
.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_observability_config.py -q
docker compose config --quiet
docker compose up -d --build scoring-api replay-producer streaming-worker prometheus grafana
Invoke-RestMethod http://127.0.0.1:9090/-/ready
Invoke-RestMethod http://127.0.0.1:3001/api/health
Invoke-RestMethod 'http://127.0.0.1:9090/api/v1/query?query=up'
```

Expected: tests and Compose validation PASS; both health requests report ready/healthy; Prometheus returns successful samples for all three runtime jobs.

- [ ] **Step 6: Commit provisioning**

```powershell
git add compose.yaml ops/prometheus/prometheus.yml ops/grafana/provisioning ops/grafana/dashboards tests/test_observability_config.py
git commit -m "feat: provision reliability dashboards"
```

### Task 4: Certify service, data, and machine fault distinctions

**Files:**
- Create: `src/industrial_reliability/fault_report.py`
- Create: `scripts/run_phase8_fault_drills.ps1`
- Create: `tests/test_fault_report.py`
- Create: `tests/integration/test_phase8_fault_drills.py`
- Create: `docs/results/phase-8-observability-reliability.json`
- Create: `docs/results/phase-8-observability-reliability.md`

**Interfaces:**
- Consumes: Compose runtime, Prometheus query API, Phase 3 quarantine topic, Phase 5 replay/session/alert APIs, and a Phase 1B holdout range known to produce an alert under the champion and locked policy.
- Produces: immutable `DrillResultV1`, `classify_drill(metrics: Mapping[str, float]) -> Literal["SERVICE", "DATA", "MACHINE"]`, and `publish_drill_report(results: tuple[DrillResultV1, ...], git_sha: str, output_dir: Path) -> tuple[Path, Path]`.
- Produces exactly three drill IDs: `scoring-outage`, `malformed-telemetry`, and `known-abnormal-replay`.

- [ ] **Step 1: Write failing classification and publisher tests**

```python
from industrial_reliability.fault_report import classify_drill


def test_fault_classes_are_mutually_exclusive() -> None:
    assert classify_drill({"dependency_ready": 0, "quarantined": 0, "alerts": 0}) == "SERVICE"
    assert classify_drill({"dependency_ready": 1, "quarantined": 1, "alerts": 0}) == "DATA"
    assert classify_drill({"dependency_ready": 1, "quarantined": 0, "alerts": 1}) == "MACHINE"


def test_ambiguous_fault_snapshot_is_rejected() -> None:
    try:
        classify_drill({"dependency_ready": 0, "quarantined": 1, "alerts": 0})
    except ValueError as exc:
        assert str(exc) == "drill snapshot is not isolated"
    else:
        raise AssertionError("ambiguous drill snapshot was accepted")
```

Also test that `publish_drill_report` accepts only the three IDs, requires a 40-character Git SHA, excludes raw series/IDs/secrets, hashes canonical JSON, and renders Markdown from that JSON.

- [ ] **Step 2: Run the focused test and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_fault_report.py -q`

Expected: FAIL because `industrial_reliability.fault_report` does not exist.

- [ ] **Step 3: Implement strict drill result validation and publishing**

`DrillResultV1` fields are `drill_id`, `expected_class`, `observed_class`, `started_at`, `finished_at`, `duration_seconds`, `assertions`, and `metric_deltas`. Permit only aggregate numeric deltas for metric names listed in Task 1. The report top level includes `schema_version="phase8-fault-drills-v1"`, `git_sha`, champion/data/contract hashes, Compose image names, the three results, and `passed = all(result.expected_class == result.observed_class and all(result.assertions.values()))`.

- [ ] **Step 4: Build the real-dependency drill runner**

`scripts/run_phase8_fault_drills.ps1` must require a clean tracked tree and exact champion/drift artifacts, bring up the stack, reset only the named drill replay sessions, capture Prometheus baselines, and execute these drills sequentially:

1. `scoring-outage`: pause `scoring-api`, start a bounded replay, verify bounded retries are visible, the consumer offset does not advance for the failed decision, the session becomes `FAILED` with the existing scoring-unavailable error, and no alert is created; unpause and wait for readiness before continuing.
2. `malformed-telemetry`: publish one invalid-schema record through the existing test producer, verify exactly one new quarantine record/reason, no score/alert is produced for its message ID, and service readiness remains one.
3. `known-abnormal-replay`: replay the pre-recorded Phase 1B alert-producing range at `1000x`, verify no new service/data error, at least one anomaly decision and one persisted alert, and the alert detail contains decision/evidence provenance.

The script writes raw query responses only below git-ignored `artifacts/certification/phase-8/<git-sha>/`, then calls the tested publisher for the two committed aggregate files.

- [ ] **Step 5: Run integration drills and verify measurable exit criteria**

```powershell
.\scripts\run_phase8_fault_drills.ps1
.\.venv\Scripts\python.exe -m pytest --no-cov tests\integration\test_phase8_fault_drills.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
```

Expected: the report contains all three isolated observed classes in order, every assertion is true, `passed` is true, the outage offset delta is zero, quarantine delta is exactly one, known-replay alert delta is at least one, and the local evidence directory is ignored by Git.

- [ ] **Step 6: Run the full phase gate**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
git diff --check
git check-ignore artifacts/certification/phase-8 artifacts/phase8/drift-reference.json
```

Expected: every command PASS, branch coverage is at least 80%, both local artifact paths are ignored, and the aggregate report names the exact tested Git SHA and champion/data/contract hashes.

- [ ] **Step 7: Commit Phase 8 certification evidence**

```powershell
git add src/industrial_reliability/fault_report.py scripts/run_phase8_fault_drills.ps1 tests/test_fault_report.py tests/integration/test_phase8_fault_drills.py docs/results/phase-8-observability-reliability.json docs/results/phase-8-observability-reliability.md
git commit -m "test: certify observable fault distinctions"
```

## Phase 8 Exit Gate

Phase 8 passes only when the exact-SHA aggregate report records all three drills as isolated and passing, Prometheus scrapes every runtime process, Grafana provisions the system/data/model-machine views, drift state is derived from a train-only hashed profile, and the known abnormal replay remains traceable from replay to decision to alert. A synthetic unit pass or dashboard file presence alone is not certification.
