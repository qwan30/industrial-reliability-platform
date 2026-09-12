"""Unit tests for Virtual Lab sensor observation and noise generator."""

from __future__ import annotations

import math
from uuid import uuid4

import numpy as np

from industrial_reliability.lab.catalog import get_reference_lab_definition
from industrial_reliability.lab.contracts import (
    ActiveFault,
    ControlState,
    PhysicalState,
    RunSpec,
    SimulationRun,
)
from industrial_reliability.lab.simulation.sensors import (
    compute_gaussian_noise,
    observe,
)


def test_stateless_noise_deterministic_reproducibility() -> None:
    sensor_id = uuid4()
    seed = 42
    tick = 100

    z1 = compute_gaussian_noise(seed, sensor_id, tick)
    z2 = compute_gaussian_noise(seed, sensor_id, tick)
    assert z1 == z2

    # Different tick gives different sample
    z_diff = compute_gaussian_noise(seed, sensor_id, tick + 1)
    assert z1 != z_diff


def test_noise_distribution_statistics() -> None:
    sensor_id = uuid4()
    seed = 12345
    samples = [compute_gaussian_noise(seed, sensor_id, t) for t in range(5000)]

    mean = float(np.mean(samples))
    std = float(np.std(samples))

    # Standard normal: mean ~ 0, std ~ 1
    assert abs(mean) < 0.05
    assert abs(std - 1.0) < 0.05


def test_observe_with_reference_lab() -> None:
    ref_lab = get_reference_lab_definition()
    run = SimulationRun(
        run_id=uuid4(),
        spec=RunSpec(lab_id=ref_lab.lab_id, lab_revision=1, seed=42, speed=1),
        status="RUNNING",
        definition=ref_lab,
        definition_digest="a" * 64,
        scene_digest="b" * 64,
        profile_digest="c" * 64,
        sampling_digest="d" * 64,
    )

    # Physical state with nominal 400k Pa and 0.02 kg/s flows
    pressures = {str(a.asset_id): 400000.0 for a in ref_lab.assets}
    flows = {str(p.pipe_id): 0.02 for p in ref_lab.pipes}
    state = PhysicalState(tick=20, pressures_pa=pressures, flows_kg_s=flows)

    obs = observe(run, state, ControlState())
    assert len(obs) == len(ref_lab.sensors)

    for o in obs:
        assert o.quality == "GOOD"
        assert o.value is not None
        if o.unit == "Pa":
            # Noise std is 100 Pa, should be around 400k Pa
            assert 395000.0 <= o.value <= 405000.0
        else:
            # Flow around 0.02 kg/s
            assert 0.015 <= o.value <= 0.025


def test_sensor_dropout_fault() -> None:
    ref_lab = get_reference_lab_definition()
    target_sensor = ref_lab.sensors[0]

    run = SimulationRun(
        run_id=uuid4(),
        spec=RunSpec(lab_id=ref_lab.lab_id, lab_revision=1, seed=42, speed=1),
        status="RUNNING",
        definition=ref_lab,
        definition_digest="a" * 64,
        scene_digest="b" * 64,
        profile_digest="c" * 64,
        sampling_digest="d" * 64,
    )

    state = PhysicalState(
        tick=40,
        pressures_pa={str(a.asset_id): 400000.0 for a in ref_lab.assets},
        flows_kg_s={},
    )

    dropout_fault = ActiveFault(target_id=target_sensor.sensor_id, kind="SENSOR_DROPOUT")
    controls = ControlState(active_faults=(dropout_fault,))

    obs = observe(run, state, controls)
    dropout_obs = next(o for o in obs if o.sensor_id == target_sensor.sensor_id)
    assert dropout_obs.quality == "MISSING"
    assert dropout_obs.value is None


def test_sensor_bias_fault() -> None:
    ref_lab = get_reference_lab_definition()
    target_sensor = next(s for s in ref_lab.sensors if s.kind == "PRESSURE")

    run = SimulationRun(
        run_id=uuid4(),
        spec=RunSpec(lab_id=ref_lab.lab_id, lab_revision=1, seed=42, speed=1),
        status="RUNNING",
        definition=ref_lab,
        definition_digest="a" * 64,
        scene_digest="b" * 64,
        profile_digest="c" * 64,
        sampling_digest="d" * 64,
    )

    state = PhysicalState(
        tick=60,
        pressures_pa={str(a.asset_id): 400000.0 for a in ref_lab.assets},
        flows_kg_s={},
    )

    # Baseline observation without bias
    obs_clean = observe(run, state, ControlState())
    val_clean = next(o.value for o in obs_clean if o.sensor_id == target_sensor.sensor_id)
    assert val_clean is not None

    # Apply 150000 Pa bias
    bias_fault = ActiveFault(
        target_id=target_sensor.sensor_id, kind="SENSOR_BIAS", values={"bias": 150000.0}
    )
    obs_biased = observe(run, state, ControlState(active_faults=(bias_fault,)))
    val_biased = next(o.value for o in obs_biased if o.sensor_id == target_sensor.sensor_id)
    assert val_biased is not None

    # Shift should match bias exactly
    assert math.isclose(val_biased - val_clean, 150000.0, rel_tol=1e-9)
