"""Unit tests for Virtual Lab v2 FastAPI routes using in-memory store."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from industrial_reliability.lab.api import create_app
from industrial_reliability.lab.contracts import (
    CommandReceipt,
    CommandRequest,
    LabDefinition,
    PhysicalState,
    RunSnapshot,
    RunSpec,
    SimulationRun,
    compute_definition_digest,
    validate_lab,
)
from industrial_reliability.lab.store import (
    CommandRevisionConflictError,
    LabNotFoundError,
    LabNotRunnableError,
    LabRevisionConflictError,
    RunNotFoundError,
)


class FakeLabStore:
    """In-memory store implementation for testing API route handling."""

    def __init__(self) -> None:
        # lab_id -> {revision: LabDefinition}
        self.labs: dict[UUID, dict[int, LabDefinition]] = {}
        self.runs: dict[UUID, SimulationRun] = {}
        self.commands: dict[UUID, list[CommandReceipt]] = {}
        self.history: dict[UUID, list[dict[str, Any]]] = {}

    def save_lab(self, definition: LabDefinition, expected_revision: int) -> LabDefinition:
        lab_id = definition.lab_id
        if lab_id not in self.labs:
            if expected_revision not in (0, 1):
                raise LabRevisionConflictError("Initial revision must be 1")
            rev_def = definition.model_copy(update={"revision": 1})
            self.labs[lab_id] = {1: rev_def}
            return rev_def

        curr_rev = max(self.labs[lab_id].keys())
        if curr_rev != expected_revision:
            raise LabRevisionConflictError(
                f"Revision conflict: current {curr_rev} != expected {expected_revision}"
            )
        new_rev = curr_rev + 1
        rev_def = definition.model_copy(update={"revision": new_rev})
        self.labs[lab_id][new_rev] = rev_def
        return rev_def

    def get_lab(self, lab_id: UUID, revision: int | None = None) -> LabDefinition | None:
        revs = self.labs.get(lab_id)
        if not revs:
            return None
        if revision is None:
            return revs[max(revs.keys())]
        return revs.get(revision)

    def list_labs(self, after: UUID | None = None, limit: int = 50) -> tuple[dict[str, Any], ...]:
        items = []
        for lab_id, revs in sorted(self.labs.items(), key=lambda x: str(x[0])):
            latest = revs[max(revs.keys())]
            items.append(
                {
                    "lab_id": lab_id,
                    "name": latest.name,
                    "current_revision": latest.revision,
                    "created_at": "2026-03-31T00:00:00Z",
                }
            )
        return tuple(items[:limit])

    def start_run(self, spec: RunSpec, run_id: UUID | None = None) -> SimulationRun:
        definition = self.get_lab(spec.lab_id, spec.lab_revision)
        if definition is None:
            raise LabNotFoundError("Lab not found")
        val = validate_lab(definition)
        if not val.run_eligible:
            raise LabNotRunnableError("Lab not runnable")

        assigned_id = run_id or uuid4()
        run = SimulationRun(
            run_id=assigned_id,
            spec=spec,
            status="CREATED",
            definition=definition,
            definition_digest=compute_definition_digest(definition),
            scene_digest="a" * 64,
            profile_digest="b" * 64,
            sampling_digest="c" * 64,
        )
        self.runs[assigned_id] = run
        return run

    def get_run(self, run_id: UUID) -> SimulationRun | None:
        return self.runs.get(run_id)

    def get_snapshot(self, run_id: UUID) -> RunSnapshot | None:
        run = self.runs.get(run_id)
        if not run:
            return None
        return RunSnapshot(
            run_id=run_id,
            tick=0,
            status=run.status,
            control_revision=run.control_revision,
            event_sequence=0,
            physical=PhysicalState(tick=0, pressures_pa={}, flows_kg_s={}),
            observations=(),
            pending_commands=tuple(self.commands.get(run_id, [])),
            alerts=(),
        )

    def submit_command(self, run_id: UUID, request: CommandRequest) -> CommandReceipt:
        run = self.runs.get(run_id)
        if not run:
            raise RunNotFoundError("Run not found")
        if request.expected_control_revision != run.control_revision:
            raise CommandRevisionConflictError("Control revision mismatch")

        receipt = CommandReceipt(
            command_id=request.command_id,
            status="ACCEPTED",
            accepted_sequence=1,
            control_revision=run.control_revision + 1,
        )
        self.runs[run_id] = run.model_copy(update={"control_revision": run.control_revision + 1})
        self.commands.setdefault(run_id, []).append(receipt)
        return receipt

    def get_history(
        self, run_id: UUID, from_tick: int = 0, to_tick: int | None = None, limit: int = 300
    ) -> tuple[dict[str, Any], ...]:
        return tuple(self.history.get(run_id, []))


@pytest.fixture
def fake_store() -> FakeLabStore:
    return FakeLabStore()


@pytest.fixture
def client(fake_store: FakeLabStore) -> TestClient:
    app = create_app(store=fake_store)
    with TestClient(app) as test_client:
        yield test_client


def test_healthz_endpoint(client: TestClient) -> None:
    res = client.get("/v2/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["status"] == "HEALTHY"


def test_catalog_endpoint(client: TestClient) -> None:
    res = client.get("/v2/catalog")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "assets" in data["data"]
    assert "COMPRESSOR" in data["data"]["assets"]


def test_reference_template_endpoint(client: TestClient) -> None:
    res = client.get("/v2/templates/reference")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["data"]["assets"]) == 20
    assert len(data["data"]["pipes"]) == 18
    assert len(data["data"]["sensors"]) == 20


def test_create_and_get_lab(client: TestClient) -> None:
    res = client.post("/v2/labs", json={"name": "New Blank Lab", "template": "BLANK"})
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    lab_id = data["data"]["lab_id"]
    assert data["data"]["name"] == "New Blank Lab"
    assert data["data"]["revision"] == 1

    get_res = client.get(f"/v2/labs/{lab_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["name"] == "New Blank Lab"


def test_update_lab_and_concurrency_conflict(client: TestClient) -> None:
    res = client.post("/v2/labs", json={"name": "Update Lab", "template": "BLANK"})
    lab_id = res.json()["data"]["lab_id"]
    lab_data = res.json()["data"]

    # Valid update
    lab_data["name"] = "Update Lab Rev 2"
    upd_res = client.put(
        f"/v2/labs/{lab_id}", json={"expected_revision": 1, "definition": lab_data}
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["data"]["revision"] == 2

    # Stale update
    stale_res = client.put(
        f"/v2/labs/{lab_id}", json={"expected_revision": 1, "definition": lab_data}
    )
    assert stale_res.status_code == 409
    assert stale_res.json()["error"]["code"] == "LAB_REVISION_CONFLICT"


def test_validate_lab_endpoint(client: TestClient) -> None:
    create_res = client.post("/v2/labs", json={"name": "Ref Lab", "template": "REFERENCE"})
    lab_id = create_res.json()["data"]["lab_id"]

    val_res = client.post(f"/v2/labs/{lab_id}/validate", json={"revision": 1})
    assert val_res.status_code == 200
    val_data = val_res.json()["data"]
    assert val_data["run_eligible"] is True
    assert len(val_data["errors"]) == 0


def test_run_creation_and_command(client: TestClient) -> None:
    create_res = client.post("/v2/labs", json={"name": "Run Lab", "template": "REFERENCE"})
    lab_id = create_res.json()["data"]["lab_id"]

    run_res = client.post(
        "/v2/runs", json={"lab_id": lab_id, "lab_revision": 1, "seed": 42, "speed": 1}
    )
    assert run_res.status_code == 201
    run_id = run_res.json()["data"]["run_id"]

    # Get snapshot
    snap_res = client.get(f"/v2/runs/{run_id}")
    assert snap_res.status_code == 200
    assert snap_res.json()["data"]["status"] == "CREATED"

    # Submit command
    cmd_res = client.post(
        f"/v2/runs/{run_id}/commands",
        json={
            "command_id": str(uuid4()),
            "expected_control_revision": 0,
            "action": "SET_COMPRESSOR_LOAD",
            "parameters": {"load": 0.8},
        },
    )
    assert cmd_res.status_code == 202
    assert cmd_res.json()["data"]["status"] == "ACCEPTED"
