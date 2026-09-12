"""Unit tests for Virtual Lab SimulationEngine execution logic."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from industrial_reliability.lab.catalog import get_reference_lab_definition
from industrial_reliability.lab.contracts import (
    ControlState,
    PhysicalState,
)
from industrial_reliability.lab.engine import SimulationEngine
from industrial_reliability.lab.simulation.network import compile_lab
from industrial_reliability.lab.simulation.solver import step


@pytest.fixture
def engine() -> SimulationEngine:
    mock_pool = MagicMock()
    return SimulationEngine(mock_pool)


def test_execute_command_set_load_and_opening(engine: SimulationEngine) -> None:
    comp_id = uuid4()
    valve_id = uuid4()

    controls = ControlState()
    # Apply compressor load
    c1 = engine.execute_command_in_controls(
        controls, "SET_COMPRESSOR_LOAD", comp_id, {"load": 0.75}
    )
    assert c1.setpoints[str(comp_id)]["load"] == 0.75

    # Apply valve opening
    c2 = engine.execute_command_in_controls(c1, "SET_VALVE_OPENING", valve_id, {"opening": 0.4})
    assert c2.setpoints[str(valve_id)]["opening"] == 0.4
    assert c2.setpoints[str(comp_id)]["load"] == 0.75


def test_execute_command_fault_injection_and_clearing(engine: SimulationEngine) -> None:
    tank_id = uuid4()
    controls = ControlState()

    # Inject leak
    c1 = engine.execute_command_in_controls(
        controls,
        "INJECT_FAULT",
        tank_id,
        {"kind": "LEAK", "port": "A", "values": {"conductance_kg_s_pa": 5e-8}},
    )
    assert len(c1.active_faults) == 1
    assert c1.active_faults[0].kind == "LEAK"
    assert c1.active_faults[0].target_id == tank_id

    # Clear leak
    c2 = engine.execute_command_in_controls(c1, "CLEAR_FAULT", tank_id, {"kind": "LEAK"})
    assert len(c2.active_faults) == 0


def test_deterministic_multi_step_run() -> None:
    ref_lab = get_reference_lab_definition()
    net = compile_lab(ref_lab, dt=0.05)

    pressures = {str(a.asset_id): 400000.0 for a in ref_lab.assets}
    state0 = PhysicalState(tick=0, pressures_pa=pressures, flows_kg_s={})
    controls = ControlState()

    # Run 40 ticks on run 1
    s1 = state0
    for _ in range(40):
        s1 = step(net, s1, controls, dt=0.05)

    # Run 40 ticks on run 2
    s2 = state0
    for _ in range(40):
        s2 = step(net, s2, controls, dt=0.05)

    assert s1.tick == 40
    assert s2.tick == 40
    for nid, p in s1.pressures_pa.items():
        assert p == s2.pressures_pa[nid]


@pytest.mark.asyncio
async def test_engine_run_once_execution() -> None:
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_pool.connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = None  # Force initial checkpoint creation

    engine = SimulationEngine(mock_pool)
    engine.store.checkpoint = MagicMock(return_value=True)

    ref_lab = get_reference_lab_definition()
    from industrial_reliability.lab.contracts import RunSpec, SimulationRun

    run = SimulationRun(
        run_id=uuid4(),
        spec=RunSpec(lab_id=ref_lab.lab_id, lab_revision=1, seed=42, speed=1, max_ticks=40),
        status="RUNNING",
        definition=ref_lab,
        definition_digest="digest",
        scene_digest="scene",
        profile_digest="profile",
        sampling_digest="sampling",
    )

    success = await engine.run_once(run)
    assert success is True
    assert engine.store.checkpoint.call_count == 20  # 40 ticks / 2 ticks per batch
