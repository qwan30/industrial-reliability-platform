# Code Audit Findings Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every actionable finding from the `2d054c6..714ead9` code audit without rewriting historical Phase 1B evidence or weakening release, replay, and artifact trust boundaries.

**Architecture:** Split remediation along four existing boundaries: replay recovery, immutable data/package identity, MLflow promotion, and runtime/release evidence. Reuse current Pydantic manifests, SHA-256 helpers, PostgreSQL store, MLflow client, and pytest fixtures; add no dependency or new service. Execute the existing replay subplan first, then make each remaining audit point an independently testable commit.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, PyArrow, psycopg 3/PostgreSQL 17, aiokafka/Kafka 4, MLflow 3, Prometheus, pytest/pytest-asyncio, Ruff, mypy, Docker Compose, PowerShell.

## Global Constraints

- Execute in an isolated worktree created with `superpowers:using-git-worktrees`; do not edit the active `fix/data-pipeline-audit-remediation` checkout.
- Pin the implementation base before editing; this plan was written against `714ead9573d4e2c84f83c7f2cf171f988fca4d31`.
- Preserve `docs/results/phase-1b-*`, `data/processed/phase1b/**`, and `artifacts/phase1b/phase1b-run-6050e71c7543/**` byte-for-byte.
- Treat Phase 1B hashes as immutable constants: contract `149e164748522fe6dfa844a8de70b29ee1259122962e036ff6a563c1120047d8`, source archive `aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a`, and prepared Parquet `0c31129cc4f4be982a6aec79f448485a2674b2fe79643186737143dccfe6d42a`.
- Publish corrected contract-v2 artifacts only under Phase 1C paths.
- Never call `joblib.load` before verifying the package manifest trust anchor and the child artifact digest.
- Never mutate an MLflow registered model, version, alias, or success receipt before every attested hash matches current run tags and package bytes.
- Do not accept a self-hash as an external trust anchor; expected source, contract, manifest, or output hashes must come from a separately trusted package, CLI argument, or immutable constant.
- Preserve research truth: `NOT FEASIBLE`, `selected_model: null`, and `RESEARCH_ONLY` never become a champion alias.
- Use RED -> GREEN -> REFACTOR. End every task with an independently recoverable commit and a fresh code review.
- Maintain at least 80% branch coverage. Final gates are Ruff, format, mypy, non-integration coverage, dependency-backed integration with zero required-service skips, `docker compose config --quiet`, and `git diff --check`.

---

## Audit Finding Map

| Audit finding | Priority | Planned coverage |
|---|---:|---|
| Phase 1B contract was replaced in place and replay cannot start | P1 | Task 2 |
| Existing `champion-package-v1` artifacts were invalidated silently | P1 | Task 3 |
| Prepared-data identity can be forged by replacing Parquet plus manifest | P1 | Task 4 |
| Reproduction executes an unverified `detector.joblib` | P1 | Task 5 |
| PyFunc is not logged under the candidate run | P1 | Task 5 |
| Promotion does not compare mutable run tags with the attestation | P1 | Task 6 |
| Initial replay recovery skips the range-start row | P1 | Replay subplan |
| Recovered replay publishes no terminal status | P1 | Replay subplan |
| PAUSE and STOP are not durable | P1 | Replay subplan |
| Existing alerts have no runtime-state backfill/fallback | P2 | Task 7 |
| Worker drift reference is not bound to the active package | P2 | Task 8 |
| Malformed dependency receipts crash certification | P2 | Task 9 |
| Phase 1C documentation claims hashes absent from its JSON | P2 | Task 9 |
| Fresh CI can skip MLflow integration tests | P2 | Task 9 |
| `git diff --check` fails on committed whitespace | P3 | Task 9 |

## File Structure

- Existing subplan `docs/superpowers/plans/2026-08-30-replay-recovery-audit-remediation.md`: lossless replay restart, terminal statuses, and durable control state.
- Modify `src/industrial_reliability/phase1b_contracts.py`: distinguish immutable Phase 1B hashes from executable Phase 1C contract-v2.
- Modify `src/industrial_reliability/phase1b_data.py`, `phase1b_features.py`, `phase1b_benchmark.py`, and their tests: use the Phase 1C contract explicitly and publish complete provenance.
- Modify `src/industrial_reliability/package_champion.py` and `package_research_candidate.py`: publish `champion-package-v2` with prepared Parquet identity.
- Modify `scripts/build_research_candidate.ps1`: detect and recoverably replace stale package schemas instead of skipping them.
- Modify `src/industrial_reliability/artifact_integrity.py`, `replay.py`, `replay_service.py`, and `compose.yaml`: verify Parquet bytes against external package identity.
- Modify `src/industrial_reliability/ml_lifecycle.py`: verify child artifacts, log the PyFunc under the candidate run, and compare promotion tags with the gate.
- Modify `src/industrial_reliability/persistence.py`: reconstruct and persist runtime alert state once for databases upgraded from migrations 001-003.
- Modify `src/industrial_reliability/drift.py` and `worker.py`: bind drift identity and feature order to the scoring package.
- Modify `src/industrial_reliability/release_certification.py`, `.github/workflows/ci.yml`, `README.md`, generated Phase 1C results, and whitespace-only affected files: fail closed and publish truthful evidence.
- Add focused tests only to existing test modules; create no new test framework or helper layer.

---

### Task 1: Execute the replay recovery subplan

**Files:**
- Plan: `docs/superpowers/plans/2026-08-30-replay-recovery-audit-remediation.md`
- Modify/Test: exactly the files enumerated by that subplan

**Interfaces:**
- Consumes: current `ReplayCheckpoint`, `RuntimeStore`, `ReplaySource`, and `ReplayService` contracts.
- Produces: `ReplayCheckpointState`; `RuntimeStore.update_replay_checkpoint_state(...)`; lossless zero-event recovery; durable PAUSED/STOPPED states; recovered COMPLETED/FAILED statuses.
- Guarantees: Task 4 can tighten replay source identity without changing recovery semantics.

- [ ] **Step 1: Verify the replay subplan base and scope**

Run:

```powershell
git rev-parse HEAD
git status --short
Get-Content -Raw docs/superpowers/plans/2026-08-30-replay-recovery-audit-remediation.md
```

Expected: the worktree is isolated and clean; the plan contains Tasks 1-3 for zero-event recovery, terminal status publication, durable PAUSE/RESUME/STOP, and live PostgreSQL/Kafka proof.

- [ ] **Step 2: Execute every replay subplan checkbox with its RED/GREEN commands**

Use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Do not copy the steps into this master plan; the linked subplan is the complete implementation contract for this independent subsystem.

- [ ] **Step 3: Record the replay subplan result**

Run:

```powershell
git log --oneline --max-count=4
.\.venv\Scripts\python.exe -m pytest tests/test_persistence.py tests/test_replay.py tests/test_replay_service.py -q
```

Expected: the three replay commits from the subplan are present and the selected tests PASS.

---

### Task 2: Separate immutable Phase 1B identity from executable Phase 1C

**Files:**
- Modify: `src/industrial_reliability/phase1b_contracts.py:1-270`
- Modify: `src/industrial_reliability/phase1b_data.py`
- Modify: `src/industrial_reliability/phase1b_features.py`
- Modify: `src/industrial_reliability/phase1b_benchmark.py`
- Modify: `src/industrial_reliability/online_features.py`
- Modify: `src/industrial_reliability/ml_lifecycle.py`
- Modify: `src/industrial_reliability/replay.py:183-199`
- Modify: `src/industrial_reliability/replay_service.py:487-514`
- Modify: `compose.yaml:75-105`
- Test: `tests/test_phase1b_contracts.py`
- Test: `tests/test_online_features.py`
- Test: `tests/test_replay.py`
- Test: `tests/test_replay_service.py`
- Test: `tests/integration/test_phase7_reproducibility.py`

**Interfaces:**
- Produces: `PHASE1B_CONTRACT_SHA256`, `PHASE1B_SOURCE_DATASET_SHA256`, `PHASE1B_PREPARED_OUTPUT_SHA256`, `PHASE1C`, and `metropt3_contract_manifest(contract: Phase1BContract = PHASE1C) -> dict[str, object]`.
- Changes: `ReplaySource.__init__(parquet_path: Path, expected_contract_sha256: str, clock: Callable[[], datetime] | None = None)` requires an explicit contract hash.
- Guarantees: historical Phase 1B files remain readable only under their immutable hash; all new offline generation uses Phase 1C.

- [ ] **Step 1: Write contract-version separation regressions**

Add to `tests/test_phase1b_contracts.py`:

```python
def test_phase1b_identity_constants_match_immutable_artifacts() -> None:
    assert PHASE1B_CONTRACT_SHA256 == (
        "149e164748522fe6dfa844a8de70b29ee1259122962e036ff6a563c1120047d8"
    )
    assert PHASE1B_SOURCE_DATASET_SHA256 == (
        "aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a"
    )
    assert PHASE1B_PREPARED_OUTPUT_SHA256 == (
        "0c31129cc4f4be982a6aec79f448485a2674b2fe79643186737143dccfe6d42a"
    )


def test_phase1c_is_the_only_executable_contract_v2() -> None:
    manifest = metropt3_contract_manifest(PHASE1C)
    assert PHASE1C.contract_version == "phase1b-contract-v2"
    assert manifest["contract_sha256"] == (
        "31f8689256951067e28c9cbb48a930c1617d8eea8c7133ba1a315f632842e1ad"
    )
    assert manifest["contract_sha256"] != PHASE1B_CONTRACT_SHA256
```

Add to `tests/test_replay.py`:

```python
def test_repository_phase1b_parquet_requires_explicit_legacy_contract() -> None:
    source = ReplaySource(
        Path("data/processed/phase1b/metropt3/telemetry.parquet"),
        expected_contract_sha256=PHASE1B_CONTRACT_SHA256,
    )
    assert source.identity.contract_sha256 == PHASE1B_CONTRACT_SHA256
```

- [ ] **Step 2: Run the version tests and observe RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase1b_contracts.py::test_phase1b_identity_constants_match_immutable_artifacts tests/test_phase1b_contracts.py::test_phase1c_is_the_only_executable_contract_v2 tests/test_replay.py::test_repository_phase1b_parquet_requires_explicit_legacy_contract -v
```

Expected: collection FAILS because the constants and `PHASE1C` do not exist; the repository replay test currently fails with the v2/v1 mismatch.

- [ ] **Step 3: Define historical identity constants and rename the executable contract**

In `phase1b_contracts.py`, add these constants immediately above the current contract instance:

```python
PHASE1B_CONTRACT_SHA256 = "149e164748522fe6dfa844a8de70b29ee1259122962e036ff6a563c1120047d8"
PHASE1B_SOURCE_DATASET_SHA256 = "aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a"
PHASE1B_PREPARED_OUTPUT_SHA256 = "0c31129cc4f4be982a6aec79f448485a2674b2fe79643186737143dccfe6d42a"
```

Mechanically rename only the existing constructor assignment token from:

```python
PHASE1B = Phase1BContract(
```

to:

```python
PHASE1C = Phase1BContract(
```

Do not alter any constructor argument in that mechanical rename; the current object already contains the complete contract-v2 values.

Replace `phase1b_contract_manifest` with the generic function and retain a temporary compatibility wrapper only for callers migrated in this task:

```python
def metropt3_contract_manifest(
    contract: Phase1BContract = PHASE1C,
) -> dict[str, object]:
    manifest_without_hash = cast(dict[str, object], _serialize(asdict(contract)))
    payload = json.dumps(
        manifest_without_hash,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **manifest_without_hash,
        "contract_sha256": hashlib.sha256(payload).hexdigest(),
    }
```

Do not create a fake reconstructable `PHASE1B` contract-v1 object: its historical manifest schema did not contain the new v2 fields.

- [ ] **Step 4: Move executable offline callers to Phase 1C**

Replace imports/usages of `PHASE1B` with `PHASE1C` in these exact files, and replace `phase1b_contract_manifest()` with `metropt3_contract_manifest(PHASE1C)`:

```text
src/industrial_reliability/ml_lifecycle.py
src/industrial_reliability/online_features.py
src/industrial_reliability/phase1b_benchmark.py
src/industrial_reliability/phase1b_data.py
src/industrial_reliability/phase1b_features.py
tests/integration/test_phase7_reproducibility.py
tests/test_online_features.py
tests/test_phase1b_benchmark.py
tests/test_phase1b_contracts.py
tests/test_phase1b_data.py
tests/test_phase1b_features.py
```

Use this exact default pattern:

```python
def build_phase1b_features(
    prepared_dir: Path,
    output_path: Path,
    contract: Phase1BContract = PHASE1C,
) -> Phase1BFeatureManifest:
    contract_manifest = metropt3_contract_manifest(contract)
```

Keep public function names for CLI compatibility; paths and manifest identity distinguish Phase 1C output.

- [ ] **Step 5: Remove the unsafe replay default**

In `ReplaySource.__init__`, make `expected_contract_sha256` required and delete the call to `phase1b_contract_manifest()`:

```python
def __init__(
    self,
    parquet_path: Path,
    expected_contract_sha256: str,
    clock: Callable[[], datetime] | None = None,
) -> None:
    self.path = parquet_path.resolve()
    if not self.path.is_file():
        raise FileNotFoundError(f"Parquet source not found: {self.path}")
    self.identity = verify_prepared_parquet(
        self.path,
        expected_contract_sha256=expected_contract_sha256,
    )
    self.clock = clock if clock is not None else (lambda: datetime.now(UTC))
```

In `replay_service.main`, require the environment value for non-certification startup:

```python
expected_contract_sha = os.environ.get("REPLAY_EXPECTED_CONTRACT_SHA256", "").strip()
if not expected_contract_sha:
    raise ValueError("REPLAY_EXPECTED_CONTRACT_SHA256 must be set")
source = ReplaySource(
    args.parquet.resolve(),
    expected_contract_sha256=expected_contract_sha,
)
```

Add to `replay-producer.environment` in `compose.yaml`:

```yaml
REPLAY_EXPECTED_CONTRACT_SHA256: ${REPLAY_EXPECTED_CONTRACT_SHA256:-149e164748522fe6dfa844a8de70b29ee1259122962e036ff6a563c1120047d8}
```

- [ ] **Step 6: Run Task 2 GREEN verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase1b_contracts.py tests/test_phase1b_data.py tests/test_phase1b_features.py tests/test_phase1b_benchmark.py tests/test_online_features.py tests/test_replay.py tests/test_replay_service.py tests/integration/test_phase7_reproducibility.py -q
.\.venv\Scripts\python.exe -m mypy src
docker compose config --quiet
git diff -- docs/results/phase-1b-metrics.json docs/results/phase-1b-metropt3-fresh-validation.md
```

Expected: tests and mypy PASS, Compose renders, and the historical Phase 1B result diff is empty.

- [ ] **Step 7: Commit Task 2**

```powershell
git add compose.yaml src/industrial_reliability/phase1b_contracts.py src/industrial_reliability/phase1b_data.py src/industrial_reliability/phase1b_features.py src/industrial_reliability/phase1b_benchmark.py src/industrial_reliability/online_features.py src/industrial_reliability/ml_lifecycle.py src/industrial_reliability/replay.py src/industrial_reliability/replay_service.py tests/test_phase1b_contracts.py tests/test_phase1b_data.py tests/test_phase1b_features.py tests/test_phase1b_benchmark.py tests/test_online_features.py tests/test_replay.py tests/test_replay_service.py tests/integration/test_phase7_reproducibility.py
git commit -m "fix: separate phase1b and phase1c identity"
```

---

### Task 3: Version the scoring package and rebuild stale local packages safely

**Files:**
- Modify: `src/industrial_reliability/package_champion.py:28-106,330-397`
- Modify: `src/industrial_reliability/package_research_candidate.py:44-132`
- Modify: `src/industrial_reliability/champion.py:91-160`
- Modify: `scripts/build_research_candidate.ps1`
- Test: `tests/test_package_champion.py`
- Test: `tests/test_champion.py`
- Test: `tests/test_portfolio_demo_scripts.py`

**Interfaces:**
- Produces: `ChampionManifest.schema_version == "champion-package-v2"` and required `prepared_output_sha256: str`.
- Produces: `python -m industrial_reliability.package_champion --verify-package <path>` exit code `0` only for a complete v2 package while preserving the current build CLI.
- Guarantees: stale v1 packages are moved to a timestamped sibling before v2 rebuild; no package is deleted in place.

- [ ] **Step 1: Write schema and stale-package regressions**

Add to `tests/test_package_champion.py`:

```python
def test_v2_manifest_binds_prepared_output() -> None:
    manifest = ChampionManifest(
        schema_version="champion-package-v2",
        source_run_id="phase1b-run-test",
        model_id="statistical",
        model_version="champion-statistical-v1",
        contract_sha256="a" * 64,
        source_dataset_sha256="b" * 64,
        prepared_output_sha256="c" * 64,
        feature_output_sha256="d" * 64,
        feature_names=("tp2_mean",),
        threshold=1.0,
        threshold_provenance=ThresholdProvenance(),
        artifact_sha256={
            DETECTOR_FILENAME: "e" * 64,
            BASELINE_FILENAME: "f" * 64,
            GOLDEN_CASES_FILENAME: "1" * 64,
            DRIFT_REFERENCE_FILENAME: "2" * 64,
        },
    )
    assert manifest.prepared_output_sha256 == "c" * 64


def test_v1_manifest_is_reported_as_stale() -> None:
    legacy = json.loads(
        Path("artifacts/research-candidate/manifest.json").read_text(encoding="utf-8")
    )
    assert legacy["schema_version"] == "champion-package-v1"
    with pytest.raises(ValidationError, match="champion-package-v2"):
        ChampionManifest.model_validate(legacy)
```

Add to `tests/test_portfolio_demo_scripts.py`:

```python
def test_research_package_builder_preserves_stale_package() -> None:
    script = Path("scripts/build_research_candidate.ps1").read_text(encoding="utf-8")
    assert "champion-package-v2" in script
    assert "Move-Item -LiteralPath $packageDir -Destination $backupDir" in script
    assert "Remove-Item" not in script
```

- [ ] **Step 2: Run schema tests RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_package_champion.py::test_v2_manifest_binds_prepared_output tests/test_package_champion.py::test_v1_manifest_is_reported_as_stale tests/test_portfolio_demo_scripts.py::test_research_package_builder_preserves_stale_package -v
```

Expected: FAIL because the current model still declares v1, lacks `prepared_output_sha256`, and the script only checks file existence.

- [ ] **Step 3: Publish package schema v2**

Change the manifest fields in `package_champion.py`:

```python
class ChampionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["champion-package-v2"] = "champion-package-v2"
    # Keep the current role/verdict/model fields.
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    prepared_output_sha256: str = Field(pattern=HEX_64_PATTERN)
    feature_output_sha256: str = Field(pattern=HEX_64_PATTERN)
```

Populate it in both package builders from the already verified run manifest:

```python
prepared_output_sha256 = (run["prepared_output_sha256"],)
feature_output_sha256 = (run["feature_output_sha256"],)
```

For the champion builder use `champion["prepared_output_sha256"]`; add that field to the Phase 1C champion manifest in `phase1b_benchmark.py` when a feasible model exists.

- [ ] **Step 4: Add a package verification CLI without loading pickle**

Add to `package_champion.py`:

```python
def verify_package_files(package_dir: Path) -> ChampionManifest:
    resolved = package_dir.resolve()
    manifest_path = resolved / MANIFEST_FILENAME
    manifest = ChampionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    for name, expected in manifest.artifact_sha256.items():
        child = _resolve_path(resolved, name)
        if not child.is_file() or sha256_file(child) != expected:
            raise ChampionPackageError(f"{name} missing or SHA-256 mismatch")
    return manifest
```

Change `main` to `main(argv: list[str] | None = None) -> int`. Add this optional argument before the existing build arguments and make the three existing build arguments optional at parse time:

```python
parser.add_argument("--verify-package", type=Path)
parser.add_argument("--run-dir", type=Path)
parser.add_argument("--features", type=Path)
parser.add_argument("--output-dir", type=Path)
```

Immediately after parsing, use this exact branch:

```python
if args.verify_package is not None:
    verify_package_files(args.verify_package)
    print("champion-package-v2 verified")
    return 0
if args.run_dir is None or args.features is None or args.output_dir is None:
    parser.error("--run-dir, --features, and --output-dir are required for build")
result = build_champion_package(args.run_dir, args.features, args.output_dir)
print(f"Successfully built champion package at {result.output_dir}")
print(f"Trust anchor manifest SHA-256: {result.manifest_sha256}")
return 0
```

Pass `argv` to `parser.parse_args(argv)`. The existing build command remains valid. Do not call `joblib.load` in verification mode.

- [ ] **Step 5: Make the PowerShell builder preserve then replace stale packages**

Replace `scripts/build_research_candidate.ps1` with this control flow while retaining the existing build arguments:

```powershell
$ErrorActionPreference = "Stop"
$packageDir = "artifacts/research-candidate"
$manifest = Join-Path $packageDir "manifest.json"
$valid = $false
if (Test-Path -LiteralPath $manifest) {
  $schema = (Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json).schema_version
  if ($schema -eq "champion-package-v2") {
    python -m industrial_reliability.package_champion --verify-package $packageDir
    if ($LASTEXITCODE -ne 0) { throw "v2 research package verification failed" }
    $valid = $true
  }
}
if (-not $valid) {
  if (Test-Path -LiteralPath $packageDir) {
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $backupDir = "$packageDir.legacy-$stamp"
    Move-Item -LiteralPath $packageDir -Destination $backupDir
  }
  python -m industrial_reliability.package_research_candidate `
    --run-dir artifacts/phase1b/phase1b-run-6050e71c7543 `
    --features data/processed/phase1b/features.parquet `
    --feature-manifest data/processed/phase1b/feature_manifest.json `
    --output-dir $packageDir
}
(Get-FileHash -Algorithm SHA256 -LiteralPath $manifest).Hash.ToLowerInvariant()
```

The legacy directory is recoverable evidence; do not automatically delete it.

- [ ] **Step 6: Run Task 3 GREEN verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_package_champion.py tests/test_champion.py tests/test_portfolio_demo_scripts.py -q
.\.venv\Scripts\python.exe -m industrial_reliability.package_champion --verify-package artifacts/research-candidate
```

Expected: tests PASS. The final command either verifies an already rebuilt v2 package or fails explicitly before the builder script is run; it must never accept v1 as v2.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src/industrial_reliability/package_champion.py src/industrial_reliability/package_research_candidate.py src/industrial_reliability/phase1b_benchmark.py src/industrial_reliability/champion.py scripts/build_research_candidate.ps1 tests/test_package_champion.py tests/test_champion.py tests/test_portfolio_demo_scripts.py
git commit -m "fix: version scoring package identity"
```

---

### Task 4: Authenticate prepared Parquet bytes with external package identity

**Files:**
- Modify: `src/industrial_reliability/artifact_integrity.py:19-69`
- Modify: `src/industrial_reliability/replay.py:183-272`
- Modify: `src/industrial_reliability/replay_service.py:487-514`
- Modify: `compose.yaml:75-105`
- Test: `tests/test_artifact_integrity.py`
- Test: `tests/test_replay.py`
- Test: `tests/test_replay_service.py`

**Interfaces:**
- Changes: `verify_prepared_parquet(path: Path, *, expected_contract_sha256: str, expected_source_dataset_sha256: str, expected_output_sha256: str) -> PreparedArtifactIdentity`.
- Changes: `ReplaySource` accepts all three external expected hashes.
- Consumes: Task 3 `ChampionManifest.prepared_output_sha256`.
- Guarantees: changing Parquet and recomputing its companion manifest still fails against package-bound bytes.

- [ ] **Step 1: Write coordinated-replacement tamper tests**

Add to `tests/test_artifact_integrity.py`:

```python
def test_coordinated_parquet_and_manifest_replacement_fails_external_anchor(
    tmp_path: Path,
) -> None:
    parquet = tmp_path / "telemetry.parquet"
    parquet.write_bytes(b"approved")
    source_sha = "a" * 64
    contract_sha = "b" * 64
    approved_sha = hashlib.sha256(b"approved").hexdigest()
    _create_self_hashed_manifest_file(
        tmp_path / "manifest.json",
        {
            "archive_sha256": source_sha,
            "contract_sha256": contract_sha,
            "output_sha256": approved_sha,
        },
    )

    parquet.write_bytes(b"replacement")
    replacement_sha = hashlib.sha256(b"replacement").hexdigest()
    _create_self_hashed_manifest_file(
        tmp_path / "manifest.json",
        {
            "archive_sha256": source_sha,
            "contract_sha256": contract_sha,
            "output_sha256": replacement_sha,
        },
    )

    with pytest.raises(ArtifactIntegrityError, match="expected prepared output"):
        verify_prepared_parquet(
            parquet,
            expected_contract_sha256=contract_sha,
            expected_source_dataset_sha256=source_sha,
            expected_output_sha256=approved_sha,
        )
```

- [ ] **Step 2: Run the tamper test RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_integrity.py::test_coordinated_parquet_and_manifest_replacement_fails_external_anchor -v
```

Expected: FAIL because the current verifier trusts the replacement digest from the replacement manifest.

- [ ] **Step 3: Require external expected identity**

Replace `verify_prepared_parquet` with:

```python
def verify_prepared_parquet(
    path: Path,
    *,
    expected_contract_sha256: str,
    expected_source_dataset_sha256: str,
    expected_output_sha256: str,
) -> PreparedArtifactIdentity:
    manifest = load_self_hashed_manifest(path.with_name("manifest.json"))
    contract = str(manifest.get("contract_sha256", ""))
    source = str(manifest.get("archive_sha256", ""))
    declared_output = str(manifest.get("output_sha256", ""))
    if contract != expected_contract_sha256:
        raise ArtifactIntegrityError(
            f"prepared contract SHA-256 mismatch: expected {expected_contract_sha256}, got {contract}"
        )
    if source != expected_source_dataset_sha256:
        raise ArtifactIntegrityError(
            f"prepared source SHA-256 mismatch: expected {expected_source_dataset_sha256}, got {source}"
        )
    if declared_output != expected_output_sha256:
        raise ArtifactIntegrityError(
            f"expected prepared output SHA-256 {expected_output_sha256}, got {declared_output}"
        )
    parquet_sha = verify_file_sha256(path, expected_output_sha256, "telemetry.parquet")
    return PreparedArtifactIdentity(
        source_dataset_sha256=source,
        contract_sha256=contract,
        parquet_sha256=parquet_sha,
        manifest_sha256=str(manifest["manifest_sha256"]),
    )
```

- [ ] **Step 4: Load replay expectations from package v2**

In `replay_service.main`, read the mounted package manifest before constructing the source:

```python
package_manifest_path = Path(
    os.environ.get(
        "REPLAY_PACKAGE_MANIFEST",
        "/runtime/scoring-package/manifest.json",
    )
)
package_manifest = ChampionManifest.model_validate_json(
    package_manifest_path.read_text(encoding="utf-8")
)
source = ReplaySource(
    args.parquet.resolve(),
    expected_contract_sha256=package_manifest.contract_sha256,
    expected_source_dataset_sha256=package_manifest.source_dataset_sha256,
    expected_output_sha256=package_manifest.prepared_output_sha256,
)
```

Update `ReplaySource.__init__` to forward these three keyword-only arguments. Add to Compose:

```yaml
REPLAY_PACKAGE_MANIFEST: /runtime/scoring-package/manifest.json
```

Remove `REPLAY_EXPECTED_CONTRACT_SHA256` added in Task 2 after package-bound identity is active.

- [ ] **Step 5: Update offline boundary callers explicitly**

For Phase 1C preparation consumers, pass values from the separately retained preparation result or run manifest; never read the expected output only from the companion manifest. Update tests to pass their fixture hashes as explicit keyword arguments.

Change the feature builder signature to:

```python
def build_phase1b_features(
    prepared_dir: Path,
    output_path: Path,
    expected_prepared_output_sha256: str,
    contract: Phase1BContract = PHASE1C,
) -> Phase1BFeatureManifest:
```

Add required CLI `--prepared-output-sha256` and pass it into the function. Use this call shape in feature generation:

```python
prep_identity = verify_prepared_parquet(
    parquet_file,
    expected_contract_sha256=expected_contract_sha,
    expected_source_dataset_sha256=contract.archive_sha256,
    expected_output_sha256=expected_prepared_output_sha256,
)
```

Change the benchmark signature to:

```python
def run_phase1b_benchmark(
    prepared_dir: Path,
    feature_path: Path,
    artifact_dir: Path,
    expected_prepared_output_sha256: str,
    contract: Phase1BContract = PHASE1C,
) -> Phase1BBenchmarkResult:
```

Add the same required CLI `--prepared-output-sha256`, pass it into the benchmark, and verify prepared bytes with the contract archive hash plus this external output hash. Update every unit/integration caller using the fixture Parquet digest already returned or computed by that fixture.

- [ ] **Step 6: Run Task 4 GREEN verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_artifact_integrity.py tests/test_replay.py tests/test_replay_service.py tests/test_phase1b_features.py tests/test_phase1b_benchmark.py -q
docker compose config --quiet
```

Expected: all tests PASS and coordinated replacement fails before Parquet is read.

- [ ] **Step 7: Commit Task 4**

```powershell
git add compose.yaml src/industrial_reliability/artifact_integrity.py src/industrial_reliability/replay.py src/industrial_reliability/replay_service.py src/industrial_reliability/phase1b_features.py src/industrial_reliability/phase1b_benchmark.py tests/test_artifact_integrity.py tests/test_replay.py tests/test_replay_service.py tests/test_phase1b_features.py tests/test_phase1b_benchmark.py
git commit -m "fix: bind replay to prepared bytes"
```

---

### Task 5: Verify executable ML artifacts and log the candidate model atomically

**Files:**
- Modify: `src/industrial_reliability/ml_lifecycle.py:181-294,297-438`
- Test: `tests/test_ml_lifecycle.py`
- Test: `tests/integration/test_mlflow_candidate.py`

**Interfaces:**
- Consumes: `load_champion(package_dir, expected_manifest_sha256, allow_research_candidate=True) -> ChampionScorer`.
- Produces: candidate run artifact `champion-model` at `runs:/<candidate_run_id>/champion-model`.
- Guarantees: detector bytes are verified before deserialization; a failed model log fails candidate import instead of returning an unusable URI.

- [ ] **Step 1: Write detector tamper and real-MLflow artifact regressions**

Add to `tests/test_ml_lifecycle.py`:

```python
def test_reproduction_rejects_tampered_detector_before_joblib_load(tmp_path: Path) -> None:
    run_dir, features, package = _create_mock_feasible_phase1b_run(tmp_path)
    detector = package / "detector.joblib"
    detector.write_bytes(detector.read_bytes() + b"tamper")
    with (
        patch("industrial_reliability.ml_lifecycle.joblib.load") as unsafe_load,
        pytest.raises(ChampionIntegrityError, match="detector.joblib SHA-256 mismatch"),
    ):
        reproduce_candidate(
            ReproductionRequest(features, run_dir, package),
            mlflow_client=FakeMlflowClient(),
        )
    unsafe_load.assert_not_called()
```

Add to `tests/integration/test_mlflow_candidate.py`:

```python
import mlflow


@pytest.mark.integration
def test_candidate_run_contains_downloadable_pyfunc(tmp_path: Path) -> None:
    run_dir, _features, package = _setup_test_run(tmp_path)
    tracking_uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    result = import_candidate(ImportCandidateRequest(package, run_dir, tracking_uri=tracking_uri))
    mlflow.set_tracking_uri(tracking_uri)
    downloaded = mlflow.artifacts.download_artifacts(
        artifact_uri=f"runs:/{result.run_id}/champion-model"
    )
    assert Path(downloaded, "MLmodel").is_file()
```

- [ ] **Step 2: Run both tests RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ml_lifecycle.py::test_reproduction_rejects_tampered_detector_before_joblib_load tests/integration/test_mlflow_candidate.py::test_candidate_run_contains_downloadable_pyfunc -v
```

Expected: the first test shows `joblib.load` is reachable without child verification; the second fails to download `champion-model`.

- [ ] **Step 3: Reuse `load_champion` in reproduction**

Replace direct detector loading with:

```python
scorer = load_champion(
    request.champion_package,
    expected_manifest_sha256=pkg_manifest_sha,
    allow_research_candidate=True,
)
detector = scorer.detector
```

Delete the direct detector path check and `joblib.load(detector_file)` from `reproduce_candidate`. Keep `joblib` where still used by training/import code; remove the import only if Ruff proves it unused.

- [ ] **Step 4: Log under the exact candidate run and propagate failure**

Replace the suppressed model log in `import_candidate` with:

```python
if mlflow_client is None:
    assert mlflow is not None
    with mlflow.start_run(run_id=run_id):
        mlflow.pyfunc.log_model(
            artifact_path="champion-model",
            python_model=PackagedChampionPyFunc(expected_manifest_sha256=pkg_manifest_sha),
            artifacts={"champion_package": str(request.champion_package.resolve())},
        )
```

Do not suppress exceptions. Fake-client unit tests pass `mlflow_client` and do not attempt a global MLflow log; the real integration test proves the production branch.

- [ ] **Step 5: Run Task 5 GREEN verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ml_lifecycle.py tests/integration/test_mlflow_candidate.py -q
.\.venv\Scripts\python.exe -m ruff check src/industrial_reliability/ml_lifecycle.py tests/test_ml_lifecycle.py tests/integration/test_mlflow_candidate.py
```

Expected: tests and Ruff PASS; the integration test downloads `MLmodel` from the returned candidate run.

- [ ] **Step 6: Commit Task 5**

```powershell
git add src/industrial_reliability/ml_lifecycle.py tests/test_ml_lifecycle.py tests/integration/test_mlflow_candidate.py
git commit -m "fix: verify and log candidate model"
```

---

### Task 6: Bind promotion to attested run tags before registry mutation

**Files:**
- Modify: `src/industrial_reliability/ml_lifecycle.py:441-555`
- Test: `tests/test_ml_lifecycle.py`
- Test: `tests/integration/test_mlflow_promotion.py`

**Interfaces:**
- Produces: `_validate_promotion_identity(tags: Mapping[str, str], gate: Phase7GateResult, manifest: ChampionManifest, manifest_sha: str) -> None`.
- Guarantees: dataset, contract, feature schema, source Git, package, and alert-policy hashes match across current run tags, gate `verified_hashes`, and package bytes before `create_registered_model`.

- [ ] **Step 1: Add parameterized mutable-tag regressions**

Add to `tests/test_ml_lifecycle.py`:

```python
@pytest.mark.parametrize(
    "tag",
    [
        "dataset_sha256",
        "contract_sha256",
        "feature_schema_sha256",
        "champion_package_sha256",
        "alert_policy_sha256",
    ],
)
def test_promotion_rejects_run_tag_changed_after_attestation(
    tmp_path: Path,
    tag: str,
) -> None:
    run_dir, _features, package = _create_mock_feasible_phase1b_run(tmp_path)
    client = FakeMlflowClient()
    candidate = import_candidate(
        ImportCandidateRequest(package, run_dir),
        mlflow_client=client,
    )
    gate_path = tmp_path / "phase7-gate.json"
    _create_mock_gate_attestation_file(
        gate_path,
        candidate.run_id,
        package_manifest_sha256=candidate.package_manifest_sha256,
        source_git_sha=candidate.provenance.source_git_sha,
        alert_policy_sha256=candidate.provenance.alert_policy_sha256,
    )
    client.tags[candidate.run_id][tag] = "f" * 64

    with pytest.raises(ValueError, match=tag):
        promote_candidate(
            PromotionRequest(
                run_id=candidate.run_id,
                approver="reliability-lead",
                expected_source_git_sha=candidate.provenance.source_git_sha,
                output=tmp_path / "receipt.json",
                champion_package=package,
                phase7_gate=gate_path,
            ),
            mlflow_client=client,
        )
    assert client.model_versions == {}
    assert client.aliases == {}
```

- [ ] **Step 2: Run tag tests RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ml_lifecycle.py::test_promotion_rejects_run_tag_changed_after_attestation -v
```

Expected: every case currently promotes or reaches registry mutation instead of raising for the changed tag.

- [ ] **Step 3: Add the complete identity validator**

Add above `promote_candidate`:

```python
def _validate_promotion_identity(
    tags: Mapping[str, str],
    gate: Phase7GateResult,
    manifest: ChampionManifest,
    manifest_sha: str,
) -> None:
    expected = {
        "dataset_sha256": manifest.source_dataset_sha256,
        "contract_sha256": manifest.contract_sha256,
        "feature_schema_sha256": canonical_sha256({"features": list(manifest.feature_names)}),
        "source_git_sha": gate.source_git_sha,
        "champion_package_sha256": manifest_sha,
        "alert_policy_sha256": gate.alert_policy_sha256,
    }
    for name, value in expected.items():
        if tags.get(name) != value:
            raise ValueError(f"{name} run tag does not match attested identity")
        if gate.verified_hashes.get(name) != value:
            raise ValueError(f"{name} Phase 7 hash does not match attested identity")
```

Import `Phase7GateResult` under `TYPE_CHECKING` or annotate with a forward string to avoid the existing circular import.

- [ ] **Step 4: Call validation before any registry API**

After loading the gate and manifest, and before `client.create_registered_model`, call:

```python
_validate_promotion_identity(tags, gate, manifest, manifest_sha)
```

Build the promotion receipt from validated manifest/gate values, not fallback zeros or untrusted tags:

```python
dataset_sha256 = manifest.source_dataset_sha256
contract_sha256 = manifest.contract_sha256
champion_package_sha256 = manifest_sha
```

- [ ] **Step 5: Run Task 6 GREEN verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ml_lifecycle.py tests/integration/test_mlflow_promotion.py -q
```

Expected: all tests PASS; every invalid precondition leaves model versions, aliases, and receipts empty.

- [ ] **Step 6: Commit Task 6**

```powershell
git add src/industrial_reliability/ml_lifecycle.py tests/test_ml_lifecycle.py tests/integration/test_mlflow_promotion.py
git commit -m "fix: bind promotion to attested tags"
```

---

### Task 7: Recover alert runtime state during database upgrade

**Files:**
- Modify: `src/industrial_reliability/persistence.py:1-459`
- Modify: `src/industrial_reliability/alert_consumer.py:108-115`
- Test: `tests/test_persistence.py`
- Test: `tests/test_alert_consumer.py`
- Test: `tests/integration/test_alert_persistence.py`

**Interfaces:**
- Produces: `RuntimeStore._reconstruct_alert_state(cur: psycopg.Cursor[Any], replay_session_id: UUID, machine_id: str, policy: LockedAlertPolicyV1) -> AlertState`.
- Changes: `load_alert_state(replay_session_id: UUID, machine_id: str, policy: LockedAlertPolicyV1 | None = None) -> AlertState` reconstructs once by replaying persisted decisions when migration 004 has no state row.
- Guarantees: a populated migrations 001-003 database never silently becomes `AlertState.empty` after applying migration 004.

- [ ] **Step 1: Write pre-alert and active-alert upgrade regressions**

Add to `tests/integration/test_alert_persistence.py`:

```python
@pytest.mark.integration
@pytest.mark.parametrize("decisions_before_upgrade", [2, 3])
def test_load_alert_state_replays_legacy_decisions_exactly(
    store: RuntimeStore,
    decisions_before_upgrade: int,
) -> None:
    session_id = uuid4()
    policy = replace(_make_policy(), persistence_decisions=3, cooldown_decisions=2)
    first = _make_decision(session_id, is_anomaly=True)
    decisions = [first]
    for index in range(1, decisions_before_upgrade):
        decisions.append(
            replace(
                first,
                decision_id=uuid4(),
                window_id=uuid4(),
                source_timestamp=first.source_timestamp + timedelta(minutes=5 * index),
            )
        )
    state = AlertState.empty(session_id, "metropt3")
    for decision in decisions:
        result = transition(state, decision, policy)
        store.record_decision_transition(decision, result)
        state = result.state

    with psycopg.connect(store.db_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM alert_runtime_states WHERE replay_session_id = %s",
            (str(session_id),),
        )
        connection.commit()

    recovered = store.load_alert_state(session_id, "metropt3", policy)
    assert recovered.active_alert_id == state.active_alert_id
    assert recovered.anomaly_decision_ids == state.anomaly_decision_ids
    assert recovered.anomaly_streak == state.anomaly_streak
    assert recovered.normal_streak == state.normal_streak
    assert recovered.last_decision_id == decisions[-1].decision_id
    assert store.count("alert_runtime_states", "replay_session_id", str(session_id)) == 1
```

The two parameter cases cover pre-alert streak state and the newly opened alert state.

Add to `tests/test_persistence.py`:

```python
def test_missing_runtime_state_with_legacy_decisions_requires_policy() -> None:
    store = RuntimeStore("postgresql://test:5432/test")
    session_id = uuid4()
    connection = MagicMock()
    cursor = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.side_effect = [None, {"count": 1}]
    with (
        patch("psycopg.connect", return_value=connection),
        pytest.raises(RuntimeError, match="policy is required"),
    ):
        store.load_alert_state(session_id, "metropt3")
```

- [ ] **Step 2: Run upgrade test RED**

```powershell
$env:REQUIRE_INTEGRATION_SERVICES='1'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_alert_persistence.py::test_load_alert_state_replays_legacy_decisions_exactly tests/test_persistence.py::test_missing_runtime_state_with_legacy_decisions_requires_policy -v
```

Expected: FAIL because `load_alert_state` has no policy argument and returns `AlertState.empty` when the new table has no row.

- [ ] **Step 3: Reconstruct by replaying persisted decisions**

Import `LockedAlertPolicyV1` and `transition`, then add this private method to `RuntimeStore`:

```python
def _reconstruct_alert_state(
    self,
    cur: psycopg.Cursor[Any],
    replay_session_id: UUID,
    machine_id: str,
    policy: LockedAlertPolicyV1,
) -> AlertState:
    cur.execute(
        """
        SELECT payload
        FROM score_decisions
        WHERE replay_session_id = %s
        ORDER BY source_timestamp ASC, decision_id ASC
        """,
        (str(replay_session_id),),
    )
    state = AlertState.empty(replay_session_id, machine_id)
    for row in cur.fetchall():
        raw = row["payload"]
        payload = raw if isinstance(raw, dict) else json.loads(raw)
        decision = ScoreDecisionV1.model_validate(payload)
        state = transition(state, decision, policy).state
    return state
```

This reuses the actual state machine and locked policy, preserving pre-alert, active-alert, cooldown, and reopen semantics without duplicating them in SQL.

- [ ] **Step 4: Fail closed without a policy and persist exact reconstructed state**

Change the signature and missing-row branch:

```python
def load_alert_state(
    self,
    replay_session_id: UUID,
    machine_id: str,
    policy: LockedAlertPolicyV1 | None = None,
) -> AlertState:
    # Keep the existing runtime-row query and decode branch.
    cur.execute(
        "SELECT COUNT(*) AS count FROM score_decisions WHERE replay_session_id = %s",
        (str(replay_session_id),),
    )
    count_row = cur.fetchone()
    decision_count = int(count_row["count"]) if count_row else 0
    if decision_count == 0:
        return AlertState.empty(replay_session_id, machine_id)
    if policy is None:
        raise RuntimeError("alert policy is required to reconstruct legacy runtime state")
    state = self._reconstruct_alert_state(cur, replay_session_id, machine_id, policy)


cur.execute(
    """
    INSERT INTO alert_runtime_states (replay_session_id, machine_id, payload)
    VALUES (%s, %s, %s)
    ON CONFLICT (replay_session_id, machine_id) DO NOTHING
    """,
    (str(replay_session_id), machine_id, json.dumps(_state_payload(state))),
)
conn.commit()
return state
```

Ensure the connection variable is named `conn` in the context manager.

- [ ] **Step 5: Pass the locked policy from the alert consumer**

Replace the current call in `AlertConsumer.process` with:

```python
state = self.store.load_alert_state(
    session_id,
    self.machine_id,
    self.policy,
)
```

Update the mock assertion in `tests/test_alert_consumer.py` to expect the policy as the third argument.

- [ ] **Step 6: Run Task 7 GREEN verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_persistence.py tests/test_alert_consumer.py tests/integration/test_alert_persistence.py -q
```

Expected: tests PASS; both legacy cases exactly match state-machine output and insert one runtime-state row.

- [ ] **Step 7: Commit Task 7**

```powershell
git add src/industrial_reliability/persistence.py src/industrial_reliability/alert_consumer.py tests/test_persistence.py tests/test_alert_consumer.py tests/integration/test_alert_persistence.py
git commit -m "fix: recover legacy alert state"
```

---

### Task 8: Bind worker drift monitoring to the scoring package

**Files:**
- Modify: `src/industrial_reliability/drift.py:170-221`
- Modify: `src/industrial_reliability/worker.py:59-122,484-509`
- Test: `tests/test_drift.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Produces: `WorkerSettings.package_manifest: dict[str, Any] | None = None`; `from_env` always populates it, while existing direct test/drill constructors remain backward compatible.
- Changes: `load_reference` verifies model version, source dataset, contract, and exact feature order.
- Guarantees: the drift file first matches `artifact_sha256["drift-reference.json"]`, then matches model, dataset, contract, and feature order; a stale self-consistent reference cannot start the worker or publish PSI.

- [ ] **Step 1: Write stale-reference and feature-order regressions**

Add to `tests/test_drift.py`:

```python
def test_load_reference_rejects_feature_order_mismatch(
    tmp_path: Path,
    reference: DriftReferenceV1,
) -> None:
    path = save_reference(reference, tmp_path / "drift-reference.json")
    expected = {
        "model_version": reference.model_version,
        "source_dataset_sha256": reference.source_dataset_sha256,
        "contract_sha256": reference.contract_sha256,
        "feature_names": tuple(reversed(reference.active_feature_names)),
    }
    with pytest.raises(ValueError, match="feature order"):
        load_reference(path, expected_manifest=expected)
```

Add to `tests/test_worker.py`:

```python
from industrial_reliability.artifact_integrity import (
    ArtifactIntegrityError,
    verify_file_sha256,
)


def test_worker_settings_bind_drift_reference_to_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from industrial_reliability.drift import _compute_drift_hash, load_reference
    from tests.helpers_champion import build_research_candidate_from_mock_run

    mock = build_research_candidate_from_mock_run(tmp_path)
    drift_path = mock.package_dir / "drift-reference.json"
    data = json.loads(drift_path.read_text(encoding="utf-8"))
    data["source_dataset_sha256"] = "f" * 64
    data["self_sha256"] = ""
    data["self_sha256"] = _compute_drift_hash(data)
    drift_path.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    monkeypatch.setenv("SCORING_API_URL", "http://localhost:8000")
    monkeypatch.setenv("SCORING_PACKAGE_DIR", str(mock.package_dir))
    monkeypatch.setenv("SCORING_MANIFEST_SHA256", mock.manifest_sha256)
    monkeypatch.setenv("ALLOW_RESEARCH_CANDIDATE", "true")
    settings = WorkerSettings.from_env()
    assert settings.package_manifest is not None

    with pytest.raises(ArtifactIntegrityError, match="drift-reference.json SHA-256 mismatch"):
        verify_file_sha256(
            drift_path,
            settings.package_manifest["artifact_sha256"]["drift-reference.json"],
            "drift-reference.json",
        )
```

- [ ] **Step 2: Run drift tests RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_drift.py::test_load_reference_rejects_feature_order_mismatch tests/test_worker.py::test_worker_settings_bind_drift_reference_to_package -v
```

Expected: the feature-order mismatch is accepted and worker startup loads the drift reference without package comparison.

- [ ] **Step 3: Verify exact feature order in `load_reference`**

Extend the expected-manifest branch:

```python
expected_features = tuple(
    expected_manifest.get("feature_names") or expected_manifest.get("active_feature_names") or ()
)
if tuple(data["active_feature_names"]) != expected_features:
    raise ValueError(
        "feature order mismatch in drift reference: "
        f"expected {expected_features}, got {tuple(data['active_feature_names'])}"
    )
```

- [ ] **Step 4: Load settings before drift and pass the active manifest**

Add this final dataclass field after `group_id` so existing direct constructors remain valid:

```python
package_manifest: dict[str, Any] | None = None
```

Populate it in `from_env` with `package_manifest=manifest_data`. Import `verify_file_sha256` from `artifact_integrity`, then reorder startup in `main`:

```python
settings = WorkerSettings.from_env()
drift_ref = None
drift_ref_path = os.environ.get("DRIFT_REFERENCE_PATH", "").strip()
if drift_ref_path:
    if settings.package_manifest is None:
        raise ValueError("package manifest is required for drift reference verification")
    artifact_hashes = settings.package_manifest.get("artifact_sha256", {})
    expected_drift_sha = artifact_hashes.get("drift-reference.json")
    if not isinstance(expected_drift_sha, str):
        raise ValueError("scoring package does not bind drift-reference.json")
    verify_file_sha256(
        Path(drift_ref_path),
        expected_drift_sha,
        "drift-reference.json",
    )
    drift_ref = load_reference(
        Path(drift_ref_path),
        expected_manifest=settings.package_manifest,
    )
worker = StreamingWorker(settings, metrics=metrics, drift_reference=drift_ref)
```

The package manifest is frozen input for process startup; do not reread it later.

- [ ] **Step 5: Run Task 8 GREEN verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_drift.py tests/test_worker.py -q
```

Expected: tests PASS and mismatched references fail before the Kafka consumer starts.

- [ ] **Step 6: Commit Task 8**

```powershell
git add src/industrial_reliability/drift.py src/industrial_reliability/worker.py tests/test_drift.py tests/test_worker.py
git commit -m "fix: bind drift to scoring package"
```

---

### Task 9: Fail closed in certification and publish truthful Phase 1C evidence

**Files:**
- Modify: `src/industrial_reliability/release_certification.py:160-204`
- Modify: `src/industrial_reliability/phase1b_benchmark.py:320-400`
- Modify: `.github/workflows/ci.yml:75-93`
- Modify: `README.md:41-50`
- Regenerate: `docs/results/phase-1c-metrics.json`
- Regenerate: `docs/results/phase-1c-metropt3-validation.md`
- Modify: `db/migrations/004_alert_runtime_state.sql`
- Modify: `.orchestration/evidence/phase0-research.md`
- Modify: `.orchestration/supervisor-notebook.md`
- Test: `tests/test_release_certification.py`
- Test: `tests/test_phase1b_benchmark.py`
- Test: `tests/test_report_hashes.py`

**Interfaces:**
- Changes: malformed `dependency_receipts` returns uncertified instead of raising.
- Produces: Phase 1C metrics fields `prepared_output_sha256`, `feature_output_sha256`, and `source_git_sha`.
- Guarantees: CI installs MLflow, required integration services cannot skip, README names only fields present in JSON, and the final diff is whitespace-clean.

- [ ] **Step 1: Write malformed-receipt regression**

Add to `tests/test_release_certification.py`:

```python
@pytest.mark.parametrize("receipts", [None, "openai", {}, ["openai"]])
def test_validator_rejects_malformed_dependency_receipts(
    tmp_path: Path,
    receipts: object,
) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path)
    _write_passing_phase9_report(tmp_path)
    path = tmp_path / "phase-9-rca-openai.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["dependency_receipts"] = receipts
    report["report_sha256"] = compute_self_hash(report, "report_sha256")
    path.write_text(json.dumps(report), encoding="utf-8")
    result = ReleaseCertificationValidator(tmp_path).evaluate("a" * 40)
    assert result.is_certified is False
```

- [ ] **Step 2: Write Phase 1C provenance-field regression**

Add to `tests/test_phase1b_benchmark.py`:

```python
def test_published_phase1c_metrics_include_byte_and_code_identity(tmp_path: Path) -> None:
    run_dir = create_phase1c_run_fixture(tmp_path)
    metrics_path, _ = publish_phase1b_results(run_dir, tmp_path / "published")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["prepared_output_sha256"] == "a" * 64
    assert metrics["feature_output_sha256"] == "b" * 64
    assert metrics["source_git_sha"] == "c" * 40
```

Construct `create_phase1c_run_fixture` inside this test module by writing the current minimal `run_manifest.json` plus these three hashes; do not create another shared helper.

- [ ] **Step 3: Run certification/evidence tests RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_release_certification.py::test_validator_rejects_malformed_dependency_receipts tests/test_phase1b_benchmark.py::test_published_phase1c_metrics_include_byte_and_code_identity -v
```

Expected: malformed `None` raises `TypeError`; published metrics omit the three required fields.

- [ ] **Step 4: Validate receipt structure before iterating**

Replace receipt collection in `_verify_release_evidence` with:

```python
raw_receipts = data.get("dependency_receipts")
if not isinstance(raw_receipts, list) or not all(
    isinstance(item, dict) and isinstance(item.get("dependency"), str) for item in raw_receipts
):
    return False
receipts = {str(item["dependency"]) for item in raw_receipts}
```

- [ ] **Step 5: Propagate complete Phase 1C identity**

Add `source_git_sha: str` as a required keyword argument to `run_phase1b_benchmark`. Validate it with the existing `validate_git_sha` helper, and write these fields to `run_manifest.json`:

```python
"prepared_output_sha256": verified_data.parquet_sha256,
"feature_output_sha256": str(feature_manifest["output_sha256"]),
"source_git_sha": validate_git_sha(source_git_sha),
```

Copy the same fields into `published_metrics` in `publish_phase1b_results`.

Add required CLI option:

```python
parser.add_argument("--source-git-sha", required=True)
```

Update the Phase 1C command in `docs/RUNBOOK.md` to pass the SHA captured before the run:

```powershell
$sha = git rev-parse HEAD
python -m industrial_reliability.phase1b_benchmark `
  --prepared-dir data/processed/phase1c/metropt3 `
  --features data/processed/phase1c/features.parquet `
  --artifact-dir artifacts/phase1c `
  --publish-dir docs/results/phase1c `
  --source-git-sha $sha
```

- [ ] **Step 6: Prevent MLflow integration skips in CI**

Change the integration install step to:

```yaml
- run: pip install -e ".[dev,mlops]"
```

Keep `REQUIRE_INTEGRATION_SERVICES: "true"`. Add a pre-test import assertion:

```yaml
- run: python -c "import mlflow; print(mlflow.__version__)"
```

This makes `pytest.importorskip("mlflow")` non-skipping without a new plugin.

- [ ] **Step 7: Regenerate Phase 1C evidence and verify README claims**

Run the updated commands from `docs/RUNBOOK.md`, then copy only the versioned Phase 1C outputs:

```powershell
Copy-Item -LiteralPath docs/results/phase1c/phase-1b-metrics.json -Destination docs/results/phase-1c-metrics.json -Force
Copy-Item -LiteralPath docs/results/phase1c/phase-1b-metropt3-fresh-validation.md -Destination docs/results/phase-1c-metropt3-validation.md -Force
```

Ensure `README.md` retains the feature/code hash statement only after this command passes:

```powershell
python -c "import json; d=json.load(open('docs/results/phase-1c-metrics.json')); assert all(k in d for k in ('prepared_output_sha256','feature_output_sha256','source_git_sha'))"
```

- [ ] **Step 8: Fix only reported whitespace**

Remove the extra EOF blank line from `db/migrations/004_alert_runtime_state.sql` and `.orchestration/supervisor-notebook.md`. Remove Markdown hard-break trailing spaces from `.orchestration/evidence/phase0-research.md` by using ordinary line endings; do not reformat unrelated audit prose.

- [ ] **Step 9: Run Task 9 GREEN verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_release_certification.py tests/test_phase1b_benchmark.py tests/test_report_hashes.py -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

Expected: tests and static checks PASS; `git diff --check` prints nothing.

- [ ] **Step 10: Commit Task 9**

```powershell
git add .github/workflows/ci.yml README.md docs/RUNBOOK.md docs/results/phase-1c-metrics.json docs/results/phase-1c-metropt3-validation.md src/industrial_reliability/release_certification.py src/industrial_reliability/phase1b_benchmark.py tests/test_release_certification.py tests/test_phase1b_benchmark.py tests/test_report_hashes.py db/migrations/004_alert_runtime_state.sql .orchestration/evidence/phase0-research.md .orchestration/supervisor-notebook.md
git commit -m "fix: publish truthful release evidence"
```

---

### Task 10: Run exact-head integration, recovery, and release gates

**Files:**
- Verify only: complete committed tree
- Generated evidence: `artifacts/certification/<exact-sha>/`
- Generated recovery evidence: `artifacts/backups/<timestamp>/restore-report.json`

**Interfaces:**
- Consumes: Tasks 1-9.
- Produces: exact-head UNIT/INTEGRATION evidence and an explicit certified-or-blocked release result.
- Guarantees: no production-readiness statement is based solely on unit tests, mocks, or generated documentation.

- [ ] **Step 1: Record the candidate exact head and clean state**

```powershell
$sha = git rev-parse HEAD
git status --short
git log --oneline 714ead9573d4e2c84f83c7f2cf171f988fca4d31..HEAD
```

Expected: only intended ignored/generated artifacts are untracked; every remediation task has its own commit.

- [ ] **Step 2: Run the complete local quality gate**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -m "not slow and not integration" --cov
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
git diff --check 714ead9573d4e2c84f83c7f2cf171f988fca4d31 HEAD
```

Expected: every command exits `0`, coverage is at least 80%, and the diff check prints nothing.

- [ ] **Step 3: Start dependency-backed services and apply migrations**

```powershell
docker compose up -d --wait postgres kafka
docker compose run --rm db-migrate
$env:REQUIRE_INTEGRATION_SERVICES='true'
$env:DATABASE_URL='postgresql://irp:irp_password@localhost:5432/irp'
$env:KAFKA_BOOTSTRAP_SERVERS='localhost:29092'
```

Expected: PostgreSQL and Kafka are healthy; migrations exit `0`.

- [ ] **Step 4: Run integration with required capabilities present**

```powershell
.\.venv\Scripts\python.exe -m pytest -m integration -v -ra
```

Expected: all integration tests PASS; no required-service or MLflow test is SKIPPED.

- [ ] **Step 5: Prove backup/restore**

```powershell
.\scripts\test_postgres_restore.ps1
```

Expected: the newest `restore-report.json` contains `"verdict": "PASS"`, a nonempty dump SHA-256, and equal critical-table counts.

- [ ] **Step 6: Build the current package and run the live stack**

```powershell
$env:SCORING_MANIFEST_SHA256 = (.\scripts\build_research_candidate.ps1 | Select-Object -Last 1)
$env:ALLOW_RESEARCH_CANDIDATE = 'true'
docker compose up -d --build
docker compose ps
```

Expected: `db-migrate` completed successfully; replay producer, worker, alert service, and scoring API are running/healthy with the v2 package.

- [ ] **Step 7: Run release certification without overstating unavailable evidence**

```powershell
$artifactDir = "artifacts/certification/$sha"
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
.\.venv\Scripts\python.exe -m industrial_reliability.release_certification --artifact-dir $artifactDir --git-sha $sha
```

Expected: certification either passes with every required dependency receipt and no simulated component, or exits blocked/invalid with explicit limitations. Do not edit the report to force PASS.

- [ ] **Step 8: Stop services without deleting durable volumes**

```powershell
docker compose stop
```

Expected: containers stop and named volumes remain.

- [ ] **Step 9: Request two-stage review and record exact head**

Request spec-compliance review against this plan, then code-quality/security review against:

```powershell
git diff 714ead9573d4e2c84f83c7f2cf171f988fca4d31..HEAD
git rev-parse HEAD
```

Block completion on replay loss, unverified deserialization, identity mismatch, registry mutation before validation, migration state loss, or false evidence claims.

---

## Final Acceptance Gate

- [ ] Historical Phase 1B result/data/artifact hashes are unchanged.
- [ ] Phase 1C has a distinct executable contract and versioned paths.
- [ ] Replay source bytes match package-bound source, contract, and prepared-output hashes.
- [ ] Zero-event replay recovery includes the range-start row and publishes terminal status.
- [ ] PAUSE/RESUME/STOP survive restart without replacing the START payload or cursor.
- [ ] No `joblib.load` is reachable before child digest verification.
- [ ] Returned candidate MLflow URI downloads a real `MLmodel` from the candidate run.
- [ ] Current MLflow tags, gate hashes, and package identity all match before registry mutation.
- [ ] Legacy databases reconstruct and persist alert state instead of returning empty state.
- [ ] Worker refuses drift references with mismatched model, dataset, contract, or feature order.
- [ ] Malformed certification receipts return uncertified and never raise.
- [ ] Phase 1C JSON actually contains every hash claimed by README.
- [ ] CI installs `mlops`; required integration tests report zero skips.
- [ ] Ruff, format, mypy, coverage, build, Compose config, and `git diff --check` pass at exact head.
- [ ] Integration, restore, and release evidence levels are reported separately from UNIT/IN_PROCESS results.

## Self-Review Result

- Spec coverage: every P1-P3 audit finding is mapped to one task or the detailed replay subplan; CI/MLflow skip risk is included in Task 9.
- Placeholder scan: no TBD/TODO, “implement later,” or unspecified test/error-handling step remains.
- Type consistency: `ChampionManifest` v2 owns `prepared_output_sha256`; `verify_prepared_parquet` consumes the same three identity fields; promotion compares the same six hash keys emitted by Phase 7.
- Dependency order: replay recovery is independent; Phase 1C separation precedes package v2; package v2 precedes replay byte binding; final integration consumes all prior tasks.
- Scope: no new dependency, service, table, platform, or speculative abstraction is introduced.
