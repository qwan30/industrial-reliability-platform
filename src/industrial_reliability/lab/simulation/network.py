"""Graph compiler transforming LabDefinition into a numerical network."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import numpy as np

from industrial_reliability.lab.contracts import LabDefinition, SensorKind

R_AIR = 287.05  # J/(kg·K)
T_REF = 293.15  # K (20 deg C)
P_ATM = 101325.0  # Pa
DT_DEFAULT = 0.05  # s (20 Hz)


@dataclass(frozen=True, slots=True)
class NetworkNode:
    node_id: str
    node_index: int
    asset_id: UUID
    port_group: str
    volume_m3: float
    capacitance: float  # C = V / (R * T)
    initial_pressure_pa: float


@dataclass(frozen=True, slots=True)
class NetworkEdge:
    edge_id: str
    from_node: int
    to_node: int
    base_conductance: float
    asset_id: UUID | None = None  # Non-None for internal valve edges
    is_valve: bool = False


@dataclass(frozen=True, slots=True)
class CompressorSource:
    asset_id: UUID
    node_index: int
    q_nom_kg_s: float
    p_max_pa: float
    nominal_load: float
    enabled: bool


@dataclass(frozen=True, slots=True)
class DemandSink:
    asset_id: UUID
    node_index: int
    base_conductance: float
    nominal_load_factor: float


@dataclass(frozen=True, slots=True)
class CompiledNetwork:
    definition_digest: str
    nodes: tuple[NetworkNode, ...]
    node_id_to_index: dict[str, int]
    port_to_node_index: dict[tuple[UUID, str], int]
    edges: tuple[NetworkEdge, ...]
    edge_id_to_index: dict[str, int]
    compressors: tuple[CompressorSource, ...]
    demands: tuple[DemandSink, ...]
    sensor_targets: dict[UUID, tuple[SensorKind, int, int]]  # sensor_id -> (kind, target_idx, sign)
    volumes: np.ndarray
    capacitances: np.ndarray
    c_over_dt: np.ndarray
    base_laplacian: np.ndarray


def compile_lab(definition: LabDefinition, dt: float = DT_DEFAULT) -> CompiledNetwork:
    """Compile LabDefinition into an immutable numerical network with sorted matrices."""
    # 1. Collect all nodes deterministically
    sorted_assets = sorted(definition.assets, key=lambda a: str(a.asset_id))
    nodes: list[NetworkNode] = []
    node_id_to_index: dict[str, int] = {}
    port_to_node_index: dict[tuple[UUID, str], int] = {}

    idx = 0
    for a in sorted_assets:
        init_p = float(a.parameters.get("initial_pressure_pa", 400000.0))

        if a.type == "TANK":
            node_id = str(a.asset_id)
            vol = float(a.parameters.get("volume_m3", 0.5))
            cap = vol / (R_AIR * T_REF)
            node = NetworkNode(
                node_id=node_id,
                node_index=idx,
                asset_id=a.asset_id,
                port_group="AB",
                volume_m3=vol,
                capacitance=cap,
                initial_pressure_pa=init_p,
            )
            nodes.append(node)
            node_id_to_index[node_id] = idx
            port_to_node_index[(a.asset_id, "A")] = idx
            port_to_node_index[(a.asset_id, "B")] = idx
            idx += 1

        elif a.type == "COMPRESSOR":
            node_id = str(a.asset_id)
            vol = 0.02  # 20 liter plenum
            cap = vol / (R_AIR * T_REF)
            node = NetworkNode(
                node_id=node_id,
                node_index=idx,
                asset_id=a.asset_id,
                port_group="OUT",
                volume_m3=vol,
                capacitance=cap,
                initial_pressure_pa=init_p,
            )
            nodes.append(node)
            node_id_to_index[node_id] = idx
            port_to_node_index[(a.asset_id, "OUT")] = idx
            idx += 1

        elif a.type == "DEMAND":
            node_id = str(a.asset_id)
            vol = 0.01  # 10 liter plenum
            cap = vol / (R_AIR * T_REF)
            node = NetworkNode(
                node_id=node_id,
                node_index=idx,
                asset_id=a.asset_id,
                port_group="IN",
                volume_m3=vol,
                capacitance=cap,
                initial_pressure_pa=init_p,
            )
            nodes.append(node)
            node_id_to_index[node_id] = idx
            port_to_node_index[(a.asset_id, "IN")] = idx
            idx += 1

        elif a.type in ("ISOLATION_VALVE", "CONTROL_VALVE"):
            # Internal node A
            node_id_a = f"{a.asset_id}:A"
            vol_a = 0.005  # 5 liter cavity
            cap_a = vol_a / (R_AIR * T_REF)
            node_a = NetworkNode(
                node_id=node_id_a,
                node_index=idx,
                asset_id=a.asset_id,
                port_group="A",
                volume_m3=vol_a,
                capacitance=cap_a,
                initial_pressure_pa=init_p,
            )
            nodes.append(node_a)
            node_id_to_index[node_id_a] = idx
            port_to_node_index[(a.asset_id, "A")] = idx
            idx += 1

            # Internal node B
            node_id_b = f"{a.asset_id}:B"
            vol_b = 0.005
            cap_b = vol_b / (R_AIR * T_REF)
            node_b = NetworkNode(
                node_id=node_id_b,
                node_index=idx,
                asset_id=a.asset_id,
                port_group="B",
                volume_m3=vol_b,
                capacitance=cap_b,
                initial_pressure_pa=init_p,
            )
            nodes.append(node_b)
            node_id_to_index[node_id_b] = idx
            port_to_node_index[(a.asset_id, "B")] = idx
            idx += 1

    num_nodes = len(nodes)
    if num_nodes == 0:
        raise ValueError("Cannot compile empty network with 0 nodes")

    # 2. Build edges: pipes and internal valve conductance
    edges: list[NetworkEdge] = []
    edge_id_to_index: dict[str, int] = {}
    edge_idx = 0

    # Pipes
    sorted_pipes = sorted(definition.pipes, key=lambda p: str(p.pipe_id))
    for p in sorted_pipes:
        from_idx = port_to_node_index[(p.from_port.asset_id, p.from_port.port)]
        to_idx = port_to_node_index[(p.to_port.asset_id, p.to_port.port)]
        edge = NetworkEdge(
            edge_id=str(p.pipe_id),
            from_node=from_idx,
            to_node=to_idx,
            base_conductance=p.conductance_kg_s_pa,
            asset_id=None,
            is_valve=False,
        )
        edges.append(edge)
        edge_id_to_index[str(p.pipe_id)] = edge_idx
        edge_idx += 1

    # Internal Valve edges
    for a in sorted_assets:
        if a.type in ("ISOLATION_VALVE", "CONTROL_VALVE"):
            from_idx = port_to_node_index[(a.asset_id, "A")]
            to_idx = port_to_node_index[(a.asset_id, "B")]
            base_cond = float(a.parameters.get("conductance_kg_s_pa", 2e-7))
            opening = float(a.parameters.get("opening", 1.0))
            valve_edge_id = f"{a.asset_id}:internal"
            edge = NetworkEdge(
                edge_id=valve_edge_id,
                from_node=from_idx,
                to_node=to_idx,
                base_conductance=base_cond * opening,
                asset_id=a.asset_id,
                is_valve=True,
            )
            edges.append(edge)
            edge_id_to_index[valve_edge_id] = edge_idx
            edge_idx += 1

    # 3. Sources & Sinks
    compressors: list[CompressorSource] = []
    for a in sorted_assets:
        if a.type == "COMPRESSOR":
            n_idx = port_to_node_index[(a.asset_id, "OUT")]
            compressors.append(
                CompressorSource(
                    asset_id=a.asset_id,
                    node_index=n_idx,
                    q_nom_kg_s=float(a.parameters.get("q_nom_kg_s", 0.02)),
                    p_max_pa=float(a.parameters.get("p_max_pa", 900000.0)),
                    nominal_load=float(a.parameters.get("load", 1.0)),
                    enabled=bool(a.parameters.get("enabled", True)),
                )
            )

    demands: list[DemandSink] = []
    for a in sorted_assets:
        if a.type == "DEMAND":
            n_idx = port_to_node_index[(a.asset_id, "IN")]
            demands.append(
                DemandSink(
                    asset_id=a.asset_id,
                    node_index=n_idx,
                    base_conductance=float(a.parameters.get("conductance_kg_s_pa", 1e-8)),
                    nominal_load_factor=float(a.parameters.get("load_factor", 1.0)),
                )
            )

    # 4. Sensor targets mapping
    sensor_targets: dict[UUID, tuple[SensorKind, int, int]] = {}
    for s in definition.sensors:
        if s.kind == "PRESSURE":
            # Target is PortRef
            n_idx = port_to_node_index[(s.target.asset_id, s.target.port)]  # type: ignore[union-attr]
            sensor_targets[s.sensor_id] = ("PRESSURE", n_idx, 1)
        elif s.kind == "FLOW":
            # Target is pipe_id UUID
            e_idx = edge_id_to_index[str(s.target)]
            sensor_targets[s.sensor_id] = ("FLOW", e_idx, 1)

    # 5. Precompute constant matrices
    volumes = np.array([n.volume_m3 for n in nodes], dtype=np.float64)
    capacitances = np.array([n.capacitance for n in nodes], dtype=np.float64)
    c_over_dt = capacitances / dt

    # Precalculate Laplacian matrix
    l_base = np.zeros((num_nodes, num_nodes), dtype=np.float64)
    for e in edges:
        k = e.base_conductance
        i = e.from_node
        j = e.to_node
        l_base[i, i] += k
        l_base[j, j] += k
        l_base[i, j] -= k
        l_base[j, i] -= k

    return CompiledNetwork(
        definition_digest=definition.scene_revision,
        nodes=tuple(nodes),
        node_id_to_index=node_id_to_index,
        port_to_node_index=port_to_node_index,
        edges=tuple(edges),
        edge_id_to_index=edge_id_to_index,
        compressors=tuple(compressors),
        demands=tuple(demands),
        sensor_targets=sensor_targets,
        volumes=volumes,
        capacitances=capacitances,
        c_over_dt=c_over_dt,
        base_laplacian=l_base,
    )
