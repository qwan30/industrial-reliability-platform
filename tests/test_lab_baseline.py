"""Unit tests for Virtual Lab synthetic baseline calibration and feature extraction."""

from __future__ import annotations

import math
from uuid import uuid4

import pytest

from industrial_reliability.lab.baseline import (
    extract_window_features,
    run_synthetic_session,
    train_synthetic_baseline,
)
from industrial_reliability.lab.contracts import (
    Asset,
    LabDefinition,
    Pipe,
    PortRef,
    Sensor,
)


def test_window_feature_extraction_accuracy() -> None:
    # Constant values -> mean = 5.0, std = 0.0, slope = 0.0
    const_feats = extract_window_features([5.0] * 10, dt_sample=1.0)
    assert math.isclose(const_feats.mean, 5.0)
    assert math.isclose(const_feats.std_pop, 0.0)
    assert math.isclose(const_feats.slope_per_sec, 0.0)

    # Linear ramp: [0, 1, 2, 3, 4] with dt=1.0 -> slope = 1.0
    ramp_feats = extract_window_features([0.0, 1.0, 2.0, 3.0, 4.0], dt_sample=1.0)
    assert math.isclose(ramp_feats.mean, 2.0)
    assert math.isclose(ramp_feats.slope_per_sec, 1.0)


@pytest.fixture
def mini_lab() -> LabDefinition:
    """Minimal viable 1-train lab for fast baseline calibration tests."""
    c_id = uuid4()
    t_id = uuid4()

    comp = Asset(
        asset_id=c_id,
        type="COMPRESSOR",
        position_m=(-2, 0, 0),
        rotation_y_rad=0,
        parameters={"q_nom_kg_s": 0.02, "p_max_pa": 900000.0, "initial_pressure_pa": 400000.0},
    )
    tank = Asset(
        asset_id=t_id,
        type="TANK",
        position_m=(2, 0, 0),
        rotation_y_rad=0,
        parameters={"volume_m3": 0.5, "initial_pressure_pa": 400000.0},
    )

    pipe = Pipe(
        pipe_id=uuid4(),
        from_port=PortRef(asset_id=c_id, port="OUT"),
        to_port=PortRef(asset_id=t_id, port="A"),
        conductance_kg_s_pa=2e-7,
    )

    p_sensor = Sensor(
        sensor_id=uuid4(),
        kind="PRESSURE",
        target=PortRef(asset_id=t_id, port="B"),
        noise_std=100.0,
        alarm_low=250000.0,
        alarm_high=850000.0,
    )

    return LabDefinition(
        lab_id=uuid4(),
        revision=1,
        name="Mini Lab",
        assets=(comp, tank),
        pipes=(pipe,),
        sensors=(p_sensor,),
    )


def test_run_synthetic_session(mini_lab: LabDefinition) -> None:
    readings = run_synthetic_session(mini_lab, seed=100, total_seconds=10, warmup_seconds=2)
    sensor_id = mini_lab.sensors[0].sensor_id
    assert sensor_id in readings
    # 8 seconds of observations at 1Hz = 8 samples
    assert len(readings[sensor_id]) >= 8
    assert all(math.isfinite(x) for x in readings[sensor_id])


def test_train_synthetic_baseline_mini_lab(mini_lab: LabDefinition) -> None:
    # Run fast baseline training
    artifact, report = train_synthetic_baseline(mini_lab, base_seed=42)

    assert artifact["status"] == "EXPERIMENTAL"
    assert artifact["schema_version"] == "lab-synthetic-baseline-v1"
    assert len(artifact["thresholds"]) == 1

    assert report["status"] == "COMPLETE"
    assert report["verdict"] == "EXPERIMENTAL_CALIBRATION"
    assert report["sensors_calibrated"] == 1
    assert report["sensors_unavailable"] == 0
    assert len(report["fault_evaluations"]) == 6
