# Phase 7 Reproducible ML Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every online champion traceable to a reproducible MLflow candidate run and an explicit, human-invoked promotion receipt without automatic retraining or promotion.

**Architecture:** The existing Phase 1B training pipeline remains the only source of model math; a thin lifecycle CLI runs it and logs exact data/code/contract/parameter/metric/artifact identities to a local MLflow server. Training ends in `candidate`. A separate promotion command verifies the run and package hashes, registers the packaged detector under one model name, moves the `champion` alias, and writes an immutable receipt. API readiness verifies its local package against that receipt and MLflow before serving scores.

**Tech Stack:** Python 3.12, MLflow 3.x, existing NumPy/scikit-learn/PyTorch champion package, PostgreSQL, FastAPI, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Begin only after Phase 6 passed its real-click gate and Phase 1B remains `FEASIBLE` with a non-null champion manifest.
- MLflow is mandatory. Airflow is not part of this phase and is evaluated separately in Phase 7A.
- Reuse the Phase 1B training and causal feature functions. Do not create a second trainer, feature implementation, model ladder, or generic multi-model runtime.
- Every run records exact dataset, contract, feature-schema, source-code, environment, champion-package, and alert-policy hashes plus parameters and metrics.
- Fit transforms/models on train only, choose thresholds on calibration only, and evaluate the locked ladder once on holdout. Never retune against Phase 1 or Phase 1B holdout.
- Training creates only a candidate. Promotion requires a separate CLI invocation with the exact run ID and approver; no metric callback, scheduled job, API route, or UI may promote automatically.
- The registered model name is `industrial-reliability-anomaly-detector`; the serving alias is `champion`.
- The operator console may display provenance but remains unable to train, compare, or promote models.
- MLflow and API host ports bind to localhost. Credentials and provider keys come from environment variables and never enter tags, artifacts, logs, or browser responses.
- Raw data and model binaries remain local and git-ignored. Committed files are code, tests, configuration, aggregate documentation, and schema definitions.
- Maintain at least 80% branch coverage and separate synthetic CI evidence from private full-data reproducibility evidence.

---

### Task 1: Run a localhost MLflow service with durable metadata

**Files:**
- Modify: `pyproject.toml`
- Modify: `compose.yaml`
- Modify: `.env.example`
- Create: `docker/mlflow.Dockerfile`
- Create: `tests/integration/test_mlflow_service.py`

**Interfaces:**
- Consumes: the existing PostgreSQL Compose service and a dedicated `mlops` optional dependency group.
- Produces: `MLFLOW_TRACKING_URI=http://mlflow:5000` inside Compose, host UI/API `http://127.0.0.1:5000`, PostgreSQL-backed tracking metadata, named volume `mlflow-artifacts`.

- [ ] **Step 1: Write the service identity and binding test**

```python
@pytest.mark.integration
def test_mlflow_service_is_local_and_persistent() -> None:
    config = json.loads(
        subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    service = config["services"]["mlflow"]
    assert service["ports"][0]["host_ip"] == "127.0.0.1"
    assert service["environment"]["MLFLOW_BACKEND_STORE_URI"].startswith("postgresql+psycopg://")
    assert service["build"]["dockerfile"] == "docker/mlflow.Dockerfile"
    assert "mlflow-artifacts" in json.dumps(service["volumes"])
    core = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    assert all(not dependency.startswith("mlflow") for dependency in core)
```

- [ ] **Step 2: Run the test before MLflow is configured**

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_mlflow_service.py -q -m integration`

Expected: FAIL because the `mlflow` service is absent.

- [ ] **Step 3: Add the dependency and service**

Add `mlflow>=3,<4` only to `[project.optional-dependencies].mlops`; do not add it to core scoring dependencies. Create the dedicated image:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[mlops]"
```

Add this service and volume while preserving localhost-only host bindings:

```yaml
mlflow:
  build:
    context: .
    dockerfile: docker/mlflow.Dockerfile
  command: ["/bin/sh", "-c", "exec mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri \"$$MLFLOW_BACKEND_STORE_URI\" --artifacts-destination /mlartifacts --serve-artifacts"]
  environment:
    MLFLOW_BACKEND_STORE_URI: postgresql+psycopg://irp:${POSTGRES_PASSWORD}@postgres:5432/irp
  volumes:
    - mlflow-artifacts:/mlartifacts
  ports:
    - "127.0.0.1:5000:5000"
  depends_on:
    postgres:
      condition: service_healthy

volumes:
  mlflow-artifacts:
```

The literal `${POSTGRES_PASSWORD}` remains an environment reference; `.env.example` contains only a non-secret local example.

- [ ] **Step 4: Build and verify MLflow health**

Run: `docker compose up -d postgres mlflow`

Run: `Invoke-RestMethod http://127.0.0.1:5000/api/2.0/mlflow/experiments/search -Method Post -ContentType application/json -Body '{"max_results":1}'`

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_mlflow_service.py -q -m integration`

Expected: the API returns an experiment list and the test passes.

- [ ] **Step 5: Commit the tracking service**

```powershell
git add pyproject.toml compose.yaml .env.example docker/mlflow.Dockerfile tests/integration/test_mlflow_service.py
git commit -m "build: add durable local MLflow service"
```

### Task 2: Define immutable lifecycle provenance

**Files:**
- Create: `src/industrial_reliability/ml_provenance.py`
- Create: `tests/test_ml_provenance.py`

**Interfaces:**
- Consumes: Phase 1B `champion-manifest.json`, Phase 2 `artifacts/champion/manifest.json`, Phase 5 `alert-policy.json`, Git SHA, Python/platform/dependency versions.
- Produces: frozen `RunProvenanceV1`, `PromotionReceiptV1`, `canonical_sha256`, `verify_provenance`, and self-hashed JSON serializers. Required MLflow tags are `dataset_sha256`, `contract_sha256`, `feature_schema_sha256`, `source_git_sha`, `champion_package_sha256`, `alert_policy_sha256`, and `lifecycle_state`.

- [ ] **Step 1: Write fail-closed provenance tests**

```python
def test_run_provenance_round_trip_verifies_all_hashes(tmp_path: Path) -> None:
    path = tmp_path / "run-provenance.json"
    write_run_provenance(path, provenance_fixture())
    assert load_run_provenance(path) == provenance_fixture()


def test_promotion_receipt_rejects_alias_or_package_mismatch() -> None:
    receipt = receipt_fixture(alias="candidate")
    with pytest.raises(ValueError, match="champion alias"):
        verify_promotion_receipt(receipt, package_manifest_fixture())
```

- [ ] **Step 2: Run tests before creating provenance types**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ml_provenance.py -q`

Expected: FAIL during collection because `ml_provenance` does not exist.

- [ ] **Step 3: Implement exact schemas and canonical hashing**

```python
@dataclass(frozen=True)
class RunProvenanceV1:
    schema_version: Literal["mlflow-run-provenance-v1"]
    mlflow_run_id: str
    experiment_name: str
    lifecycle_state: Literal["candidate"]
    dataset_sha256: str
    contract_sha256: str
    feature_schema_sha256: str
    source_git_sha: str
    python_version: str
    dependency_versions: Mapping[str, str]
    champion_package_sha256: str
    alert_policy_sha256: str
    parameters: Mapping[str, JSONScalar]
    metrics: Mapping[str, float]
    artifact_sha256: Mapping[str, str]
    provenance_sha256: str


@dataclass(frozen=True)
class PromotionReceiptV1:
    schema_version: Literal["mlflow-promotion-receipt-v1"]
    mlflow_run_id: str
    registered_model_name: Literal["industrial-reliability-anomaly-detector"]
    registered_model_version: str
    alias: Literal["champion"]
    model_version: str
    dataset_sha256: str
    contract_sha256: str
    champion_package_sha256: str
    source_git_sha: str
    approver: str
    promoted_at: str
    receipt_sha256: str
```

All SHA fields match `^[0-9a-f]{64}$`. Serialization uses sorted canonical JSON, rejects NaN, and verifies the self-hash before exposing a dataclass.

- [ ] **Step 4: Run provenance tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ml_provenance.py -q`

Expected: PASS, including one-bit tamper rejection.

- [ ] **Step 5: Commit provenance contracts**

```powershell
git add src/industrial_reliability/ml_provenance.py tests/test_ml_provenance.py
git commit -m "feat: define ML lifecycle provenance"
```

### Task 3: Import the immutable candidate and reproduce its fit without holdout

**Files:**
- Create: `src/industrial_reliability/ml_lifecycle.py`
- Create: `tests/test_ml_lifecycle.py`
- Create: `tests/integration/test_mlflow_candidate.py`

**Interfaces:**
- Consumes: immutable Phase 1B run directory and champion manifest; Phase 1B `fit_phase1b_candidate(*, model_id: ModelId, train_features: NDArray[np.float64], calibration_features: NDArray[np.float64], contract: Phase1BContract = PHASE1B) -> FittedCandidate`; Phase 2 `artifacts/champion/` produced by `build_champion_package(run_dir, features_path, output_dir)`; locked alert policy; `MLFLOW_TRACKING_URI`.
- Produces: CLI subcommands `import-candidate` and `reproduce`; MLflow experiment `industrial-reliability-offline`; one `candidate` run containing the immutable Phase 1B/2 evidence and valid `runs:/<run-id>/champion-model`, plus one `reproduction` run containing train/calibration refit threshold, calibration scores, and golden scores. Neither command evaluates holdout.

- [ ] **Step 1: Write tests that prove the CLI delegates and never promotes**

```python
def test_import_candidate_logs_existing_evidence_and_stops_at_candidate(
    fake_mlflow: FakeMlflow,
) -> None:
    result = import_candidate(import_request_fixture(), mlflow_client=fake_mlflow)
    assert fake_mlflow.tags[result.run_id]["lifecycle_state"] == "candidate"
    assert fake_mlflow.tags[result.run_id]["dataset_sha256"] == "a" * 64
    assert result.model_uri == f"runs:/{result.run_id}/champion-model"
    assert fake_mlflow.registered_models == []
    assert fake_mlflow.aliases == []


def test_reproduction_never_calls_holdout_benchmark(fake_mlflow: FakeMlflow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(phase1b_benchmark, "run_phase1b_benchmark", Mock(side_effect=AssertionError("holdout")))
    result = reproduce_candidate(reproduction_request_fixture(), mlflow_client=fake_mlflow)
    assert fake_mlflow.tags[result.run_id]["lifecycle_state"] == "reproduction"


def test_import_candidate_refuses_dirty_or_wrong_source_sha(fake_mlflow: FakeMlflow) -> None:
    with pytest.raises(ValueError, match="source Git SHA"):
        import_candidate(import_request_fixture(source_git_sha="f" * 40), mlflow_client=fake_mlflow)
```

- [ ] **Step 2: Run tests and observe the missing lifecycle CLI**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ml_lifecycle.py -q`

Expected: FAIL during collection because `ml_lifecycle` does not exist.

- [ ] **Step 3: Implement immutable import, valid pyfunc logging, and train/calibration-only refit**

```python
EXPERIMENT_NAME = "industrial-reliability-offline"
REGISTERED_MODEL_NAME = "industrial-reliability-anomaly-detector"


class PackagedChampionPyFunc(mlflow.pyfunc.PythonModel):
    def load_context(self, context: PythonModelContext) -> None:
        self._champion = load_champion(Path(context.artifacts["champion_package"]))

    def predict(
        self,
        context: PythonModelContext,
        model_input: pd.DataFrame,
        params: dict[str, object] | None = None,
    ) -> pd.DataFrame:
        expected = list(self._champion.feature_names)
        if list(model_input.columns) != expected:
            raise ValueError("feature names/order differ from champion package")
        scores = self._champion.score(model_input.to_numpy(dtype=np.float64, copy=False))
        return pd.DataFrame({"score": scores, "is_anomaly": scores >= self._champion.threshold})


def import_candidate(request: ImportCandidateRequest) -> CandidateResult:
    evidence = verify_phase1b_and_package_evidence(request)
    with mlflow.start_run(experiment_id=ensure_experiment(mlflow_client, EXPERIMENT_NAME)) as run:
        log_identity_tags(evidence.identities, lifecycle_state="candidate")
        log_aggregate_metrics(evidence.phase1b_aggregate_metrics)
        model_info = mlflow.pyfunc.log_model(
            artifact_path="champion-model",
            python_model=PackagedChampionPyFunc(),
            artifacts={"champion_package": str(request.champion_package)},
            input_example=evidence.golden_feature_frame.head(1),
        )
        log_allowlisted_evidence(evidence)
        return CandidateResult(run.info.run_id, model_info.model_uri, evidence.package_manifest_sha256)


def reproduce_candidate(request: ReproductionRequest) -> ReproductionResult:
    evidence = verify_phase1b_and_package_evidence(request)
    table = pq.read_table(request.features_path, filters=[("split", "in", ["train", "calibration"])])
    frame = table.to_pandas()
    fitted = fit_phase1b_candidate(
        model_id=evidence.model_id,
        train_features=ordered_features(frame, "train", evidence.feature_names),
        calibration_features=ordered_features(frame, "calibration", evidence.feature_names),
    )
    calibration_scores = fitted.detector.score(ordered_features(frame, "calibration", evidence.feature_names))
    golden_scores = fitted.detector.score(evidence.golden_feature_frame.to_numpy(dtype=np.float64))
    return log_reproduction_run(evidence, fitted.threshold, calibration_scores, golden_scores)
```

`import_candidate` logs only immutable Phase 1B aggregate evidence and the already-built Phase 2 package. `reproduce_candidate` calls the public Phase 1B fit/calibration function and scores packaged golden feature vectors; it never invokes `run_phase1b_benchmark`, loads holdout rows, emits a new feasibility verdict, or rebuilds the Phase 2 package. Allowlisted artifacts exclude raw ZIP/CSV/Parquet and non-champion weights.

- [ ] **Step 4: Verify unit and real MLflow candidate recording**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ml_lifecycle.py tests/integration/test_mlflow_candidate.py -q`

Expected: PASS; the candidate is searchable by all seven identity tags, `mlflow.pyfunc.load_model(result.model_uri)` scores the golden input, the reproduction run contains only calibration/golden outputs, and no registered model exists.

- [ ] **Step 5: Commit candidate tracking**

```powershell
git add src/industrial_reliability/ml_lifecycle.py tests/test_ml_lifecycle.py tests/integration/test_mlflow_candidate.py
git commit -m "feat: track and reproduce MLflow candidate"
```

### Task 4: Add explicit candidate-to-champion promotion

**Files:**
- Modify: `src/industrial_reliability/ml_lifecycle.py`
- Modify: `tests/test_ml_lifecycle.py`
- Create: `tests/integration/test_mlflow_promotion.py`

**Interfaces:**
- Consumes: exact candidate `run_id`, non-empty `approver`, expected dataset/contract/source/package hashes, and MLflow run artifacts.
- Produces: CLI `.\.venv\Scripts\python.exe -m industrial_reliability.ml_lifecycle promote --run-id <exact-id> --approver <name> --expected-source-git-sha <40-hex> --output artifacts/phase7/<run-id>/promotion-receipt.json`; registered model version and alias `champion`.

- [ ] **Step 1: Write tests for the manual gate**

```python
def test_promote_requires_exact_run_and_approver(fake_mlflow: FakeMlflow) -> None:
    with pytest.raises(ValueError, match="approver"):
        promote_candidate(promotion_request(approver=""), mlflow_client=fake_mlflow)


def test_promote_verifies_artifacts_before_alias_change(fake_mlflow: FakeMlflow) -> None:
    fake_mlflow.tamper_artifact("detector.joblib")
    with pytest.raises(ValueError, match="artifact SHA-256"):
        promote_candidate(promotion_request(), mlflow_client=fake_mlflow)
    assert fake_mlflow.aliases == []
```

- [ ] **Step 2: Run tests and observe the absent promotion command**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ml_lifecycle.py -q`

Expected: FAIL because `promote_candidate` is not defined.

- [ ] **Step 3: Implement verify-register-alias-receipt ordering**

```python
def promote_candidate(request: PromotionRequest, *, mlflow_client: MlflowClient) -> PromotionReceiptV1:
    run = require_candidate_run(mlflow_client, request.run_id)
    provenance = download_and_verify_provenance(mlflow_client, run.info.run_id)
    verify_expected_identities(request, provenance)
    model_uri = f"runs:/{run.info.run_id}/champion-model"
    download_and_verify_logged_model(mlflow_client, model_uri, provenance)
    registered = mlflow.register_model(
        model_uri=model_uri,
        name=REGISTERED_MODEL_NAME,
    )
    version = require_ready_model_version(mlflow_client, registered.version)
    mlflow_client.set_registered_model_alias(REGISTERED_MODEL_NAME, "champion", version)
    receipt = build_promotion_receipt(request, provenance, version)
    write_promotion_receipt(request.output, receipt)
    return receipt
```

No import or reproduction function calls `promote_candidate`. Promotion registers the already-logged `runs:/<run-id>/champion-model`; it never logs a new model or starts a run. The command refuses lifecycle states other than `candidate`, metrics that do not meet the Phase 1B gate, missing artifacts, hash differences, dirty/unexpected source SHA, and an output path that already exists.

- [ ] **Step 4: Verify promotion against the real local registry**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_ml_lifecycle.py tests/integration/test_mlflow_promotion.py -q`

Expected: PASS; one explicit call sets exactly one `champion` alias and writes a self-hashed receipt matching the registered run.

- [ ] **Step 5: Commit manual promotion**

```powershell
git add src/industrial_reliability/ml_lifecycle.py tests/test_ml_lifecycle.py tests/integration/test_mlflow_promotion.py
git commit -m "feat: add explicit champion promotion"
```

### Task 5: Fail scoring readiness closed on provenance mismatch

**Files:**
- Modify: `src/industrial_reliability/champion.py`
- Modify: `src/industrial_reliability/api.py`
- Modify: `src/industrial_reliability/persistence.py`
- Create: `tests/test_model_provenance_api.py`

**Interfaces:**
- Consumes: `PROMOTION_RECEIPT_PATH`, `MLFLOW_TRACKING_URI`, local `artifacts/champion/manifest.json`, MLflow alias `models:/industrial-reliability-anomaly-detector@champion`.
- Produces: `ChampionProvenanceVerifier.verify() -> VerifiedChampionProvenance`; `GET /v1/models/{model_version}/provenance`; `/readyz` fails with stable code `CHAMPION_PROVENANCE_MISMATCH` when local package, receipt, registry, or alias disagrees.

- [ ] **Step 1: Write readiness and read-route tests**

```python
def test_readyz_fails_closed_on_registry_alias_mismatch(client: TestClient, mlflow: FakeMlflow) -> None:
    mlflow.alias_run_id = "different-run"
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CHAMPION_PROVENANCE_MISMATCH"


def test_model_provenance_returns_allowlisted_identity(client: TestClient) -> None:
    response = client.get("/v1/models/model-v1/provenance")
    assert response.status_code == 200
    assert set(response.json()["data"]) == {
        "model_version", "mlflow_run_id", "registered_model_version", "dataset_sha256",
        "contract_sha256", "feature_schema_sha256", "source_git_sha",
        "champion_package_sha256", "alert_policy_sha256", "metrics",
    }
```

- [ ] **Step 2: Run tests before provenance verification is wired**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_model_provenance_api.py -q`

Expected: FAIL because readiness ignores the receipt and the route is 404.

- [ ] **Step 3: Verify identities at startup and expose the allowlist**

```python
class ChampionProvenanceVerifier:
    def verify(self) -> VerifiedChampionProvenance:
        receipt = load_promotion_receipt(self._receipt_path)
        manifest = load_champion_manifest(self._package_dir / "manifest.json")
        registered = self._client.get_model_version_by_alias(
            "industrial-reliability-anomaly-detector", "champion"
        )
        if registered.run_id != receipt.mlflow_run_id:
            raise ProvenanceMismatch("registry alias run differs from promotion receipt")
        verify_promotion_receipt(receipt, manifest)
        return VerifiedChampionProvenance.from_verified(receipt, manifest, registered)
```

Cache only a successful immutable verification for the process lifetime. A failed verification is rechecked on `/readyz` and never permits `/v1/score`. The provenance API returns aggregate metrics and hashes only; it excludes approver identity, filesystem paths, environment values, and MLflow credentials.

- [ ] **Step 4: Verify readiness, scoring, and operator read path**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_model_provenance_api.py tests/test_api.py tests/test_alert_api.py -q`

Expected: PASS; matching provenance allows scoring and the alert detail can link to the model provenance route.

- [ ] **Step 5: Commit runtime provenance enforcement**

```powershell
git add src/industrial_reliability/champion.py src/industrial_reliability/api.py src/industrial_reliability/persistence.py tests/test_model_provenance_api.py
git commit -m "feat: enforce champion MLflow provenance"
```

### Task 6: Certify reproducibility and lineage

**Files:**
- Create: `src/industrial_reliability/phase7_gate.py`
- Create: `tests/test_phase7_gate.py`
- Create: `tests/integration/test_phase7_reproducibility.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: one imported immutable candidate run, one train/calibration-only reproduction run, one promotion receipt, registered champion alias, and online provenance API.
- Produces: `artifacts/phase7/<promoted-run-id>/phase7-gate.json` with both run IDs, stable identities, threshold/calibration/golden-score deltas, promoted package/receipt hash, registered version, alias, and booleans `rerun_within_tolerance`, `lineage_complete`, `manual_promotion_verified`, `online_provenance_verified`.

- [ ] **Step 1: Write tolerance and lineage gate tests**

```python
def test_gate_accepts_reproducible_runs_with_exact_identity() -> None:
    gate = evaluate_phase7(run_fixture("run-a"), run_fixture("run-b"), receipt_fixture())
    assert gate.rerun_within_tolerance is True
    assert gate.threshold_delta <= 1e-9
    assert gate.max_calibration_score_delta <= 1e-6
    assert gate.max_golden_score_delta <= 1e-6


def test_gate_rejects_matching_metrics_with_different_data() -> None:
    second = replace(run_fixture("run-b"), dataset_sha256="f" * 64)
    with pytest.raises(ValueError, match="dataset SHA-256"):
        evaluate_phase7(run_fixture("run-a"), second, receipt_fixture())
```

- [ ] **Step 2: Run tests before the gate evaluator exists**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_phase7_gate.py -q`

Expected: FAIL during collection because `phase7_gate` does not exist.

- [ ] **Step 3: Implement fail-closed comparison and canonical gate output**

```python
THRESHOLD_ATOL = 1e-9
CALIBRATION_SCORE_ATOL = 1e-6
GOLDEN_SCORE_ATOL = 1e-6
REPRODUCTION_IDENTITIES = (
    "dataset_sha256", "contract_sha256", "feature_schema_sha256", "source_git_sha",
    "model_id", "model_parameter_sha256",
)


def evaluate_phase7(first: RunEvidence, second: RunEvidence, receipt: PromotionReceiptV1) -> Phase7Gate:
    require_equal_identities(first, second, REPRODUCTION_IDENTITIES)
    threshold_delta = abs(first.threshold - second.threshold)
    calibration_delta = max_abs_delta(first.calibration_scores, second.calibration_scores)
    golden_delta = max_abs_delta(first.golden_scores, second.golden_scores)
    verify_receipt_binds_imported_package(receipt, first)
    return Phase7Gate(
        rerun_within_tolerance=threshold_delta <= THRESHOLD_ATOL
        and calibration_delta <= CALIBRATION_SCORE_ATOL
        and golden_delta <= GOLDEN_SCORE_ATOL,
        threshold_delta=threshold_delta,
        max_calibration_score_delta=calibration_delta,
        max_golden_score_delta=golden_delta,
        lineage_complete=all(first.tags.get(name) for name in REPRODUCTION_IDENTITIES),
        manual_promotion_verified=receipt.mlflow_run_id == first.run_id,
    )
```

The writer refuses any false required boolean, absent artifact hash, alias/run mismatch, or output overwrite.

- [ ] **Step 4: Run private reproducibility and repository gates**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_phase7_gate.py tests/integration/test_phase7_reproducibility.py -q`

Run: `.\.venv\Scripts\python.exe -m ruff check .`

Run: `.\.venv\Scripts\python.exe -m ruff format --check .`

Run: `.\.venv\Scripts\python.exe -m mypy src`

Run: `.\.venv\Scripts\python.exe -m pytest -q --cov-branch --cov-fail-under=80`

Run: `.\.venv\Scripts\python.exe -m pip check`

Run: `.\.venv\Scripts\python.exe -m build`

Expected: every command exits 0; the gate proves a train/calibration refit matches the immutable candidate threshold/calibration/golden outputs within tolerance, and the promoted Phase 2 package separately matches the receipt and online provenance endpoint.

- [ ] **Step 5: Commit Phase 7 certification**

```powershell
git add src/industrial_reliability/phase7_gate.py tests/test_phase7_gate.py tests/integration/test_phase7_reproducibility.py README.md
git commit -m "test: certify reproducible ML lineage"
```

## Phase 7 Exit Gate

Move Phase 7A to `Ready` only when the online Phase 2 package resolves to the MLflow `champion` alias and immutable promotion receipt; a train/calibration-only refit from identical data/contract/code/parameters reproduces the locked threshold within `1e-9` and calibration/golden scores within `1e-6`; no holdout evaluation is repeated; every required identity is queryable; promotion was a separate explicit command; and `phase7-gate.json` is self-hashed. A successful local package without MLflow lineage does not pass.
