"""Numerical solver for pneumatic lumped-parameter isothermal networks."""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

import numpy as np

from industrial_reliability.lab.contracts import ControlState, PhysicalState
from industrial_reliability.lab.simulation.network import (
    DT_DEFAULT,
    P_ATM,
    CompiledNetwork,
)


class NumericalFailureError(RuntimeError):
    """Raised when numerical convergence or physical constraints fail."""


def step(
    network: CompiledNetwork,
    state: PhysicalState,
    controls: ControlState,
    dt: float = DT_DEFAULT,
) -> PhysicalState:
    """Advance simulation by one physics time step (dt seconds)."""
    num_nodes = len(network.nodes)
    p_prev = np.zeros(num_nodes, dtype=np.float64)

    for node in network.nodes:
        p_val = state.pressures_pa.get(node.node_id, node.initial_pressure_pa)
        if not math.isfinite(p_val) or p_val <= 0:
            raise NumericalFailureError(
                f"Initial node pressure invalid for {node.node_id}: {p_val}"
            )
        p_prev[node.node_index] = p_val

    # 1. Determine dynamic edge conductances
    # Extract setpoints and active faults
    setpoints = controls.setpoints
    faults_by_target: dict[UUID, dict[str, Any]] = {}
    for f in controls.active_faults:
        faults_by_target.setdefault(f.target_id, {})[f.kind] = f

    # Build dynamic Laplacian matrix L
    l_dyn = np.zeros((num_nodes, num_nodes), dtype=np.float64)

    # Edge conductances tracking for flow calculations
    edge_conductances = np.zeros(len(network.edges), dtype=np.float64)

    for e in network.edges:
        k = e.base_conductance
        if e.is_valve and e.asset_id:
            # Check for VALVE_STUCK fault
            stuck_fault = faults_by_target.get(e.asset_id, {}).get("VALVE_STUCK")
            if stuck_fault:
                opening = float(stuck_fault.values.get("opening", 0.0))
            else:
                asset_sp = setpoints.get(str(e.asset_id), {})
                opening = float(asset_sp.get("opening", 1.0))

            opening = max(0.0, min(1.0, opening))
            # e.base_conductance was compiled as base_cond * initial_opening.
            # Here we scale proportionally:
            k = e.base_conductance * opening

        edge_conductances[network.edge_id_to_index[e.edge_id]] = k
        i = e.from_node
        j = e.to_node
        l_dyn[i, i] += k
        l_dyn[j, j] += k
        l_dyn[i, j] -= k
        l_dyn[j, i] -= k

    # 2. Prepare compressor source characteristics
    comp_configs = []
    operating_modes: dict[str, str] = {}

    for c in network.compressors:
        unavail = faults_by_target.get(c.asset_id, {}).get("COMPRESSOR_UNAVAILABLE")
        if unavail:
            enabled = False
            operating_modes[str(c.asset_id)] = "UNAVAILABLE"
        else:
            sp = setpoints.get(str(c.asset_id), {})
            enabled = bool(sp.get("enabled", c.enabled))
            operating_modes[str(c.asset_id)] = "RUNNING" if enabled else "OFF"

        sp = setpoints.get(str(c.asset_id), {})
        load = float(sp.get("load", c.nominal_load))
        load = max(0.0, min(1.0, load))

        comp_configs.append((c.node_index, c.q_nom_kg_s, c.p_max_pa, load, enabled))

    # 3. Prepare demand sink characteristics
    demand_configs = []
    for d in network.demands:
        sp = setpoints.get(str(d.asset_id), {})
        load_factor = float(sp.get("load_factor", d.nominal_load_factor))
        load_factor = max(0.0, min(2.0, load_factor))
        k_sink = d.base_conductance * load_factor
        demand_configs.append((d.node_index, k_sink))

    # 4. Prepare leak fault sinks
    leak_configs = []
    for f in controls.active_faults:
        if f.kind == "LEAK":
            # Map target and port to node index
            if f.port:
                n_idx = network.port_to_node_index.get((f.target_id, f.port))
            else:
                # Default to first node of asset
                n_idx = next(
                    (n.node_index for n in network.nodes if n.asset_id == f.target_id),
                    None,
                )
            if n_idx is not None:
                k_leak = float(f.values.get("conductance_kg_s_pa", 1e-8))
                leak_configs.append((n_idx, k_leak))

    # 5. Active-Set Iteration
    # Active masks: comp_active[i], sink_active[j]
    p_curr = np.copy(p_prev)
    c_dt = network.capacitances / dt

    converged = False
    p_next = np.copy(p_prev)

    for _iteration in range(16):
        a_vec = np.zeros(num_nodes, dtype=np.float64)
        b_vec = np.zeros(num_nodes, dtype=np.float64)

        # Apply active compressors: q_in = q_nom * load * max(0, 1 - p / p_max)
        for n_idx, q_nom, p_max, load, enabled in comp_configs:
            if enabled and load > 0 and p_curr[n_idx] < p_max:
                slope = (q_nom * load) / p_max
                a_vec[n_idx] += q_nom * load
                b_vec[n_idx] += slope

        # Apply active demands: q_out = K_sink * max(0, p - p_atm)
        for n_idx, k_sink in demand_configs:
            if p_curr[n_idx] > P_ATM and k_sink > 0:
                a_vec[n_idx] += k_sink * P_ATM
                b_vec[n_idx] += k_sink

        # Apply active leaks: q_leak = K_leak * max(0, p - p_atm)
        for n_idx, k_leak in leak_configs:
            if p_curr[n_idx] > P_ATM and k_leak > 0:
                a_vec[n_idx] += k_leak * P_ATM
                b_vec[n_idx] += k_leak

        # Linear system: (diag(C/dt + b) + L) * p_next = (C/dt) * p_prev + a
        matrix = np.diag(c_dt + b_vec) + l_dyn
        rhs = c_dt * p_prev + a_vec

        try:
            p_sol = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError as e:
            raise NumericalFailureError(f"Singular matrix in solver iteration: {e}") from e

        # Check convergence
        max_delta = np.max(np.abs(p_sol - p_curr))

        # Check if active set state matches solution
        comp_match = all(
            (p_sol[n_idx] < p_max) == (p_curr[n_idx] < p_max)
            for n_idx, _, p_max, load, enabled in comp_configs
            if enabled and load > 0
        )
        sink_match = all(
            (p_sol[n_idx] > P_ATM) == (p_curr[n_idx] > P_ATM)
            for n_idx, k in demand_configs
            if k > 0
        )

        p_curr = p_sol

        if comp_match and sink_match and max_delta <= 1e-7:
            p_next = p_sol
            converged = True
            break

    if not converged:
        p_next = p_curr

    # 6. Physical Sanity Bounds Gate
    if not np.all(np.isfinite(p_next)):
        raise NumericalFailureError("Non-finite pressure detected in solution")
    if np.any(p_next <= 0.0):
        raise NumericalFailureError("Non-positive absolute pressure in solution")
    if np.any(p_next > 2.0e6):
        raise NumericalFailureError("Extreme pressure exceeding 2.0 MPa limit")

    # 7. Mass Conservation Gate
    m_prev = network.capacitances * p_prev
    m_next = network.capacitances * p_next
    delta_m = np.sum(m_next - m_prev)

    # Calculate actual source and sink masses entering/exiting in dt
    q_src_total = 0.0
    for n_idx, q_nom, p_max, load, enabled in comp_configs:
        if enabled and load > 0:
            q_src_total += q_nom * load * max(0.0, 1.0 - p_next[n_idx] / p_max)

    q_sink_total = 0.0
    for n_idx, k_sink in demand_configs:
        if k_sink > 0:
            q_sink_total += k_sink * max(0.0, p_next[n_idx] - P_ATM)
    for n_idx, k_leak in leak_configs:
        if k_leak > 0:
            q_sink_total += k_leak * max(0.0, p_next[n_idx] - P_ATM)

    net_boundary_mass = dt * (q_src_total - q_sink_total)
    conservation_error = abs(delta_m - net_boundary_mass)
    allowed_tolerance = 1e-9 + 1e-8 * np.sum(np.abs(m_prev))

    if conservation_error > allowed_tolerance:
        raise NumericalFailureError(
            f"Conservation gate violation: error {conservation_error:.3e} kg > tolerance {allowed_tolerance:.3e} kg"
        )

    # 8. Compute Edge Flows
    flows_kg_s: dict[str, float] = {}
    for edge in network.edges:
        k = edge_conductances[network.edge_id_to_index[edge.edge_id]]
        p_from = p_next[edge.from_node]
        p_to = p_next[edge.to_node]
        q_flow = float(k * (p_from - p_to))
        flows_kg_s[edge.edge_id] = q_flow

    pressures_pa: dict[str, float] = {
        node.node_id: float(p_next[node.node_index]) for node in network.nodes
    }

    return PhysicalState(
        tick=state.tick + 1,
        pressures_pa=pressures_pa,
        flows_kg_s=flows_kg_s,
        operating_modes=operating_modes,
    )
