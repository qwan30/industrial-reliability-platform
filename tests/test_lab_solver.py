"""Unit tests for Virtual Lab numerical solver and physical network equations."""

from __future__ import annotations

import math
from uuid import uuid4

import numpy as np
import pytest

from industrial_reliability.lab.contracts import (
    ActiveFault,
    Asset,
    ControlState,
    LabDefinition,
    PhysicalState,
    Pipe,
    PortRef,
)
from industrial_reliability.lab.simulation.network import (
    P_ATM,
    R_AIR,
    T_REF,
    compile_lab,
)
from industrial_reliability.lab.simulation.solver import NumericalFailureError, step


def test_closed_3_node_loop_mass_conservation() -> None:
    """Case 1 from Plan Section 6.3:

    3 nodes, volumes [0.5, 0.3, 0.2] m3, initial pressures [700k, 200k, 300k] Pa,
    conductances [2e-7, 1e-7, 1e-7] kg/(s·Pa).
    Over 200 ticks, total mass must be conserved to within 1e-12 kg.
    """
    id1, id2, id3 = uuid4(), uuid4(), uuid4()
    t1 = Asset(
        asset_id=id1,
        type="TANK",
        position_m=(-4, 0, 0),
        rotation_y_rad=0,
        parameters={"volume_m3": 0.5, "initial_pressure_pa": 700000.0},
    )
    t2 = Asset(
        asset_id=id2,
        type="TANK",
        position_m=(0, 0, 0),
        rotation_y_rad=0,
        parameters={"volume_m3": 0.3, "initial_pressure_pa": 200000.0},
    )
    t3 = Asset(
        asset_id=id3,
        type="TANK",
        position_m=(4, 0, 0),
        rotation_y_rad=0,
        parameters={"volume_m3": 0.2, "initial_pressure_pa": 300000.0},
    )

    p1 = Pipe(
        pipe_id=uuid4(),
        from_port=PortRef(asset_id=id1, port="A"),
        to_port=PortRef(asset_id=id2, port="A"),
        conductance_kg_s_pa=2e-7,
    )
    p2 = Pipe(
        pipe_id=uuid4(),
        from_port=PortRef(asset_id=id2, port="B"),
        to_port=PortRef(asset_id=id3, port="A"),
        conductance_kg_s_pa=1e-7,
    )
    p3 = Pipe(
        pipe_id=uuid4(),
        from_port=PortRef(asset_id=id3, port="B"),
        to_port=PortRef(asset_id=id1, port="B"),
        conductance_kg_s_pa=1e-7,
    )

    lab = LabDefinition(
        lab_id=uuid4(),
        revision=1,
        name="Loop Lab",
        assets=(t1, t2, t3),
        pipes=(p1, p2, p3),
        sensors=(),
    )
    net = compile_lab(lab, dt=0.05)

    p_curr = {str(id1): 700000.0, str(id2): 200000.0, str(id3): 300000.0}
    state = PhysicalState(tick=0, pressures_pa=p_curr, flows_kg_s={})

    m_initial = (0.5 * 700000.0 + 0.3 * 200000.0 + 0.2 * 300000.0) / (R_AIR * T_REF)
    assert math.isclose(m_initial, 5.585350196852399, rel_tol=1e-12)

    for _ in range(200):
        state = step(net, state, ControlState(), dt=0.05)

    m_final = sum(
        net.nodes[net.node_id_to_index[nid]].capacitance * p
        for nid, p in state.pressures_pa.items()
    )
    assert math.isclose(m_final, m_initial, abs_tol=1e-12)


def test_receiver_tank_leak_discharge() -> None:
    """Case 2 from Plan Section 6.3:

    Receiver 0.5 m3, p=500000 Pa, leak K=1e-8.
    Next tick pressure must be exactly 499966.4548368196 Pa.
    Without leak, pressure stays at 500000.0 Pa.
    """
    t_id = uuid4()
    tank = Asset(
        asset_id=t_id,
        type="TANK",
        position_m=(0, 0, 0),
        rotation_y_rad=0,
        parameters={"volume_m3": 0.5, "initial_pressure_pa": 500000.0},
    )
    lab = LabDefinition(
        lab_id=uuid4(), revision=1, name="Tank Test", assets=(tank,), pipes=(), sensors=()
    )
    net = compile_lab(lab, dt=0.05)
    state0 = PhysicalState(tick=0, pressures_pa={str(t_id): 500000.0}, flows_kg_s={})

    # Without leak
    s_no_leak = step(net, state0, ControlState(), dt=0.05)
    assert s_no_leak.pressures_pa[str(t_id)] == 500000.0

    # With leak K=1e-8
    leak = ActiveFault(target_id=t_id, kind="LEAK", values={"conductance_kg_s_pa": 1e-8})
    s_leak = step(net, state0, ControlState(active_faults=(leak,)), dt=0.05)
    assert math.isclose(s_leak.pressures_pa[str(t_id)], 499966.4548368196, abs_tol=1e-8)


def test_analytic_exponential_discharge_convergence() -> None:
    """Case 3 from Plan Section 6.3:

    Receiver p0=700000 Pa, V=0.5 m3, leak K=1e-7 over 10s.
    Analytic solution: 607266.709947246 Pa.
    dt=0.05 error: ~35.807 Pa.
    dt=0.025 error: ~17.908 Pa.
    Error refinement ratio h/2 < 0.6 * error h.
    """
    t_id = uuid4()
    tank = Asset(
        asset_id=t_id,
        type="TANK",
        position_m=(0, 0, 0),
        rotation_y_rad=0,
        parameters={"volume_m3": 0.5, "initial_pressure_pa": 700000.0},
    )
    lab = LabDefinition(
        lab_id=uuid4(), revision=1, name="Discharge Test", assets=(tank,), pipes=(), sensors=()
    )

    t_final = 10.0
    k_leak = 1e-7
    vol = 0.5
    tau = vol / (k_leak * R_AIR * T_REF)
    p_analytic = P_ATM + (700000.0 - P_ATM) * np.exp(-t_final / tau)
    assert math.isclose(p_analytic, 607266.709947246, rel_tol=1e-9)

    controls = ControlState(
        active_faults=(
            ActiveFault(target_id=t_id, kind="LEAK", values={"conductance_kg_s_pa": k_leak}),
        )
    )

    # dt = 0.05 (200 steps)
    net_005 = compile_lab(lab, dt=0.05)
    s_005 = PhysicalState(tick=0, pressures_pa={str(t_id): 700000.0}, flows_kg_s={})
    for _ in range(200):
        s_005 = step(net_005, s_005, controls, dt=0.05)
    err_005 = abs(s_005.pressures_pa[str(t_id)] - p_analytic)
    assert math.isclose(err_005, 35.806939, abs_tol=1e-3)

    # dt = 0.025 (400 steps)
    net_0025 = compile_lab(lab, dt=0.025)
    s_0025 = PhysicalState(tick=0, pressures_pa={str(t_id): 700000.0}, flows_kg_s={})
    for _ in range(400):
        s_0025 = step(net_0025, s_0025, controls, dt=0.025)
    err_0025 = abs(s_0025.pressures_pa[str(t_id)] - p_analytic)
    assert math.isclose(err_0025, 17.908173, abs_tol=1e-3)

    # Convergence order ratio check
    ratio = err_0025 / err_005
    assert ratio < 0.6


def test_compressor_cutout_at_max_pressure() -> None:
    c_id = uuid4()
    comp = Asset(
        asset_id=c_id,
        type="COMPRESSOR",
        position_m=(0, 0, 0),
        rotation_y_rad=0,
        parameters={"q_nom_kg_s": 0.05, "p_max_pa": 900000.0, "initial_pressure_pa": 900000.0},
    )
    lab = LabDefinition(
        lab_id=uuid4(), revision=1, name="Comp Cutout", assets=(comp,), pipes=(), sensors=()
    )
    net = compile_lab(lab, dt=0.05)

    state0 = PhysicalState(tick=0, pressures_pa={str(c_id): 900000.0}, flows_kg_s={})
    # When p == p_max, compressor source flow is 0, pressure should not increase
    state1 = step(net, state0, ControlState(), dt=0.05)
    assert math.isclose(state1.pressures_pa[str(c_id)], 900000.0, abs_tol=1e-6)


def test_extreme_pressure_fails_numerical_gate() -> None:
    t_id = uuid4()
    tank = Asset(
        asset_id=t_id,
        type="TANK",
        position_m=(0, 0, 0),
        rotation_y_rad=0,
        parameters={"volume_m3": 0.5, "initial_pressure_pa": 1000000.0},
    )
    lab = LabDefinition(
        lab_id=uuid4(), revision=1, name="Limit Test", assets=(tank,), pipes=(), sensors=()
    )
    net = compile_lab(lab, dt=0.05)

    # Input pressure exceeding 2.0 MPa limit
    state_extreme = PhysicalState(tick=0, pressures_pa={str(t_id): 2.5e6}, flows_kg_s={})
    with pytest.raises(NumericalFailureError):
        step(net, state_extreme, ControlState(), dt=0.05)
