# Industrial Reliability Platform

Production-oriented industrial anomaly detection and reliability intelligence platform.

> **Status:** Phase 1 offline ML feasibility — **NOT FEASIBLE** on the frozen MetroPT holdout; no model met the predeclared gate. This is offline evidence, not production readiness. See the [aggregate Phase 1 result](docs/results/phase-1-offline-ml-feasibility.md).
> Master specification: `docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md`

## Development setup

Requires Python 3.12.

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Quality checks

The same checks CI runs on every push and pull request:

```bash
ruff check .
ruff format --check .
mypy src
pytest -m "not slow"
pip check
python -m build
```

## Project layout

```text
src/industrial_reliability/   # package source (grows with each phase)
tests/                        # test suite
docs/                         # specifications and research notes
references/                   # local-only reference repositories (git-ignored)
data/                         # local-only datasets (git-ignored)
```

## Reproducible ML Lifecycle (Phase 7)

Phase 7 brings MLflow 3.x-backed offline tracking, immutable run provenance, and fail-closed promotion gates to ensure full numerical and artifact reproducibility.

### Optional MLOps Dependencies
Install offline tracking dependencies:
```bash
pip install -e ".[mlops]"
```

### Local MLflow Server
Start the isolated localhost MLflow tracking server backed by PostgreSQL:
```bash
docker compose up -d mlflow
```
The server binds exclusively to `127.0.0.1:5000` with artifacts stored in the `mlflow-artifacts` volume.

### ML Lifecycle CLI
The platform provides three immutable lifecycle commands:

1. **Import Candidate**:
   Logs champion artifacts, contracts, schemas, and git SHA to MLflow under the `candidate` state:
   ```bash
   python -m industrial_reliability.ml_lifecycle import-candidate \
       --champion-package artifacts/champion \
       --phase1b-run-dir artifacts/phase1b/phase1b-run-6050e71c7543
   ```

2. **Reproduce Candidate**:
   Re-fits on train and evaluates on calibration partitions only (never holdout) to verify exact score matching:
   ```bash
   python -m industrial_reliability.ml_lifecycle reproduce \
       --features-path data/processed/phase1b/metropt3/features.parquet \
       --phase1b-run-dir artifacts/phase1b/phase1b-run-6050e71c7543 \
       --champion-package artifacts/champion
   ```

3. **Promote Candidate**:
   Registers the model version under alias `champion` and writes an immutable `promotion-receipt.json`:
   ```bash
   python -m industrial_reliability.ml_lifecycle promote \
       --run-id <candidate-run-id> \
       --approver "lead-reliability-engineer" \
       --expected-source-git-sha <git-sha> \
       --output artifacts/champion/promotion-receipt.json
   ```

### Reproducibility & Lineage Gate
Certifies that candidate reproduction threshold delta $\le 10^{-9}$, score delta $\le 10^{-6}$, and all artifact hashes match:
```bash
python -m industrial_reliability.phase7_gate \
    --champion-package artifacts/champion \
    --features-path data/processed/phase1b/metropt3/features.parquet \
    --phase1b-run-dir artifacts/phase1b/phase1b-run-6050e71c7543 \
    --output-dir artifacts/phase7
```

## License

MIT — see [LICENSE](LICENSE).

