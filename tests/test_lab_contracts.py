"""Unit tests for Virtual Lab domain contracts, catalog, and validation rules."""

from __future__ import annotations

import uuid
from uuid import uuid4

import pytest
from pydantic import ValidationError

from industrial_reliability.lab.catalog import (
    clone_lab_definition,
    get_catalog,
    get_reference_lab_definition,
)
from industrial_reliability.lab.contracts import (
    Asset,
    LabDefinition,
    Pipe,
    PortRef,
    Sensor,
    compute_definition_digest,
    validate_lab,
)


def test_catalog_metadata_structure() -> None:
    catalog = get_catalog()
    assert catalog["catalog_version"] == "lab-catalog-v1"
    assert "COMPRESSOR" in catalog["assets"]
    assert "TANK" in catalog["assets"]
    assert "ISOLATION_VALVE" in catalog["assets"]
    assert "CONTROL_VALVE" in catalog["assets"]
    assert "DEMAND" in catalog["assets"]
    assert "pneumatic-isothermal-v1" in catalog["supported_models"]


def test_reference_lab_construction_and_validation() -> None:
    ref_lab = get_reference_lab_definition()
    assert len(ref_lab.assets) == 20
    assert len(ref_lab.pipes) == 18
    assert len(ref_lab.sensors) == 20

    res = validate_lab(ref_lab)
    assert res.run_eligible is True
    assert len(res.errors) == 0
    assert len(res.definition_digest) == 64


def test_clone_lab_definition_remaps_all_ids() -> None:
    ref_lab = get_reference_lab_definition()
    new_id = uuid4()
    cloned = clone_lab_definition(ref_lab, new_id, "Cloned Test Lab")

    assert cloned.lab_id == new_id
    assert cloned.name == "Cloned Test Lab"
    assert cloned.revision == 1

    # Verify asset IDs are different
    original_asset_ids = {a.asset_id for a in ref_lab.assets}
    cloned_asset_ids = {a.asset_id for a in cloned.assets}
    assert len(original_asset_ids.intersection(cloned_asset_ids)) == 0

    # Verify pipe port refs point to cloned asset IDs
    for p in cloned.pipes:
        assert p.from_port.asset_id in cloned_asset_ids
        assert p.to_port.asset_id in cloned_asset_ids

    # Verify sensor targets point to cloned assets or pipes
    cloned_pipe_ids = {p.pipe_id for p in cloned.pipes}
    for s in cloned.sensors:
        if s.kind == "PRESSURE":
            assert isinstance(s.target, PortRef)
            assert s.target.asset_id in cloned_asset_ids
        else:
            assert isinstance(s.target, uuid.UUID)
            assert s.target in cloned_pipe_ids

    res = validate_lab(cloned)
    assert res.run_eligible is True


def test_empty_lab_validation_fails_run_eligibility() -> None:
    empty_lab = LabDefinition(
        lab_id=uuid4(),
        revision=1,
        name="Empty Lab",
        assets=(),
        pipes=(),
        sensors=(),
    )
    res = validate_lab(empty_lab)
    assert res.run_eligible is False
    assert any(e.code == "EMPTY_LAB" for e in res.errors)


def test_sensorless_valid_lab_is_run_eligible() -> None:
    ref_lab = get_reference_lab_definition()
    sensorless = ref_lab.model_copy(update={"sensors": ()})
    res = validate_lab(sensorless)
    assert res.run_eligible is True
    assert len(res.errors) == 0


def test_asset_bounds_and_coordinates() -> None:
    # Valid compressor
    a = Asset(
        asset_id=uuid4(),
        type="COMPRESSOR",
        position_m=(0.0, 0.0, 0.0),
        rotation_y_rad=0.0,
        parameters={"q_nom_kg_s": 0.05, "p_max_pa": 800000.0, "load": 1.0, "enabled": True},
    )
    assert a.type == "COMPRESSOR"

    # X out of bounds
    with pytest.raises(ValidationError):
        Asset(
            asset_id=uuid4(),
            type="COMPRESSOR",
            position_m=(15.0, 0.0, 0.0),
            rotation_y_rad=0.0,
        )

    # Y non-zero
    with pytest.raises(ValidationError):
        Asset(
            asset_id=uuid4(),
            type="COMPRESSOR",
            position_m=(0.0, 1.0, 0.0),
            rotation_y_rad=0.0,
        )

    # Extra parameters forbidden
    with pytest.raises(ValidationError):
        Asset(
            asset_id=uuid4(),
            type="COMPRESSOR",
            position_m=(0.0, 0.0, 0.0),
            rotation_y_rad=0.0,
            parameters={"non_existent_param": 123.0},
        )

    # Initial pressure out of range
    with pytest.raises(ValidationError):
        Asset(
            asset_id=uuid4(),
            type="COMPRESSOR",
            position_m=(0.0, 0.0, 0.0),
            rotation_y_rad=0.0,
            parameters={"initial_pressure_pa": 50000.0},
        )


def test_pipe_validation_and_self_loops() -> None:
    asset_id = uuid4()
    # Connecting a port to itself is rejected
    with pytest.raises(ValidationError):
        Pipe(
            pipe_id=uuid4(),
            from_port=PortRef(asset_id=asset_id, port="OUT"),
            to_port=PortRef(asset_id=asset_id, port="OUT"),
        )

    # Too many waypoints (>16)
    with pytest.raises(ValidationError):
        Pipe(
            pipe_id=uuid4(),
            from_port=PortRef(asset_id=asset_id, port="A"),
            to_port=PortRef(asset_id=uuid4(), port="B"),
            waypoints_m=tuple((float(i), 0.0, float(i)) for i in range(20)),
        )


def test_sensor_target_and_alarm_hysteresis_validation() -> None:
    asset_id = uuid4()
    # Pressure sensor must have PortRef target
    with pytest.raises(ValidationError):
        Sensor(
            sensor_id=uuid4(),
            kind="PRESSURE",
            target=uuid4(),
            noise_std=100.0,
        )

    # Flow sensor must have UUID target
    with pytest.raises(ValidationError):
        Sensor(
            sensor_id=uuid4(),
            kind="FLOW",
            target=PortRef(asset_id=asset_id, port="A"),
            noise_std=1e-5,
        )

    # Alarm low + hysteresis >= alarm high - hysteresis must fail
    # For pressure, hysteresis is 10000 Pa:
    with pytest.raises(ValidationError):
        Sensor(
            sensor_id=uuid4(),
            kind="PRESSURE",
            target=PortRef(asset_id=asset_id, port="OUT"),
            noise_std=100.0,
            alarm_low=500000.0,
            alarm_high=510000.0,  # 500000 + 10000 = 510000 >= 510000 - 10000 (500000)
        )


def test_deterministic_definition_digest() -> None:
    ref1 = get_reference_lab_definition()
    ref2 = get_reference_lab_definition()
    digest1 = compute_definition_digest(ref1)
    digest2 = compute_definition_digest(ref2)
    assert digest1 == digest2
    assert len(digest1) == 64
