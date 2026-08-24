# Phase 2 Champion Package and Scoring API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package exactly the feasible Phase 1B champion and expose deterministic, integrity-checked stateless scoring through `POST /v1/score`.

**Architecture:** A packaging command verifies the private Phase 1B champion and copies one fitted detector plus one train-only evidence baseline into a hashed local package. `ChampionScorer` is the only runtime model surface; FastAPI validates a versioned feature vector, calls it, and returns a versioned score decision without constructing features or selecting models.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Uvicorn, NumPy, joblib, pytest, httpx, Docker

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Do not start Phase 2 unless Phase 1B aggregate evidence is `FEASIBLE` and its private `phase1b-champion-v1` manifest is non-null and hash-consistent.
- Package only the selected champion. Do not add a registry, factory, multi-model runtime, model promotion UI, or batch-scoring platform.
- `POST /v1/score` accepts only an ordered versioned feature vector carrying the exact `contract_sha256` and requested `model_version`; feature/window construction stays outside the API.
- A contract, model version, feature name/order/count, non-finite value, package hash, or artifact hash mismatch fails closed.
- The score, threshold, anomaly decision, and evidence vector must match Phase 1B golden artifacts; anomaly comparison remains inclusive `score >= threshold`.
- The API is stateless, binds to localhost in local execution, has no authentication, and must not be exposed to a public network.
- Raw telemetry and Phase 1B private run artifacts remain local and git-ignored; the built champion package is a local runtime artifact, not a committed file.
- Every quality pass runs Ruff, Ruff formatting, mypy, pytest with at least 80% branch coverage, `pip check`, package build, and Docker build.

---

### Task 1: Hard-gate and build one champion package

**Files:**
- Create: `src/industrial_reliability/package_champion.py`
- Create: `tests/test_package_champion.py`
- Modify: `pyproject.toml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `artifacts/phase1b/$phase1bRunId/champion-manifest.json`, selected detector, `evidence-baseline.npz`, `scores.parquet`, and the hashed Phase 1B feature Parquet.
- Produces: `build_champion_package(run_dir: Path, features_path: Path, output_dir: Path) -> ChampionPackageResult` and local `artifacts/champion/{manifest.json,detector.joblib,evidence-baseline.npz,golden-cases.json}`.

- [ ] **Step 1: Write failing package-gate tests**

```python
def test_package_rejects_infeasible_or_missing_champion(tmp_path: Path) -> None:
    run_dir = phase1b_run(tmp_path, verdict="NOT FEASIBLE", champion=False)
    with pytest.raises(ChampionPackageError, match="FEASIBLE champion"):
        build_champion_package(run_dir, tmp_path / "features.parquet", tmp_path / "package")


def test_package_rejects_any_referenced_hash_mismatch(tmp_path: Path) -> None:
    run_dir, features = feasible_phase1b_run(tmp_path)
    (run_dir / "models" / "statistical.joblib").write_bytes(b"tampered")
    with pytest.raises(ChampionPackageError, match="SHA-256"):
        build_champion_package(run_dir, features, tmp_path / "package")


def test_package_contains_one_model_and_three_golden_cases(tmp_path: Path) -> None:
    run_dir, features = feasible_phase1b_run(tmp_path)
    result = build_champion_package(run_dir, features, tmp_path / "package")
    assert result.manifest["schema_version"] == "champion-package-v1"
    assert set(path.name for path in result.output_dir.iterdir()) == {
        "manifest.json",
        "detector.joblib",
        "evidence-baseline.npz",
        "golden-cases.json",
    }
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_package_champion.py -q`

Expected: FAIL with `ModuleNotFoundError: industrial_reliability.package_champion`.

- [ ] **Step 3: Add explicit runtime dependencies and implement the gate**

Add `fastapi>=0.116,<1`, `pydantic>=2.11,<3`, `uvicorn>=0.35,<1`, and `joblib>=1.5,<2` to project dependencies. Add `httpx>=0.28,<1` to the existing `dev` optional-dependency list. Define the artifact types before the builder:

```python
class ThresholdProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    split: Literal["calibration"]
    quantile: Literal[0.995]
    method: Literal["higher"]


class ChampionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["champion-package-v1"]
    source_champion_schema: Literal["phase1b-champion-v1"]
    source_run_id: str
    model_id: Literal["statistical", "isolation_forest", "autoencoder"]
    model_version: str
    contract_sha256: str
    source_dataset_sha256: str
    feature_names: tuple[str, ...]
    threshold: float
    threshold_provenance: ThresholdProvenance
    golden_case_count: Literal[3]
    artifact_sha256: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class GoldenCase:
    case_id: str
    source_timestamp: datetime
    window_start: datetime
    window_end: datetime
    feature_names: tuple[str, ...]
    feature_values: tuple[float, ...]
    expected_score: float
    expected_threshold: float
    expected_is_anomaly: bool
    expected_evidence: tuple[tuple[str, float, float], ...]


@dataclass(frozen=True, slots=True)
class ChampionPackageResult:
    output_dir: Path
    manifest: ChampionManifest
    manifest_sha256: str
```

Serialize golden cases under top-level schema `champion-golden-cases-v1` with exact key `cases`. Validate all hashes as lowercase 64-hex, exactly three allowlisted artifact keys, unique non-empty feature names, finite threshold/values/evidence, and equal feature lengths; copy the artifact mapping into `MappingProxyType` in an after-validator so callers cannot mutate it. Then implement:

```python
def build_champion_package(
    run_dir: Path, features_path: Path, output_dir: Path
) -> ChampionPackageResult:
    champion = load_json_object(run_dir / "champion-manifest.json")
    if (
        champion.get("schema_version") != "phase1b-champion-v1"
        or champion.get("verdict") != "FEASIBLE"
    ):
        raise ChampionPackageError("Phase 2 requires a FEASIBLE champion")
    if output_dir.exists():
        raise FileExistsError(f"destination already exists: {output_dir}")
    verify_phase1b_artifacts(run_dir, features_path, champion)
    verify_git_ancestor(cast(str, champion["git_sha"]))
    golden = select_golden_cases(run_dir / "scores.parquet", features_path, champion)
    return atomic_copy_package(run_dir, output_dir, champion, golden)
```

`verify_git_ancestor` runs `subprocess.run(["git", "merge-base", "--is-ancestor", champion_git_sha, "HEAD"], check=False)` and rejects a non-zero exit. Select exactly three calibration rows deterministically: earliest valid row, highest normal score, and earliest anomalous score for the champion. Store the exact `GoldenCase` fields above. `manifest.json` must include the exact `ChampionManifest` fields and allow only `detector.joblib`, `evidence-baseline.npz`, and `golden-cases.json` in `artifact_sha256`. Print the SHA-256 of `manifest.json`; this external value is the runtime trust anchor.

- [ ] **Step 4: Protect local packages and run focused tests**

Ensure `.gitignore` contains `artifacts/champion/`. Run:

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_package_champion.py -q`

Expected: PASS; any missing, extra, stale, or hash-mismatched source artifact is rejected before `joblib.load`, and failed builds leave no partial destination.

- [ ] **Step 5: Commit the package builder**

```powershell
git add pyproject.toml .gitignore src/industrial_reliability/package_champion.py tests/test_package_champion.py
git commit -m "feat: package the Phase 1B champion"
```

Expected: no package or private Phase 1B artifact is staged.

### Task 2: Define the stable feature and score messages

**Files:**
- Create: `src/industrial_reliability/runtime_messages.py`
- Create: `tests/test_runtime_messages.py`

**Interfaces:**
- Consumes: exact Phase 1B provenance and feature order.
- Produces: `CoverageEvidenceV1`, `FeatureVectorV1`, `ScoreRequestV1`, `EvidenceValueV1`, `ScoreDecisionV1`, `ScoreResponseV1`, and `ErrorResponseV1` Pydantic models.

- [ ] **Step 1: Write strict schema tests**

```python
def test_feature_vector_rejects_extra_or_nonfinite_values() -> None:
    payload = valid_feature_vector_payload()
    payload["feature_values"][0] = float("nan")
    with pytest.raises(ValidationError):
        FeatureVectorV1.model_validate(payload)
    payload = valid_feature_vector_payload() | {"unexpected": True}
    with pytest.raises(ValidationError):
        FeatureVectorV1.model_validate(payload)


def test_score_request_requires_matching_feature_lengths() -> None:
    payload = valid_feature_vector_payload()
    payload["feature_values"] = payload["feature_values"][:-1]
    with pytest.raises(ValidationError, match="same length"):
        ScoreRequestV1(model_version="phase1b-statistical-v1", feature_vector=payload)
```

- [ ] **Step 2: Run tests and verify the schema module is absent**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_runtime_messages.py -q`

Expected: FAIL because `industrial_reliability.runtime_messages` does not exist.

- [ ] **Step 3: Implement frozen, extra-forbid Pydantic models**

```python
class FrozenMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageEvidenceV1(FrozenMessage):
    observations_by_bin: tuple[int, int, int, int, int, int]
    bin_ends: tuple[datetime, datetime, datetime, datetime, datetime, datetime]


class FeatureVectorV1(FrozenMessage):
    schema_version: Literal["feature-vector-v1"] = "feature-vector-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_timestamp: datetime
    emitted_at: datetime
    window_id: UUID
    machine_id: str = Field(min_length=1, max_length=128)
    window_start: datetime
    window_end: datetime
    feature_names: tuple[str, ...] = Field(min_length=1)
    feature_values: tuple[float, ...] = Field(min_length=1)
    coverage: CoverageEvidenceV1


class ScoreRequestV1(FrozenMessage):
    model_version: str = Field(min_length=1, max_length=200)
    feature_vector: FeatureVectorV1


class EvidenceValueV1(FrozenMessage):
    feature_name: str
    feature_value: float
    robust_deviation: float


class ScoreDecisionV1(FrozenMessage):
    schema_version: Literal["score-decision-v1"] = "score-decision-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str
    contract_sha256: str
    source_timestamp: datetime
    emitted_at: datetime
    decision_id: UUID
    window_id: UUID
    model_version: str
    score: float
    threshold: float
    is_anomaly: bool
    evidence_vector: tuple[EvidenceValueV1, ...]


class ApiErrorV1(FrozenMessage):
    code: str
    message: str


class ScoreResponseV1(FrozenMessage):
    success: Literal[True] = True
    data: ScoreDecisionV1
    error: None = None


class ErrorResponseV1(FrozenMessage):
    success: Literal[False] = False
    data: None = None
    error: ApiErrorV1
```

Add model validators requiring naive `source_timestamp`, `window_start`, `window_end`, timezone-aware UTC `emitted_at`, `window_start < window_end == source_timestamp`, six strictly increasing bin ends with each count at least 24, equal unique feature-name/value lengths, finite numeric fields, and 64-lowercase-hex hashes on both message types.

- [ ] **Step 4: Run schema tests**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_runtime_messages.py -q`

Expected: PASS, including JSON round-trip tests and rejection of timezone/ordering/hash violations.

- [ ] **Step 5: Commit the runtime contract**

```powershell
git add src/industrial_reliability/runtime_messages.py tests/test_runtime_messages.py
git commit -m "feat: define scoring message contract"
```

Expected: one schema-only commit with no API or Kafka code.

### Task 3: Load and score the integrity-checked champion

**Files:**
- Create: `src/industrial_reliability/champion.py`
- Create: `tests/test_champion.py`

**Interfaces:**
- Consumes: local champion package and the out-of-package expected manifest SHA-256.
- Produces: `load_champion(package_dir: Path, expected_manifest_sha256: str) -> ChampionScorer` and `ChampionScorer.score(feature: FeatureVectorV1) -> ScoredVector`.

- [ ] **Step 1: Write tamper, identity, and golden parity tests**

```python
def test_load_champion_rejects_manifest_or_model_tamper(package_dir: Path) -> None:
    expected = sha256_file(package_dir / "manifest.json")
    (package_dir / "detector.joblib").write_bytes(b"tampered")
    with pytest.raises(ChampionIntegrityError, match="detector.joblib"):
        load_champion(package_dir, expected)


def test_score_rejects_contract_model_and_feature_order(package_dir: Path) -> None:
    scorer = load_champion(package_dir, package_manifest_sha(package_dir))
    with pytest.raises(ScoringContractError, match="feature order"):
        scorer.score(feature_vector(feature_names=tuple(reversed(scorer.feature_names))))


def test_all_golden_cases_match_phase1b(package_dir: Path) -> None:
    scorer = load_champion(package_dir, package_manifest_sha(package_dir))
    for case in load_golden_cases(package_dir):
        actual = scorer.score(case.feature_vector)
        assert actual.score == pytest.approx(case.expected_score, rel=0.0, abs=1e-12)
        assert actual.evidence_vector == case.expected_evidence
```

- [ ] **Step 2: Run tests and verify the loader is missing**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_champion.py -q`

Expected: FAIL because `industrial_reliability.champion` does not exist.

- [ ] **Step 3: Implement verification before deserialization**

```python
def load_champion(package_dir: Path, expected_manifest_sha256: str) -> ChampionScorer:
    manifest_path = package_dir / "manifest.json"
    if sha256_file(manifest_path) != expected_manifest_sha256:
        raise ChampionIntegrityError("manifest SHA-256 does not match the runtime trust anchor")
    manifest = ChampionManifest.model_validate_json(manifest_path.read_bytes())
    for name, expected in manifest.artifact_sha256.items():
        if sha256_file(package_dir / name) != expected:
            raise ChampionIntegrityError(f"{name} SHA-256 mismatch")
    detector = joblib.load(package_dir / "detector.joblib")
    baseline = np.load(package_dir / "evidence-baseline.npz", allow_pickle=False)
    return ChampionScorer.from_verified(manifest, detector, baseline)
```

Reject symlinks and any manifest artifact name outside the package root. `evidence-baseline.npz` must contain only 1-D `feature_names`, `median`, and `mad` arrays of equal non-zero length and exact manifest order. This local package is trusted only after the external manifest hash and every child hash pass.

- [ ] **Step 4: Implement deterministic score and evidence output**

```python
@dataclass(frozen=True, slots=True)
class ScoredVector:
    score: float
    threshold: float
    is_anomaly: bool
    evidence_vector: tuple[EvidenceValueV1, ...]


def score(self, feature: FeatureVectorV1) -> ScoredVector:
    self._validate_identity(feature)
    matrix = np.asarray([feature.feature_values], dtype=np.float64)
    score = float(self.detector.score(matrix)[0])
    deviations = np.divide(
        np.abs(matrix[0] - self.median),
        1.4826 * self.mad,
        out=np.zeros_like(matrix[0]),
        where=self.mad != 0.0,
    )
    evidence = tuple(
        EvidenceValueV1(
            feature_name=name, feature_value=float(value), robust_deviation=float(delta)
        )
        for name, value, delta in zip(self.feature_names, matrix[0], deviations, strict=True)
    )
    return ScoredVector(score, self.threshold, score >= self.threshold, evidence)
```

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_champion.py -q`

Expected: PASS; caller arrays and package files remain unchanged, and all three golden cases match exactly within `1e-12` score tolerance.

- [ ] **Step 5: Commit the single-champion scorer**

```powershell
git add src/industrial_reliability/champion.py tests/test_champion.py
git commit -m "feat: score with verified champion package"
```

Expected: no registry, plugin loader, model switch, or second runtime implementation is present.

### Task 4: Expose health, readiness, and stateless scoring

**Files:**
- Create: `src/industrial_reliability/api.py`
- Create: `tests/test_api.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `ChampionScorer`, `ScoreRequestV1`, and environment variables `CHAMPION_PACKAGE_DIR` and `CHAMPION_MANIFEST_SHA256`.
- Produces: `create_app(scorer: ChampionScorer) -> FastAPI`, `create_app_from_env() -> FastAPI`, `GET /healthz`, `GET /readyz`, and `POST /v1/score`.

- [ ] **Step 1: Write API behavior tests**

```python
def test_score_returns_versioned_decision(
    client: TestClient, valid_request: dict[str, object]
) -> None:
    response = client.post("/v1/score", json=valid_request)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["schema_version"] == "score-decision-v1"
    assert body["data"]["is_anomaly"] == (body["data"]["score"] >= body["data"]["threshold"])
    assert body["data"]["window_id"] == valid_request["feature_vector"]["window_id"]


@pytest.mark.parametrize("field", ["model_version", "contract_sha256"])
def test_score_identity_mismatch_is_conflict(
    client: TestClient, valid_request: dict[str, object], field: str
) -> None:
    mutate_identity(valid_request, field)
    response = client.post("/v1/score", json=valid_request)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SCORING_CONTRACT_MISMATCH"
```

Also test malformed input returns the exact `ErrorResponseV1` envelope with 422, `/healthz` returns `{"success":true,"data":{"status":"ok"},"error":null}` without model details, `/readyz` returns the same envelope with status `ready` only after verified load, and startup fails before binding when the manifest trust anchor is absent or wrong.

- [ ] **Step 2: Run tests and verify the API module is missing**

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_api.py -q`

Expected: FAIL because `industrial_reliability.api` does not exist.

- [ ] **Step 3: Implement the app factory and deterministic decision IDs**

```python
def create_app(scorer: ChampionScorer) -> FastAPI:
    app = FastAPI(title="Industrial Reliability Scoring API", version="1.0")

    @app.exception_handler(ScoringContractError)
    async def scoring_contract_error(
        _request: Request, error: ScoringContractError
    ) -> JSONResponse:
        body = ErrorResponseV1(
            error=ApiErrorV1(code="SCORING_CONTRACT_MISMATCH", message=str(error))
        )
        return JSONResponse(status_code=409, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponseV1(
            error=ApiErrorV1(code="INVALID_REQUEST", message="request validation failed")
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.post("/v1/score", response_model=ScoreResponseV1)
    def score(request: ScoreRequestV1) -> ScoreResponseV1:
        result = scorer.score(request.feature_vector)
        feature = request.feature_vector
        decision_id = uuid5(
            RUNTIME_NAMESPACE, f"decision:{feature.window_id}:{scorer.model_version}"
        )
        decision = ScoreDecisionV1(
            message_id=decision_id,
            decision_id=decision_id,
            replay_session_id=feature.replay_session_id,
            source_dataset_sha256=feature.source_dataset_sha256,
            contract_sha256=feature.contract_sha256,
            source_timestamp=feature.source_timestamp,
            emitted_at=datetime.now(UTC),
            window_id=feature.window_id,
            model_version=scorer.model_version,
            score=result.score,
            threshold=result.threshold,
            is_anomaly=result.is_anomaly,
            evidence_vector=result.evidence_vector,
        )
        return ScoreResponseV1(data=decision)

    return app
```

Keep the API synchronous because one local CPU score call is bounded; do not add queues or background jobs. `create_app_from_env` resolves the two required variables and calls `load_champion` before returning the app.

- [ ] **Step 4: Document local-only configuration and run API tests**

Add only variable names and safe example paths/hashes to `.env.example`; do not place secrets or actual private hashes in Git.

Run: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_api.py -q`

Expected: PASS; score responses have deterministic decision IDs for the same window/model while `emitted_at` remains the actual UTC response time.

- [ ] **Step 5: Commit the API slice**

```powershell
git add .env.example src/industrial_reliability/api.py tests/test_api.py
git commit -m "feat: expose stateless champion scoring"
```

Expected: no auth, public binding, feature construction, persistence, or model selection code is included.

### Task 5: Certify package/API parity and build the runtime image

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `tests/integration/test_scoring_api.py`
- Create: `docs/results/phase-2-model-package-scoring-api.md`
- Create: `requirements-runtime.txt`

**Interfaces:**
- Consumes: exact local champion package and manifest trust anchor.
- Produces: tested local scoring image and aggregate Phase 2 parity report.

- [ ] **Step 1: Write the package-to-HTTP golden integration test**

```python
@pytest.mark.integration
def test_http_scores_every_packaged_golden_case(champion_package: Path) -> None:
    scorer = load_champion(champion_package, package_manifest_sha(champion_package))
    client = TestClient(create_app(scorer))
    for case in load_golden_cases(champion_package):
        response = client.post("/v1/score", json=case.request)
        assert response.status_code == 200
        assert response.json()["data"]["score"] == pytest.approx(
            case.expected_score, rel=0.0, abs=1e-12
        )
        assert response.json()["data"]["evidence_vector"] == case.expected_evidence
```

- [ ] **Step 2: Create a single non-root runtime image**

```dockerfile
FROM python:3.12.10-slim-bookworm
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir .
USER 65532:65532
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "industrial_reliability.api:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

`.dockerignore` must exclude `.git`, `.venv`, `.worktrees`, `data`, `artifacts`, `references`, caches, coverage, and local environment files. The package is mounted read-only at runtime, never copied into the image. Container networking listens on `0.0.0.0:8000`; `compose.yaml` must publish it later as `127.0.0.1:8000:8000`.

- [ ] **Step 3: Build the package and run focused integration evidence**

```powershell
$phase1b = Get-Content -LiteralPath docs/results/phase-1b-metrics.json -Raw | ConvertFrom-Json
if ($phase1b.verdict -ne 'FEASIBLE' -or [string]::IsNullOrWhiteSpace($phase1b.run_id)) { throw 'Phase 1B champion gate failed' }
$phase1bRunDir = Join-Path 'artifacts/phase1b' $phase1b.run_id
.\.venv\Scripts\python.exe -m industrial_reliability.package_champion --run-dir $phase1bRunDir --features data/processed/phase1b/features.parquet --output-dir artifacts/champion
.\.venv\Scripts\python.exe -m pytest --no-cov tests/integration/test_scoring_api.py -q
docker build --tag industrial-reliability:phase2 .
```

Expected: the command derives the reviewed run ID directly from aggregate evidence; the package command prints the manifest SHA-256, all golden HTTP cases PASS, and Docker build exits 0. If the aggregate has no feasible run ID, PowerShell stops before package construction.

- [ ] **Step 4: Run complete gates and write measured evidence**

```powershell
.\.venv\Scripts\python.exe -m pip freeze --exclude-editable | Sort-Object | Set-Content -Encoding ascii requirements-runtime.txt
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest --cov=industrial_reliability --cov-branch --cov-fail-under=80
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
git diff --check
```

Expected: all commands PASS. Record exact Git SHA, Phase 1B run/contract/source/model/package hashes, golden-case count/tolerance, Docker image ID, command results, localhost-only boundary, and limitations in `docs/results/phase-2-model-package-scoring-api.md`; do not record raw feature values or private paths.

- [ ] **Step 5: Commit Phase 2 evidence and runtime build files**

```powershell
git add Dockerfile .dockerignore requirements-runtime.txt tests/integration/test_scoring_api.py docs/results/phase-2-model-package-scoring-api.md
git commit -m "docs: certify Phase 2 scoring parity"
git status --short --branch
```

Expected: the local champion package stays ignored; the Phase 2 report does not claim production deployment.

## Whole-Phase Review and Merge Gate

Phase 3 remains blocked until reviewers verify: Phase 1B is feasible; the package has exactly one detector; the external manifest hash anchors all loaded bytes; every golden score/evidence vector matches; the API rejects identity/order/tamper errors; coverage is at least 80%; and the runtime image builds. Run `git diff --check` and stage only the exact Phase 2 files before merging.
