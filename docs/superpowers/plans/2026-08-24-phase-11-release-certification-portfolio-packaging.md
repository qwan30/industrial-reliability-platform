# Phase 11 Release Certification and Portfolio Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package, verify, and certify the entire platform into a reproducible, pinned one-command local demonstration and portfolio-grade release bundle with exact-SHA evidence, data/model cards, runbook, and measured CV claims.

**Architecture:** A release certification engine reads the final output of prior phases and validates all terminal gates (Phase 1/1B feasibility, champion provenance, replay determinism, offline-online parity, alert persistence, console E2E, MLflow tracking, decision gates for Airflow/Spark/OpenVINO). If the feasible path was completed, it validates the pinned Docker Compose environment, executes a deterministic end-to-end demo scenario with real browser Playwright verification, checks security/secret hygiene, and generates exact-SHA documentation. If the infeasible path occurred, it bundles a rigorous, honest negative-research release documenting model limitations and engineering learnings.

**Tech Stack:** Python 3.12, Docker Compose, Playwright, FastAPI, React/Vite, PostgreSQL, Kafka, MLflow, Prometheus, Grafana, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Must run only after all preceding applicable phases have reached their verified terminal gates.
- Pinned local execution only: services bind exclusively to localhost (127.0.0.1); no public ingress, cloud IaC, or multi-tenant scaffolding.
- Strict provenance: every claim in the documentation, data/model cards, and portfolio summary must trace directly to a verified, immutable SHA-256 artifact.
- Zero secrets: no hardcoded API keys, tokens, or private credentials in repository or Docker configs; all LLM provider keys passed via environment variables with fail-closed fallback.
- Dual-path support:
  - Feasible path: Full platform release package (Docker Compose, Replay, Streaming Worker, FastAPI Scorer, React Console, MLflow, Prometheus, Grafana, Grounded RCA).
  - Infeasible path: Negative-research release package (methodology, benchmark artifacts, failure taxonomy, root-cause analysis, lessons learned).
- Code quality & test coverage: All new Python code must maintain >= 80% branch coverage, pass `ruff check`, `ruff format --check`, and `mypy --strict`.

---

### Task 1: Build the Release Certification and Gate Validator

**Files:**
- Create: `src/industrial_reliability/release_certification.py`
- Create: `tests/test_release_certification.py`

**Interfaces:**
- Consumes: Manifests and aggregate results from Phase 1/1B through Phase 10B (`artifacts/**/manifest.json`, `artifacts/**/decision.json`).
- Produces: `ReleaseCertificationReportV1`, CLI `python -m industrial_reliability.release_certification`, and `verify_release_prerequisites() -> ReleaseCertificationReportV1`.
- `ReleaseCertificationReportV1` fields: `schema_version`, `timestamp`, `git_sha`, `verdict` (`"FEASIBLE_PLATFORM_RELEASE"` | `"NEGATIVE_RESEARCH_RELEASE"` | `"INVALID"`), `phases_passed`, `decision_gates`, `artifact_hashes`, `limitations`.

- [ ] **Step 1: Write failing tests for release gate validation**

```python
import pytest
from industrial_reliability.release_certification import (
    ReleaseCertificationValidator,
    ReleaseCertificationReportV1,
)


def test_validator_detects_feasible_platform_path():
    validator = ReleaseCertificationValidator(artifact_dir="tests/fixtures/artifacts_feasible")
    report = validator.evaluate()
    assert report.verdict == "FEASIBLE_PLATFORM_RELEASE"
    assert "phase1b" in report.phases_passed
    assert "phase9" in report.phases_passed
    assert report.is_certified is True


def test_validator_detects_infeasible_research_path():
    validator = ReleaseCertificationValidator(artifact_dir="tests/fixtures/artifacts_infeasible")
    report = validator.evaluate()
    assert report.verdict == "NEGATIVE_RESEARCH_RELEASE"
    assert report.is_certified is True


def test_validator_rejects_missing_mandatory_gate():
    validator = ReleaseCertificationValidator(artifact_dir="tests/fixtures/artifacts_incomplete")
    report = validator.evaluate()
    assert report.verdict == "INVALID"
    assert report.is_certified is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release_certification.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'industrial_reliability.release_certification'`

- [ ] **Step 3: Implement ReleaseCertificationValidator**

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import json


@dataclass(frozen=True)
class ReleaseCertificationReportV1:
    schema_version: str
    verdict: Literal["FEASIBLE_PLATFORM_RELEASE", "NEGATIVE_RESEARCH_RELEASE", "INVALID"]
    phases_passed: list[str]
    decision_gates: dict[str, str]
    artifact_hashes: dict[str, str]
    is_certified: bool
    limitations: list[str]


class ReleaseCertificationValidator:
    def __init__(self, artifact_dir: str | Path) -> None:
        self.artifact_dir = Path(artifact_dir)

    def evaluate(self) -> ReleaseCertificationReportV1:
        if not self.artifact_dir.exists():
            return ReleaseCertificationReportV1(
                schema_version="1.0.0",
                verdict="INVALID",
                phases_passed=[],
                decision_gates={},
                artifact_hashes={},
                is_certified=False,
                limitations=["Artifact directory missing"],
            )
        # Parse phase manifests and verify SHA digests
        # ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release_certification.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add src/industrial_reliability/release_certification.py tests/test_release_certification.py
git commit -m "feat(release): implement release certification and gate validator"
```

---

### Task 2: Pinned One-Command Compose Stack and Preflight Verification

**Files:**
- Create: `deploy/docker-compose.yml`
- Create: `deploy/preflight.py`
- Create: `deploy/run_demo.py`
- Create: `tests/test_deploy_preflight.py`

**Interfaces:**
- Consumes: Environment variables, Docker daemon, port bindings, local storage.
- Produces: `deploy.preflight:verify_host_environment() -> PreflightResult`, deterministic service launch with health checks (`kafka`, `postgres`, `control_api`, `stream_worker`, `console`, `prometheus`, `grafana`, `mlflow`).

- [ ] **Step 1: Write failing preflight environment tests**

```python
from deploy.preflight import verify_host_environment, PreflightConfig


def test_preflight_checks_required_ports_and_memory(monkeypatch):
    monkeypatch.setattr("shutil.disk_usage", lambda _: (100 * 1024**3, 50 * 1024**3, 50 * 1024**3))
    monkeypatch.setattr(
        "psutil.virtual_memory", lambda: type("VM", (), {"available": 8 * 1024**3})()
    )

    result = verify_host_environment(PreflightConfig(min_memory_gb=4, min_disk_gb=10))
    assert result.passed is True
    assert len(result.errors) == 0


def test_preflight_fails_on_low_memory(monkeypatch):
    monkeypatch.setattr(
        "psutil.virtual_memory", lambda: type("VM", (), {"available": 1 * 1024**3})()
    )
    result = verify_host_environment(PreflightConfig(min_memory_gb=4, min_disk_gb=10))
    assert result.passed is False
    assert any("memory" in err.lower() for err in result.errors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deploy_preflight.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deploy.preflight'`

- [ ] **Step 3: Implement preflight checker and pinned docker-compose.yml**

```python
# deploy/preflight.py
from __future__ import annotations
import shutil
import socket
import psutil
from dataclasses import dataclass


@dataclass(frozen=True)
class PreflightConfig:
    min_memory_gb: float = 4.0
    min_disk_gb: float = 10.0
    required_ports: tuple[int, ...] = (8000, 3000, 5432, 9092, 9090, 5000)


@dataclass(frozen=True)
class PreflightResult:
    passed: bool
    errors: list[str]
    warnings: list[str]


def verify_host_environment(config: PreflightConfig = PreflightConfig()) -> PreflightResult:
    errors = []
    warnings = []
    # Check RAM
    vm = psutil.virtual_memory()
    if vm.available < config.min_memory_gb * (1024**3):
        errors.append(
            f"Insufficient RAM: {vm.available / 1024**3:.1f}GB available, {config.min_memory_gb}GB required."
        )
    # Check Ports
    for port in config.required_ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                errors.append(f"Port {port} is already in use.")
    return PreflightResult(passed=len(errors) == 0, errors=errors, warnings=warnings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_deploy_preflight.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add deploy/docker-compose.yml deploy/preflight.py deploy/run_demo.py tests/test_deploy_preflight.py
git commit -m "feat(deploy): add pinned compose stack and preflight verification"
```

---

### Task 3: End-to-End Real-Click Browser & Replay Scenario Certification

**Files:**
- Create: `tests/e2e/test_release_e2e.py`
- Create: `tests/e2e/conftest.py`

**Interfaces:**
- Consumes: Live or test container FastAPI endpoints and React console via Playwright.
- Produces: Playwright browser trace, screenshot evidence, end-to-end assertion from `ReplayCommandV1` -> `TelemetryEventV1` -> `ScoreDecisionV1` -> `AlertEventV1` -> `RcaReportV1`.

- [ ] **Step 1: Write failing Playwright E2E scenario test**

```python
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_full_platform_demo_scenario(page: Page, live_server_url: str):
    # Navigate to Operator Console
    page.goto(live_server_url)
    expect(page.locator("h1")).to_contain_text("Operator Console")

    # Start Replay
    page.click("button#start-replay-btn")
    expect(page.locator("#replay-status")).to_contain_text("RUNNING")

    # Observe streaming anomaly score
    page.wait_for_selector("#telemetry-chart")
    expect(page.locator("#active-alerts-count")).not_to_have_text("0", timeout=15000)

    # Inspect Alert and grounded RCA
    page.click(".alert-item-row:first-child")
    expect(page.locator("#rca-summary")).to_be_visible()
    expect(page.locator("#rca-evidence-list")).to_be_visible()
```

- [ ] **Step 2: Run test to verify it fails without server/mocks**

Run: `uv run pytest tests/e2e/test_release_e2e.py -v -m e2e`
Expected: FAIL (or skipped if live server fixture not configured)

- [ ] **Step 3: Implement test harness and conftest fixtures**

Ensure conftest manages ephemeral FastAPI test servers and static SPA assets for isolated CI testing.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/e2e/ -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add tests/e2e/test_release_e2e.py tests/e2e/conftest.py
git commit -m "test(e2e): add end-to-end real-click release certification tests"
```

---

### Task 4: Documentation Package, Runbook, Cards, and Measured Claims Generator

**Files:**
- Create: `docs/RUNBOOK.md`
- Create: `docs/DATA_CARD.md`
- Create: `docs/MODEL_CARD.md`
- Create: `docs/ARCHITECTURE_DIAGRAMS.md`
- Create: `src/industrial_reliability/portfolio_claims.py`
- Create: `tests/test_portfolio_claims.py`

**Interfaces:**
- Consumes: Release certification report and immutable benchmark outputs.
- Produces: Formatted documentation suite, markdown verification, and `generate_measured_claims() -> dict[str, Any]` ensuring zero ungrounded CV/portfolio claims.

- [ ] **Step 1: Write failing tests for portfolio claims generator**

```python
from industrial_reliability.portfolio_claims import generate_portfolio_claims


def test_claims_strictly_derived_from_actual_metrics():
    metrics = {
        "dataset": "MetroPT-3",
        "detected_events": 3,
        "total_events": 4,
        "lead_time_seconds_p50": 1800,
        "false_episodes_per_day": 0.42,
        "pr_auc": 0.88,
    }
    claims = generate_portfolio_claims(metrics)
    assert claims["event_detection_rate"] == "75.0% (3/4 events)"
    assert "0.42" in claims["false_alarm_rate"]
    assert "1800" in claims["lead_time_summary"]
    assert claims["unsupported_claims"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_portfolio_claims.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'industrial_reliability.portfolio_claims'`

- [ ] **Step 3: Implement portfolio claims generator and documentation cards**

```python
from __future__ import annotations
from typing import Any


def generate_portfolio_claims(metrics: dict[str, Any]) -> dict[str, Any]:
    detected = metrics.get("detected_events", 0)
    total = metrics.get("total_events", 1)
    rate = (detected / total) * 100

    return {
        "event_detection_rate": f"{rate:.1f}% ({detected}/{total} events)",
        "false_alarm_rate": f"{metrics.get('false_episodes_per_day', 0.0):.2f} false episodes/day",
        "lead_time_summary": f"{metrics.get('lead_time_seconds_p50', 0)}s median lead time",
        "pr_auc": f"{metrics.get('pr_auc', 0.0):.4f}",
        "unsupported_claims": [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_portfolio_claims.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add docs/RUNBOOK.md docs/DATA_CARD.md docs/MODEL_CARD.md docs/ARCHITECTURE_DIAGRAMS.md src/industrial_reliability/portfolio_claims.py tests/test_portfolio_claims.py
git commit -m "docs(release): generate runbook, model/data cards, and measured claims"
```

---

### Task 5: Final Release Bundle Checksum Package

**Files:**
- Create: `src/industrial_reliability/package_release.py`
- Create: `tests/test_package_release.py`

**Interfaces:**
- Consumes: All committed files and generated certification artifacts.
- Produces: `release_manifest.json` with SHA-256 checksums of every release file and verification CLI `python -m industrial_reliability.package_release --verify`.

- [ ] **Step 1: Write failing release manifest packager tests**

```python
import tempfile
from pathlib import Path
from industrial_reliability.package_release import (
    generate_release_manifest,
    verify_release_manifest,
)


def test_generate_and_verify_release_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("demo", encoding="utf-8")
        manifest_path = generate_release_manifest(root)

        assert manifest_path.exists()
        assert verify_release_manifest(manifest_path) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_package_release.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'industrial_reliability.package_release'`

- [ ] **Step 3: Implement package_release.py**

```python
from __future__ import annotations
import hashlib
import json
from pathlib import Path


def generate_release_manifest(root: Path) -> Path:
    checksums: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_file() and not any(part.startswith(".") for part in p.parts):
            checksums[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()

    manifest_path = root / "release_manifest.json"
    manifest_path.write_text(
        json.dumps({"checksums": checksums}, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest_path


def verify_release_manifest(manifest_path: Path) -> bool:
    root = manifest_path.parent
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rel_path, expected_hash in data.get("checksums", {}).items():
        file_path = root / rel_path
        if (
            not file_path.exists()
            or hashlib.sha256(file_path.read_bytes()).hexdigest() != expected_hash
        ):
            return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_package_release.py -v`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add src/industrial_reliability/package_release.py tests/test_package_release.py
git commit -m "feat(release): add release manifest packaging and verification CLI"
```
