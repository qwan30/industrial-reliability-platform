"""Catalog definitions and reference lab templates."""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from industrial_reliability.lab.contracts import (
    DEFAULT_PARAMETERS_BY_ASSET_TYPE,
    VALID_PORTS_BY_ASSET_TYPE,
    Asset,
    AssetType,
    LabDefinition,
    Pipe,
    PortRef,
    Sensor,
)

NAMESPACE_LAB = uuid.uuid5(uuid.NAMESPACE_URL, "https://industrial-reliability.local/lab")


def get_catalog() -> dict[str, Any]:
    """Return catalog metadata including asset types, parameters, ports, and defaults."""
    assets_catalog = {}
    for asset_type, ports in VALID_PORTS_BY_ASSET_TYPE.items():
        assets_catalog[asset_type] = {
            "type": asset_type,
            "ports": list(ports),
            "parameters": DEFAULT_PARAMETERS_BY_ASSET_TYPE[asset_type],
        }
    return {
        "catalog_version": "lab-catalog-v1",
        "assets": assets_catalog,
        "supported_models": ["pneumatic-isothermal-v1"],
    }


def get_reference_lab_definition() -> LabDefinition:
    """Construct deterministic 4-train reference lab definition.

    Layout:
    4 trains, Z: [-4.5, -1.5, 1.5, 4.5] m
    X: COMPRESSOR (-8m), TANK (-4m), ISOLATION_VALVE (0m), CONTROL_VALVE (3m), DEMAND (7m)
    Pipes per train:
      OUT -> tankA
      tankB -> isoA
      isoB -> controlA
      controlB -> demandIN
    Cross pipes:
      tankB train 1 <-> tankB train 2
      tankB train 3 <-> tankB train 4
    Sensors per train:
      pressure: compressorOUT, tankB, demandIN (3 * 4 = 12)
      flow: first pipe (compressor->tank), last pipe (control->demand) (2 * 4 = 8)
      Total = 20 sensors
    """
    lab_id = uuid.uuid5(NAMESPACE_LAB, "reference-pneumatic-v1")
    z_coords = [-4.5, -1.5, 1.5, 4.5]
    x_coords = {
        "COMPRESSOR": -8.0,
        "TANK": -4.0,
        "ISOLATION_VALVE": 0.0,
        "CONTROL_VALVE": 3.0,
        "DEMAND": 7.0,
    }

    assets: list[Asset] = []
    pipes: list[Pipe] = []
    sensors: list[Sensor] = []

    # Map for easy lookup during wiring: (train_idx, asset_type) -> Asset
    train_assets: dict[tuple[int, AssetType], Asset] = {}

    for t_idx, z in enumerate(z_coords, start=1):
        # 1. Compressor
        comp_id = uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:compressor")
        comp = Asset(
            asset_id=comp_id,
            type="COMPRESSOR",
            position_m=(x_coords["COMPRESSOR"], 0.0, z),
            rotation_y_rad=0.0,
            parameters=dict(DEFAULT_PARAMETERS_BY_ASSET_TYPE["COMPRESSOR"]),
        )
        assets.append(comp)
        train_assets[(t_idx, "COMPRESSOR")] = comp

        # 2. Tank
        tank_id = uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:tank")
        tank = Asset(
            asset_id=tank_id,
            type="TANK",
            position_m=(x_coords["TANK"], 0.0, z),
            rotation_y_rad=0.0,
            parameters=dict(DEFAULT_PARAMETERS_BY_ASSET_TYPE["TANK"]),
        )
        assets.append(tank)
        train_assets[(t_idx, "TANK")] = tank

        # 3. Isolation Valve
        iso_id = uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:isolation_valve")
        iso = Asset(
            asset_id=iso_id,
            type="ISOLATION_VALVE",
            position_m=(x_coords["ISOLATION_VALVE"], 0.0, z),
            rotation_y_rad=0.0,
            parameters=dict(DEFAULT_PARAMETERS_BY_ASSET_TYPE["ISOLATION_VALVE"]),
        )
        assets.append(iso)
        train_assets[(t_idx, "ISOLATION_VALVE")] = iso

        # 4. Control Valve
        ctrl_id = uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:control_valve")
        ctrl = Asset(
            asset_id=ctrl_id,
            type="CONTROL_VALVE",
            position_m=(x_coords["CONTROL_VALVE"], 0.0, z),
            rotation_y_rad=0.0,
            parameters=dict(DEFAULT_PARAMETERS_BY_ASSET_TYPE["CONTROL_VALVE"]),
        )
        assets.append(ctrl)
        train_assets[(t_idx, "CONTROL_VALVE")] = ctrl

        # 5. Demand
        dem_id = uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:demand")
        dem = Asset(
            asset_id=dem_id,
            type="DEMAND",
            position_m=(x_coords["DEMAND"], 0.0, z),
            rotation_y_rad=0.0,
            parameters=dict(DEFAULT_PARAMETERS_BY_ASSET_TYPE["DEMAND"]),
        )
        assets.append(dem)
        train_assets[(t_idx, "DEMAND")] = dem

        # Intra-train pipes
        # Pipe 1: Compressor OUT -> Tank A
        p1_id = uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:pipe_comp_tank")
        p1 = Pipe(
            pipe_id=p1_id,
            from_port=PortRef(asset_id=comp_id, port="OUT"),
            to_port=PortRef(asset_id=tank_id, port="A"),
            conductance_kg_s_pa=2e-7,
        )
        pipes.append(p1)

        # Pipe 2: Tank B -> Iso Valve A
        p2_id = uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:pipe_tank_iso")
        p2 = Pipe(
            pipe_id=p2_id,
            from_port=PortRef(asset_id=tank_id, port="B"),
            to_port=PortRef(asset_id=iso_id, port="A"),
            conductance_kg_s_pa=2e-7,
        )
        pipes.append(p2)

        # Pipe 3: Iso Valve B -> Control Valve A
        p3_id = uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:pipe_iso_ctrl")
        p3 = Pipe(
            pipe_id=p3_id,
            from_port=PortRef(asset_id=iso_id, port="B"),
            to_port=PortRef(asset_id=ctrl_id, port="A"),
            conductance_kg_s_pa=2e-7,
        )
        pipes.append(p3)

        # Pipe 4: Control Valve B -> Demand IN
        p4_id = uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:pipe_ctrl_dem")
        p4 = Pipe(
            pipe_id=p4_id,
            from_port=PortRef(asset_id=ctrl_id, port="B"),
            to_port=PortRef(asset_id=dem_id, port="IN"),
            conductance_kg_s_pa=2e-7,
        )
        pipes.append(p4)

        # Sensors per train:
        # Pressure sensor 1: Compressor OUT
        s_p_comp = Sensor(
            sensor_id=uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:sensor_p_comp"),
            kind="PRESSURE",
            target=PortRef(asset_id=comp_id, port="OUT"),
            noise_std=100.0,
            alarm_low=250000.0,
            alarm_high=850000.0,
        )
        # Pressure sensor 2: Tank B
        s_p_tank = Sensor(
            sensor_id=uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:sensor_p_tank"),
            kind="PRESSURE",
            target=PortRef(asset_id=tank_id, port="B"),
            noise_std=100.0,
            alarm_low=250000.0,
            alarm_high=850000.0,
        )
        # Pressure sensor 3: Demand IN
        s_p_dem = Sensor(
            sensor_id=uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:sensor_p_dem"),
            kind="PRESSURE",
            target=PortRef(asset_id=dem_id, port="IN"),
            noise_std=100.0,
            alarm_low=250000.0,
            alarm_high=850000.0,
        )
        # Flow sensor 1: on Pipe 1 (Compressor -> Tank)
        s_f_comp = Sensor(
            sensor_id=uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:sensor_f_comp"),
            kind="FLOW",
            target=p1_id,
            noise_std=1e-5,
            alarm_low=-0.05,
            alarm_high=0.05,
        )
        # Flow sensor 2: on Pipe 4 (Control -> Demand)
        s_f_dem = Sensor(
            sensor_id=uuid.uuid5(NAMESPACE_LAB, f"ref:train_{t_idx}:sensor_f_dem"),
            kind="FLOW",
            target=p4_id,
            noise_std=1e-5,
            alarm_low=-0.05,
            alarm_high=0.05,
        )

        sensors.extend([s_p_comp, s_p_tank, s_p_dem, s_f_comp, s_f_dem])

    # Cross pipes:
    # Cross pipe 1: Tank B train 1 <-> Tank A train 2 (using valid ports: train1 tankB to train2 tankA)
    # Tank has ports A and B. Train 1 tank A is connected to compressor OUT. Train 1 tank B is connected to iso A.
    # A port can receive multiple pipes (junction as per plan Section 6.1: "Port nhận nhiều pipes là junction").
    cross_p1_id = uuid.uuid5(NAMESPACE_LAB, "ref:crosspipe_train_1_2")
    cross_p1 = Pipe(
        pipe_id=cross_p1_id,
        from_port=PortRef(asset_id=train_assets[(1, "TANK")].asset_id, port="B"),
        to_port=PortRef(asset_id=train_assets[(2, "TANK")].asset_id, port="B"),
        conductance_kg_s_pa=2e-7,
    )
    pipes.append(cross_p1)

    # Cross pipe 2: Tank B train 3 <-> Tank B train 4
    cross_p2_id = uuid.uuid5(NAMESPACE_LAB, "ref:crosspipe_train_3_4")
    cross_p2 = Pipe(
        pipe_id=cross_p2_id,
        from_port=PortRef(asset_id=train_assets[(3, "TANK")].asset_id, port="B"),
        to_port=PortRef(asset_id=train_assets[(4, "TANK")].asset_id, port="B"),
        conductance_kg_s_pa=2e-7,
    )
    pipes.append(cross_p2)

    return LabDefinition(
        schema_version="lab-definition-v1",
        lab_id=lab_id,
        revision=1,
        name="Reference Pneumatic Lab",
        assets=tuple(assets),
        pipes=tuple(pipes),
        sensors=tuple(sensors),
        scene_revision="scene-v1",
    )


def clone_lab_definition(template: LabDefinition, new_lab_id: UUID, new_name: str) -> LabDefinition:
    """Clone a LabDefinition, remapping all internal UUIDs to fresh IDs."""
    id_map: dict[UUID, UUID] = {}

    def get_new_id(old_id: UUID) -> UUID:
        if old_id not in id_map:
            id_map[old_id] = uuid.uuid4()
        return id_map[old_id]

    # Pre-populate asset IDs
    for a in template.assets:
        get_new_id(a.asset_id)

    # Pre-populate pipe IDs
    for p in template.pipes:
        get_new_id(p.pipe_id)

    # Clone assets
    new_assets = []
    for a in template.assets:
        new_assets.append(
            Asset(
                asset_id=id_map[a.asset_id],
                type=a.type,
                position_m=a.position_m,
                rotation_y_rad=a.rotation_y_rad,
                parameters=dict(a.parameters),
            )
        )

    # Clone pipes
    new_pipes = []
    for p in template.pipes:
        new_pipes.append(
            Pipe(
                pipe_id=id_map[p.pipe_id],
                from_port=PortRef(
                    asset_id=id_map[p.from_port.asset_id],
                    port=p.from_port.port,
                ),
                to_port=PortRef(
                    asset_id=id_map[p.to_port.asset_id],
                    port=p.to_port.port,
                ),
                conductance_kg_s_pa=p.conductance_kg_s_pa,
                waypoints_m=p.waypoints_m,
            )
        )

    # Clone sensors
    new_sensors = []
    for s in template.sensors:
        new_target: PortRef | UUID
        if s.kind == "PRESSURE":
            assert isinstance(s.target, PortRef)
            new_target = PortRef(
                asset_id=id_map[s.target.asset_id],
                port=s.target.port,
            )
        else:
            assert isinstance(s.target, UUID)
            new_target = id_map[s.target]
        new_sensors.append(
            Sensor(
                sensor_id=uuid.uuid4(),
                kind=s.kind,
                target=new_target,
                noise_std=s.noise_std,
                alarm_low=s.alarm_low,
                alarm_high=s.alarm_high,
            )
        )

    return LabDefinition(
        schema_version=template.schema_version,
        lab_id=new_lab_id,
        revision=1,
        name=new_name,
        assets=tuple(new_assets),
        pipes=tuple(new_pipes),
        sensors=tuple(new_sensors),
        scene_revision=template.scene_revision,
    )
