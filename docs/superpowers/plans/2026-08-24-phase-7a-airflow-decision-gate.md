# Phase 7A Airflow NOT ADOPTED Decision Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish an exact-hash `NOT_ADOPTED` Airflow decision and prove the repository contains no Airflow runtime surface.

**Architecture:** The approved system has one manually invoked ML lifecycle, zero recurring workflows, no scheduling requirement, and an explicit manual promotion gate. A tiny stdlib publisher binds that already-approved scope to the Phase 7 gate and current Git SHA. One guard test prevents accidental Airflow dependencies, services, or DAGs.

**Tech Stack:** Python 3.12 standard library, pytest, existing Phase 7 MLflow evidence.

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- MLflow remains mandatory and is not replaced by this decision.
- The approved lifecycle is manual candidate import/reproduction plus explicit manual champion promotion.
- The approved project has zero recurring workflows and no scheduling requirement; therefore Airflow does not need to exist.
- Do not add `apache-airflow`, an Airflow container/service/database/executor, a DAG directory, or Airflow configuration.
- Do not invent retry/resume savings, monthly run counts, failure samples, or benchmark thresholds when no scheduled workflow exists.
- Bind the decision to the exact roadmap spec SHA-256, passing Phase 7 gate SHA-256, and Git SHA.
- A future approved recurring or scheduled workflow is a new architectural request and must return to brainstorming/specification before Airflow is reconsidered.
- `NOT_ADOPTED` is the only Phase 7A terminal result for the currently approved scope.

---

### Task 1: Publish the exact-hash NOT ADOPTED evidence

**Files:**
- Create: `scripts/write_phase7a_airflow_decision.py`
- Create: `tests/test_phase7a_airflow_decision.py`
- Create: `docs/decisions/2026-08-24-airflow-not-adopted.md`

**Interfaces:**
- Consumes: approved roadmap spec path, passing `phase7-gate.json`, and clean Git SHA.
- Produces: private self-hashed `artifacts/phase7a/<git-sha>/airflow-decision.json` with `schema_version="airflow-decision-v1"`, `decision="NOT_ADOPTED"`, `approved_recurring_workflows=0`, `scheduled_workflows=0`, `promotion_mode="manual"`, `airflow_installed=false`, source hashes, and `decision_sha256`; committed ADR with the same rationale and reconsideration trigger.

- [ ] **Step 1: Write the failing publisher test**

```python
def test_publisher_writes_only_not_adopted_with_exact_hashes(tmp_path: Path) -> None:
    spec = write_json(tmp_path / "spec.json", {"workflow": "manual"})
    phase7 = write_json(tmp_path / "phase7-gate.json", passing_phase7_gate())
    output = tmp_path / "airflow-decision.json"
    write_decision(spec=spec, phase7_gate=phase7, git_sha="a" * 40, output=output)
    body = json.loads(output.read_text(encoding="utf-8"))
    assert body["decision"] == "NOT_ADOPTED"
    assert body["approved_recurring_workflows"] == 0
    assert body["scheduled_workflows"] == 0
    assert body["promotion_mode"] == "manual"
    assert body["airflow_installed"] is False
    assert verify_self_hash(body, "decision_sha256")


def test_publisher_rejects_nonpassing_phase7_gate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Phase 7 gate"):
        write_decision(
            spec=write_json(tmp_path / "spec.json", {}),
            phase7_gate=write_json(tmp_path / "phase7.json", {"lineage_complete": False}),
            git_sha="a" * 40,
            output=tmp_path / "decision.json",
        )
```

- [ ] **Step 2: Run the test before the publisher exists**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_phase7a_airflow_decision.py -q`

Expected: FAIL during collection because `write_phase7a_airflow_decision.py` does not exist.

- [ ] **Step 3: Implement the minimum fail-closed publisher**

```python
def write_decision(*, spec: Path, phase7_gate: Path, git_sha: str, output: Path) -> None:
    gate = json.loads(phase7_gate.read_text(encoding="utf-8"))
    required = ("rerun_within_tolerance", "lineage_complete", "manual_promotion_verified")
    if not all(gate.get(name) is True for name in required):
        raise ValueError("Phase 7 gate has not passed")
    if not re.fullmatch(r"[0-9a-f]{40}", git_sha):
        raise ValueError("Git SHA must be 40 lowercase hexadecimal characters")
    payload = {
        "schema_version": "airflow-decision-v1",
        "decision": "NOT_ADOPTED",
        "approved_recurring_workflows": 0,
        "scheduled_workflows": 0,
        "promotion_mode": "manual",
        "airflow_installed": False,
        "roadmap_spec_sha256": sha256_file(spec),
        "phase7_gate_sha256": sha256_file(phase7_gate),
        "git_sha": git_sha,
        "reconsideration_trigger": "an approved recurring or scheduled workflow with measured orchestration requirements",
    }
    write_new_json(output, {**payload, "decision_sha256": canonical_sha256(payload)})
```

`write_new_json` creates parent directories, writes UTF-8 canonical JSON through a temporary file, refuses overwrite, and rejects NaN. The CLI accepts only `--spec`, `--phase7-gate`, `--git-sha`, and `--output`; it has no decision override.

- [ ] **Step 4: Verify the publisher and write the actual evidence**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_phase7a_airflow_decision.py -q`

Run: `.\.venv\Scripts\python.exe scripts/write_phase7a_airflow_decision.py --spec docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md --phase7-gate $env:PHASE7_GATE_PATH --git-sha $(git rev-parse HEAD) --output artifacts/phase7a/$(git rev-parse HEAD)/airflow-decision.json`

Expected: test exits 0 and the artifact is self-hashed with `decision="NOT_ADOPTED"`.

- [ ] **Step 5: Write the source-backed ADR and commit**

The ADR records: MLflow is mandatory; training/import and promotion are manual; approved recurring and scheduled workflow counts are both zero; Airflow would add an idle scheduler, metadata surface, executor, and operational burden without serving a requirement; the exact private artifact path proves the decision; a future recurring/scheduled requirement restarts brainstorming rather than editing this verdict.

```powershell
git add scripts/write_phase7a_airflow_decision.py tests/test_phase7a_airflow_decision.py docs/decisions/2026-08-24-airflow-not-adopted.md
git commit -m "docs: record Airflow not-adopted decision"
```

### Task 2: Guard the repository and close Phase 7A

**Files:**
- Create: `tests/test_no_airflow_surfaces.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `pyproject.toml`, `compose.yaml`, repository paths, Phase 7A decision artifact.
- Produces: one regression guard and a runbook line naming `NOT_ADOPTED` as the completed Phase 7A result.

- [ ] **Step 1: Write the guard test**

```python
def test_repository_has_no_airflow_runtime_surface() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    extras = [
        item
        for group in project["project"].get("optional-dependencies", {}).values()
        for item in group
    ]
    assert all("airflow" not in item.lower() for item in [*dependencies, *extras])
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    assert all("airflow" not in name.lower() for name in compose["services"])
    assert not Path("airflow").exists()
    assert not Path("dags").exists()
    assert Path("docs/decisions/2026-08-24-airflow-not-adopted.md").is_file()
```

- [ ] **Step 2: Run the guard before the ADR exists**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_no_airflow_surfaces.py tests/test_phase7a_airflow_decision.py -q`

Expected: FAIL on the ADR existence assertion until Task 1 is complete; all Airflow-absence assertions pass.

- [ ] **Step 3: Add the exact README runbook entry**

Add a Phase 7A entry pointing to the ADR and private `artifacts/phase7a/<git-sha>/airflow-decision.json`. State `NOT_ADOPTED`, keep using the Phase 7 manual MLflow lifecycle CLI, and require a new brainstorm/spec before any Airflow dependency is added.

- [ ] **Step 4: Run all Phase 7A and repository gates**

Run: `.\.venv\Scripts\python.exe -m ruff check .`

Run: `.\.venv\Scripts\python.exe -m ruff format --check .`

Run: `.\.venv\Scripts\python.exe -m mypy src`

Run: `.\.venv\Scripts\python.exe -m pytest -q --cov-branch --cov-fail-under=80`

Run: `.\.venv\Scripts\python.exe -m pip check`

Run: `.\.venv\Scripts\python.exe -m build`

Expected: every command exits 0 and the Airflow guard remains green.

- [ ] **Step 5: Commit the guard and runbook**

```powershell
git add tests/test_no_airflow_surfaces.py README.md
git commit -m "test: guard Airflow not-adopted scope"
```

## Phase 7A Exit Gate

Move Phase 8 to `Ready` when the exact-hash artifact and ADR both say `NOT_ADOPTED`, the passing Phase 7 gate is referenced, and the repository guard proves no Airflow dependency, service, or DAG exists. Reconsideration requires a newly approved recurring or scheduled workflow and a fresh brainstorming/spec cycle.
