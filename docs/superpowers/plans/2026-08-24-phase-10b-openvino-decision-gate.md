# Phase 10B OpenVINO Decision Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide `ADOPTED`, `NOT_ADOPTED`, or `N/A` for OpenVINO from champion applicability, score/decision/event parity, CPU latency/throughput, memory, and artifact-size evidence.

**Architecture:** A dependency-free gate reads the integrity-checked champion first; a statistical or Isolation Forest champion ends `N/A` without OpenVINO installation. For an autoencoder champion, benchmark the existing PyTorch scorer on one frozen workload, then authorize an isolated FP32 OpenVINO conversion and compare it under the same process/thread conditions. Only a parity-safe material improvement changes the default scoring API; the fixed small dense model gets a measured quantization decision without speculative INT8 infrastructure.

**Tech Stack:** Python 3.12, NumPy, PyTorch CPU, psutil benchmark sampling, existing champion/scoring API, optional isolated OpenVINO 2025.4.0, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Run after Phase 10A records its terminal decision and Phase 9 still passes on the default runtime.
- Read and hash-verify `artifacts/champion/manifest.json` before deserializing `detector.joblib`. `model_id` is one of `statistical`, `isolation_forest`, or `autoencoder`.
- If Phase 1B is not feasible, the champion is null, or `model_id != "autoencoder"`, publish `N/A` and do not install/import/download OpenVINO or create conversion files.
- Do not add OpenVINO to `pyproject.toml`, Docker, Compose, or the default venv before a local authorization artifact records `EVALUATE_OPENVINO` for the exact Git/champion/contract/data hashes.
- The exact candidate pin `openvino==2025.4.0` was not live-verified while planning because browser-act was unavailable. Installation failure is fail-closed `NOT_ADOPTED`; never repin during execution without a reviewed plan change.
- Freeze both runtimes to batch size 1, one CPU inference thread, 100 warmups, the earliest 10,000 valid Phase 1B holdout feature vectors in source order, and five measured repetitions. The workload is performance evidence only; it never changes transforms, weights, threshold, alert policy, or champion selection.
- Adoption requires score tolerance, exact anomaly decisions, unchanged event/alert metrics, and measured benefit. A conversion/runtime error is not a reason to weaken parity thresholds.
- Candidate XML/BIN, feature inputs, per-sample timings, scores, and environment captures remain git-ignored under `artifacts/phase10b/`. Commit only aggregate decisions/hashes and limitations.
- Quantization is a secondary evidence gate. The fixed `[input,64,16,64,input]` champion is not quantized unless its measured FP32 model artifact exceeds 32 MiB; a smaller artifact records `N/A` for INT8 and adds no NNCF dependency.
- Do not add a provider/factory/engine registry or a runtime toggle. If adopted, the API directly loads the verified OpenVINO scorer; otherwise the existing champion loader is unchanged.
- Use `.\.venv\Scripts\python.exe` for baseline/project checks and `.\.venv-openvino\Scripts\python.exe` only after authorization. Every implementation task follows RED-GREEN-REFACTOR and keeps at least 80% branch coverage for project code.

---

### Task 1: Gate applicability and benchmark the current PyTorch scorer first

**Files:**
- Modify: `pyproject.toml`
- Create: `src/industrial_reliability/inference_benchmark.py`
- Create: `src/industrial_reliability/phase10b_gate.py`
- Create: `tests/test_inference_benchmark.py`
- Create: `tests/test_phase10b_gate.py`

**Interfaces:**
- Consumes: Phase 1B result, Phase 2 `ChampionManifest` and integrity loader, Phase 2 golden cases, ordered Phase 1B holdout feature artifact, and Phase 1B event metrics.
- Produces: frozen `InferenceBenchmarkResultV1`, `OpenVinoDecisionV1`, `applicability(manifest) -> Literal["N/A", "EVALUATE_OPENVINO"]`, CLI `.\.venv\Scripts\python.exe -m industrial_reliability.inference_benchmark`, and local `artifacts/phase10b/openvino-authorization.json`.
- `InferenceBenchmarkResultV1` fields are `runtime`, `git_sha`, `champion_manifest_sha256`, `detector_sha256`, `contract_sha256`, `source_dataset_sha256`, `workload_sha256`, `sample_count`, `warmup_count`, `repetitions`, `batch_size`, `cpu_threads`, `score_digest`, `decision_digest`, `event_metrics`, `max_abs_score_error`, `max_rel_score_error`, `p50_latency_ms`, `p95_latency_ms`, `throughput_samples_per_second`, `peak_rss_bytes`, and `model_artifact_bytes`.

- [ ] **Step 1: Write failing applicability and benchmark-schema tests**

```python
@pytest.mark.parametrize("model_id", ["statistical", "isolation_forest"])
def test_classical_champion_is_na_without_candidate(model_id: str) -> None:
    decision = decide_applicability(champion_manifest(model_id=model_id))
    assert decision.status == "N/A"
    assert decision.reason_codes == ("NON_PYTORCH_CHAMPION",)
    assert decision.candidate is None


def test_autoencoder_authorizes_evaluation_without_adoption() -> None:
    authorization = decide_applicability(champion_manifest(model_id="autoencoder"))
    assert authorization.action == "EVALUATE_OPENVINO"
    assert authorization.champion_manifest_sha256 == "a" * 64


def test_inference_benchmark_rejects_non_finite_or_wrong_workload() -> None:
    with pytest.raises(ValueError, match="sample_count"):
        benchmark_fixture(sample_count=9_999)
    with pytest.raises(ValueError, match="latency"):
        benchmark_fixture(p95_latency_ms=float("nan"))
```

- [ ] **Step 2: Run focused tests and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_inference_benchmark.py tests\test_phase10b_gate.py -q`

Expected: FAIL because the benchmark and gate modules do not exist.

- [ ] **Step 3: Implement immutable benchmark and decision records**

Add `psutil>=7,<8` to the `dev` optional dependencies so both PyTorch and OpenVINO benchmark processes use the same cross-platform process-memory sampler; it is benchmark/test tooling, not an inference runtime dependency.

```python
@dataclass(frozen=True)
class OpenVinoDecisionV1:
    schema_version: str
    status: Literal["ADOPTED", "NOT_ADOPTED", "N/A"]
    git_sha: str
    champion_manifest_sha256: str | None
    contract_sha256: str | None
    source_dataset_sha256: str | None
    reason_codes: tuple[str, ...]
    baseline: InferenceBenchmarkResultV1 | None
    candidate: InferenceBenchmarkResultV1 | None
    score_parity_passed: bool | None
    decision_parity_passed: bool | None
    event_parity_passed: bool | None
    benefit_passed: bool | None
    quantization_status: Literal["N/A", "NOT_ADOPTED"]
    limitations: tuple[str, ...]
    decision_sha256: str = ""
```

Reuse only `canonical_sha256` from Phase 10A. Validate exact hashes, finite non-negative metrics, five repetitions, batch/thread/warmup/sample literals, and status-dependent evidence. A terminal `ADOPTED` requires both results and all four booleans true.

- [ ] **Step 4: Build the frozen input workload without optional imports**

The CLI verifies the champion package, reads the earliest 10,000 holdout feature rows in `(window_end, window_id)` order, confirms exact feature names and hashes, writes only the workload manifest/hash locally, warms 100 calls, then measures five one-thread batch-1 repetitions through the existing `ChampionScorer`. Set `torch.set_num_threads(1)` and `torch.set_num_interop_threads(1)` before warmup. Use `time.perf_counter_ns()` and sample `psutil.Process(os.getpid()).memory_info().rss` every 10 ms in a background thread for both runtimes; subtract the pre-load RSS and record the maximum non-negative delta.

- [ ] **Step 5: Run applicability before candidate installation**

```powershell
git status --short --branch
git check-ignore artifacts/phase10b
.\.venv\Scripts\python.exe -m industrial_reliability.phase10b_gate authorize --phase1b-result docs\results\phase-1b-metrics.json --champion artifacts\champion\manifest.json --output artifacts\phase10b\openvino-authorization.json
```

Expected: `N/A` for no/classical champion, or `EVALUATE_OPENVINO` for `autoencoder`. For `N/A`, render both committed result files, skip Tasks 2-4, and continue at Task 5. No OpenVINO package/environment/file exists at this point.

- [ ] **Step 6: For an authorized autoencoder, run the PyTorch baseline**

```powershell
.\.venv\Scripts\python.exe -m industrial_reliability.inference_benchmark --runtime pytorch --champion artifacts\champion --features data\processed\phase1b\features.parquet --sample-count 10000 --warmup-count 100 --repetitions 5 --batch-size 1 --cpu-threads 1 --output artifacts\phase10b\baseline
```

Expected: the benchmark hashes the exact workload, matches all Phase 2 golden cases at absolute tolerance `1e-12`, and records the baseline without changing the model or package.

- [ ] **Step 7: Commit only applicability/baseline tooling**

```powershell
git add pyproject.toml src/industrial_reliability/inference_benchmark.py src/industrial_reliability/phase10b_gate.py tests/test_inference_benchmark.py tests/test_phase10b_gate.py
git commit -m "test: gate OpenVINO applicability"
```

### Task 2: Convert an authorized autoencoder in an isolated environment

**Files:**
- Create: `requirements-phase10b-openvino.txt`
- Modify: `src/industrial_reliability/autoencoder.py`
- Modify: `tests/test_autoencoder.py`
- Create: `benchmarks/openvino_candidate.py`
- Create: `tests/optional/test_openvino_candidate.py`

**Interfaces:**
- Consumes: exact authorization artifact, verified autoencoder detector, public scaler mean/scale, fixed network state, and Task 1 workload.
- Produces: `DenseAutoencoderDetector.inference_module() -> torch.nn.Module`, `convert_candidate(detector, example, output_dir) -> OptimizedArtifactV1`, and local `artifacts/phase10b/candidate/{model.xml,model.bin,manifest.json}`.

- [ ] **Step 1: Revalidate authorization before creating the optional venv**

```powershell
.\.venv\Scripts\python.exe -m industrial_reliability.phase10b_gate verify-authorization --authorization artifacts\phase10b\openvino-authorization.json --expected-git-sha (git rev-parse HEAD) --champion artifacts\champion\manifest.json
```

Expected: prints `EVALUATE_OPENVINO authorized`; stale Git/champion/contract/data hashes exit nonzero before environment creation.

- [ ] **Step 2: Write the PyTorch export-module parity test**

```python
def test_inference_module_matches_detector_score() -> None:
    detector = fitted_autoencoder_fixture()
    values = feature_fixture(rows=32)
    module = detector.inference_module().eval()
    with torch.no_grad():
        actual = module(torch.from_numpy(values).float()).numpy()
    np.testing.assert_allclose(actual, detector.score(values), rtol=0.0, atol=1e-7)
```

- [ ] **Step 3: Create the isolated exact environment and observe candidate RED**

`requirements-phase10b-openvino.txt` contains exactly:

```text
openvino==2025.4.0
```

Run:

```powershell
py -3.12 -m venv .venv-openvino
.\.venv-openvino\Scripts\python.exe -m pip install -e ".[dev]" -r requirements-phase10b-openvino.txt
.\.venv-openvino\Scripts\python.exe -m pytest --no-cov tests\optional\test_openvino_candidate.py -q
```

Expected: FAIL because `benchmarks.openvino_candidate` does not exist. If the exact pinned package is unavailable for Python 3.12, record the installation failure and produce `NOT_ADOPTED` with `CANDIDATE_ENVIRONMENT_UNAVAILABLE`; do not change the pin during execution.

- [ ] **Step 4: Implement the immutable PyTorch scoring module**

Return a new evaluation-mode module that registers copied scaler mean/scale as buffers, runs the copied dense network, and returns per-row mean squared reconstruction error. Do not expose training, mutate the detector, or refit a scaler.

- [ ] **Step 5: Convert FP32 and hash both runtime files**

```python
module = detector.inference_module().eval()
example = torch.zeros((1, len(manifest.feature_names)), dtype=torch.float32)
ov_model = openvino.convert_model(module, example_input=example)
openvino.save_model(ov_model, output_dir / "model.xml", compress_to_fp16=False)
compiled = openvino.Core().compile_model(
    output_dir / "model.xml",
    "CPU",
    {"INFERENCE_NUM_THREADS": "1"},
)
```

The candidate manifest records source champion/detector hashes, OpenVINO/PyTorch/Python/platform versions, input order/shape/dtype, XML/BIN SHA-256, conversion settings, and its own canonical SHA-256. It contains no weights inline.

- [ ] **Step 6: Run conversion and focused parity tests**

```powershell
.\.venv-openvino\Scripts\python.exe -m benchmarks.openvino_candidate --champion artifacts\champion --output artifacts\phase10b\candidate
.\.venv-openvino\Scripts\python.exe -m pytest --no-cov tests\optional\test_openvino_candidate.py tests\test_autoencoder.py -q
.\.venv\Scripts\python.exe -m pytest -m "not slow"
```

Expected: the export module matches PyTorch at `1e-7`; XML/BIN hashes verify before compilation; candidate outputs have shape `(batch,)` and finite values.

- [ ] **Step 7: Commit isolated conversion support**

```powershell
git add requirements-phase10b-openvino.txt src/industrial_reliability/autoencoder.py tests/test_autoencoder.py benchmarks/openvino_candidate.py tests/optional/test_openvino_candidate.py
git commit -m "perf: add isolated OpenVINO candidate"
```

### Task 3: Compare score, decision, event, performance, and resource evidence

**Files:**
- Modify: `src/industrial_reliability/phase10b_gate.py`
- Modify: `tests/test_phase10b_gate.py`
- Create: `tests/integration/test_openvino_parity.py`

**Interfaces:**
- Consumes: same-workload PyTorch/OpenVINO `InferenceBenchmarkResultV1`, all three golden cases, full Phase 1B holdout scores/event metrics, threshold, and XML/BIN manifest.
- Produces: `compare_openvino(baseline, candidate) -> OpenVinoDecisionV1` with terminal `ADOPTED` or `NOT_ADOPTED`.

- [ ] **Step 1: Write failing parity and benefit tests**

```python
def test_material_safe_improvement_is_adopted() -> None:
    decision = compare_openvino(
        baseline_fixture(p95_latency_ms=2.0, throughput_samples_per_second=500),
        candidate_fixture(p95_latency_ms=1.5, throughput_samples_per_second=700),
    )
    assert decision.status == "ADOPTED"


def test_decision_flip_blocks_adoption_even_when_faster() -> None:
    candidate = candidate_fixture(p95_latency_ms=0.5, decision_digest="0" * 64)
    decision = compare_openvino(baseline_fixture(), candidate)
    assert decision.status == "NOT_ADOPTED"
    assert "DECISION_PARITY_FAILED" in decision.reason_codes


def test_small_speedup_or_memory_growth_is_not_adopted() -> None:
    decision = compare_openvino(
        baseline_fixture(p95_latency_ms=2.0, peak_rss_bytes=100_000_000),
        candidate_fixture(p95_latency_ms=1.9, peak_rss_bytes=130_000_000),
    )
    assert decision.status == "NOT_ADOPTED"
```

- [ ] **Step 2: Run comparison tests and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_phase10b_gate.py -q`

Expected: FAIL because comparative rules are absent.

- [ ] **Step 3: Implement predeclared conversion gates**

Score parity requires maximum absolute error at most `1e-5` and maximum relative error at most `1e-4` over golden plus full holdout scores. Decision parity requires identical ordered anomaly booleans at the locked inclusive threshold. Event parity requires identical event detections, first detections, false episodes/day, and time in alert. Benefit requires all five repetitions to show either p95 latency at most `0.80x` baseline or throughput at least `1.25x` baseline, while candidate peak RSS and model artifact bytes are each at most `1.25x` baseline. Recovery/integrity checks must pass.

- [ ] **Step 4: Run candidate benchmark and full parity once**

```powershell
.\.venv-openvino\Scripts\python.exe -m industrial_reliability.inference_benchmark --runtime openvino --champion artifacts\champion --optimized artifacts\phase10b\candidate --features data\processed\phase1b\features.parquet --sample-count 10000 --warmup-count 100 --repetitions 5 --batch-size 1 --cpu-threads 1 --output artifacts\phase10b\candidate-benchmark
.\.venv-openvino\Scripts\python.exe -m pytest --no-cov tests\integration\test_openvino_parity.py -q -m integration
.\.venv\Scripts\python.exe -m industrial_reliability.phase10b_gate compare --baseline artifacts\phase10b\baseline\benchmark.json --candidate artifacts\phase10b\candidate-benchmark\benchmark.json --output artifacts\phase10b\decision.json
```

Expected: one terminal decision with exact hashes; any score/decision/event mismatch is `NOT_ADOPTED` regardless of performance.

- [ ] **Step 5: Commit comparison logic**

```powershell
git add src/industrial_reliability/phase10b_gate.py tests/test_phase10b_gate.py tests/integration/test_openvino_parity.py
git commit -m "test: compare OpenVINO parity and benefit"
```

### Task 4: Resolve the quantization sub-gate without speculative infrastructure

**Files:**
- Modify: `src/industrial_reliability/phase10b_gate.py`
- Modify: `tests/test_phase10b_gate.py`

**Interfaces:**
- Consumes: verified FP32 XML+BIN byte total and fixed autoencoder architecture metadata.
- Produces: `quantization_decision(model_artifact_bytes: int) -> Literal["N/A"]` for the reviewed 32 MiB ceiling and reason code `FP32_MODEL_BELOW_QUANTIZATION_GATE`.

- [ ] **Step 1: Write the failing fixed-ceiling test**

```python
def test_small_dense_model_does_not_add_int8_tooling() -> None:
    status, reason = quantization_decision(2_000_000)
    assert status == "N/A"
    assert reason == "FP32_MODEL_BELOW_QUANTIZATION_GATE"


def test_unexpected_large_artifact_fails_closed() -> None:
    with pytest.raises(ValueError, match="fixed architecture"):
        quantization_decision(32 * 1024 * 1024 + 1)
```

- [ ] **Step 2: Run the test and observe RED**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_phase10b_gate.py -q`

Expected: FAIL because the sub-gate is absent.

- [ ] **Step 3: Implement and verify the size gate**

Return `N/A` at or below `33_554_432` bytes. Above that size, reject the artifact as inconsistent with the reviewed fixed architecture and require a new design rather than silently installing a quantizer. Do not add NNCF, calibration code, or INT8 files.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_phase10b_gate.py -q`

Expected: PASS, and `requirements-phase10b-openvino.txt` remains the only optional requirement file.

- [ ] **Step 4: Commit the measured quantization decision**

```powershell
git add src/industrial_reliability/phase10b_gate.py tests/test_phase10b_gate.py
git commit -m "test: gate OpenVINO quantization need"
```

### Task 5: Publish the decision and change serving only after adoption

**Files:**
- Create if adopted: `src/industrial_reliability/openvino_champion.py`
- Create if adopted: `tests/test_openvino_champion.py`
- Modify if adopted: `src/industrial_reliability/api.py`
- Modify if adopted: `pyproject.toml`
- Modify if adopted: `Dockerfile`
- Modify if adopted: `compose.yaml`
- Modify if adopted: `.env.example`
- Create: `docs/results/phase-10b-openvino-decision.json`
- Create: `docs/results/phase-10b-openvino-decision.md`

**Interfaces:**
- Consumes: terminal Phase 10B decision and verified candidate manifest.
- Produces: unchanged PyTorch/classical serving for `NOT_ADOPTED`/`N/A`; for `ADOPTED`, direct `load_openvino_champion(champion_dir, optimized_dir, expected_manifest_sha256) -> ChampionScorer` used by the scoring API.

- [ ] **Step 1: Publish `N/A` or `NOT_ADOPTED` without runtime edits**

Render the committed JSON/Markdown from the canonical decision. Include exact hashes, parity/performance/resource aggregates, quantization status, reason codes, and limitations. State `OpenVINO is not part of the default runtime.` Skip Steps 2-3 and proceed to Step 4.

- [ ] **Step 2: For `ADOPTED` only, write failing optimized-loader tests**

```python
def test_openvino_loader_rejects_xml_or_bin_tamper(optimized_package: Path) -> None:
    (optimized_package / "optimized" / "model.bin").write_bytes(b"tampered")
    with pytest.raises(ChampionIntegrityError, match="model.bin"):
        load_openvino_champion(
            champion_dir=optimized_package / "champion",
            optimized_dir=optimized_package / "optimized",
            expected_manifest_sha256=optimized_manifest_sha(optimized_package),
        )
```

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_openvino_champion.py -q`

Expected: FAIL because the adopted loader does not exist.

- [ ] **Step 3: Promote the verified FP32 runtime directly**

Add `openvino==2025.4.0` to default dependencies and pin it in the runtime image. `openvino_champion.py` verifies original champion manifest/children plus optimized manifest/XML/BIN before compilation, computes the same evidence vector from the original median/MAD, and returns the existing `ScoredVector`. `api.py` calls this loader directly; Compose mounts the local optimized directory read-only and supplies only expected hashes/paths. Do not keep a runtime engine switch.

Rerun Phase 2 golden HTTP cases, Phase 4 online parity, Phase 5 alert recovery, Phase 8 fault drills, and Phase 9 complete/fallback RCA gates. Render `ADOPTED` only after every affected gate passes.

- [ ] **Step 4: Run common final verification**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -m "not slow"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
docker compose config --quiet
git diff --check
git check-ignore artifacts/phase10b
```

Expected: all commands PASS with branch coverage at least 80%, private candidate evidence is ignored, and the committed decision names the exact tested Git/champion/contract/data/workload hashes.

- [ ] **Step 5: Commit the decision, and runtime only when adopted**

For `N/A` or `NOT_ADOPTED`:

```powershell
git add docs/results/phase-10b-openvino-decision.json docs/results/phase-10b-openvino-decision.md
git commit -m "docs: record OpenVINO decision gate"
```

For `ADOPTED`:

```powershell
git add src/industrial_reliability/openvino_champion.py tests/test_openvino_champion.py src/industrial_reliability/api.py pyproject.toml Dockerfile compose.yaml .env.example docs/results/phase-10b-openvino-decision.json docs/results/phase-10b-openvino-decision.md
git commit -m "perf: adopt measured OpenVINO scoring"
```

## Phase 10B Exit Gate

The phase ends with one exact-SHA status. `N/A` is valid for a stopped platform path or a classical champion and installs nothing. `NOT_ADOPTED` is valid when conversion is unavailable or the candidate misses any parity/benefit/resource gate. `ADOPTED` is valid only for an autoencoder whose optimized default scorer passes all affected downstream gates. INT8 remains `N/A` for the measured fixed model below 32 MiB; no résumé-driven quantization code is added.
