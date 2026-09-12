"""Unit tests for Virtual Lab process limit and data quality rules engine."""

from __future__ import annotations

from uuid import uuid4

import pytest

from industrial_reliability.lab.analysis import (
    SensorAnalysisState,
    evaluate_sensor_observation,
)
from industrial_reliability.lab.contracts import Observation, PortRef, Sensor


@pytest.fixture
def test_sensor() -> Sensor:
    return Sensor(
        sensor_id=uuid4(),
        kind="PRESSURE",
        target=PortRef(asset_id=uuid4(), port="OUT"),
        noise_std=100.0,
        alarm_low=250000.0,
        alarm_high=850000.0,
    )


def test_process_limit_above_threshold_opens_and_resolves(test_sensor: Sensor) -> None:
    state = SensorAnalysisState(sensor_id=test_sensor.sensor_id)
    assert isinstance(test_sensor.target, PortRef)
    run_id = uuid4()
    asset_id = test_sensor.target.asset_id

    # 1. First 2 high samples: violations=2, no alert yet
    for i in (1, 2):
        obs = Observation(
            run_id=run_id,
            asset_id=asset_id,
            sensor_id=test_sensor.sensor_id,
            tick=i * 20,
            unit="Pa",
            value=900000.0,  # > 850000
            quality="GOOD",
            profile_digest="digest",
        )
        alerts, _ = evaluate_sensor_observation(obs, test_sensor, state)
        assert len(alerts) == 0
        assert state.high_violations == i

    # 2. 3rd high sample: opens PROCESS_LIMIT alert
    obs3 = Observation(
        run_id=run_id,
        asset_id=asset_id,
        sensor_id=test_sensor.sensor_id,
        tick=60,
        unit="Pa",
        value=900000.0,
        quality="GOOD",
        profile_digest="digest",
    )
    alerts3, _ = evaluate_sensor_observation(obs3, test_sensor, state)
    assert len(alerts3) == 1
    assert alerts3[0].state == "OPEN"
    assert alerts3[0].origin == "PROCESS_LIMIT"
    assert alerts3[0].kind == "ABOVE_LIMIT"
    assert state.active_process_alert is not None

    # 3. 4 samples inside boundary (800000 Pa < 840000 hysteresis threshold): alert remains OPEN
    for i in range(4):
        obs_norm = Observation(
            run_id=run_id,
            asset_id=asset_id,
            sensor_id=test_sensor.sensor_id,
            tick=80 + i * 20,
            unit="Pa",
            value=800000.0,
            quality="GOOD",
            profile_digest="digest",
        )
        alerts_norm, _ = evaluate_sensor_observation(obs_norm, test_sensor, state)
        assert len(alerts_norm) == 0
        assert state.active_process_alert is not None

    # 4. 5th normal sample: alert resolves!
    obs_resolve = Observation(
        run_id=run_id,
        asset_id=asset_id,
        sensor_id=test_sensor.sensor_id,
        tick=160,
        unit="Pa",
        value=800000.0,
        quality="GOOD",
        profile_digest="digest",
    )
    alerts_res, _ = evaluate_sensor_observation(obs_resolve, test_sensor, state)
    assert len(alerts_res) == 1
    assert alerts_res[0].state == "RESOLVED"
    assert state.active_process_alert is None


def test_data_quality_missing_and_resolution(test_sensor: Sensor) -> None:
    state = SensorAnalysisState(sensor_id=test_sensor.sensor_id)
    assert isinstance(test_sensor.target, PortRef)
    run_id = uuid4()
    asset_id = test_sensor.target.asset_id

    # 1. First MISSING: streak=1, no alert
    obs1 = Observation(
        run_id=run_id,
        asset_id=asset_id,
        sensor_id=test_sensor.sensor_id,
        tick=20,
        unit="Pa",
        value=None,
        quality="MISSING",
        profile_digest="digest",
    )
    alerts1, _ = evaluate_sensor_observation(obs1, test_sensor, state)
    assert len(alerts1) == 0

    # 2. 2nd MISSING: opens DATA_QUALITY alert
    obs2 = Observation(
        run_id=run_id,
        asset_id=asset_id,
        sensor_id=test_sensor.sensor_id,
        tick=40,
        unit="Pa",
        value=None,
        quality="MISSING",
        profile_digest="digest",
    )
    alerts2, _ = evaluate_sensor_observation(obs2, test_sensor, state)
    assert len(alerts2) == 1
    assert alerts2[0].origin == "DATA_QUALITY"
    assert alerts2[0].kind == "MISSING"
    assert alerts2[0].state == "OPEN"

    # 3. 2 GOOD samples: alert still open
    for i in (1, 2):
        obs_good = Observation(
            run_id=run_id,
            asset_id=asset_id,
            sensor_id=test_sensor.sensor_id,
            tick=40 + i * 20,
            unit="Pa",
            value=400000.0,
            quality="GOOD",
            profile_digest="digest",
        )
        alerts_good, _ = evaluate_sensor_observation(obs_good, test_sensor, state)
        assert len(alerts_good) == 0
        assert state.active_quality_alert is not None

    # 4. 3rd consecutive GOOD sample: alert resolves!
    obs_res = Observation(
        run_id=run_id,
        asset_id=asset_id,
        sensor_id=test_sensor.sensor_id,
        tick=100,
        unit="Pa",
        value=400000.0,
        quality="GOOD",
        profile_digest="digest",
    )
    alerts_res, _ = evaluate_sensor_observation(obs_res, test_sensor, state)
    assert len(alerts_res) == 1
    assert alerts_res[0].state == "RESOLVED"
    assert state.active_quality_alert is None


def test_independent_sensor_streaks(test_sensor: Sensor) -> None:
    sensor_b = Sensor(
        sensor_id=uuid4(),
        kind="PRESSURE",
        target=PortRef(asset_id=uuid4(), port="OUT"),
        noise_std=100.0,
        alarm_low=250000.0,
        alarm_high=850000.0,
    )
    state_a = SensorAnalysisState(sensor_id=test_sensor.sensor_id)
    state_b = SensorAnalysisState(sensor_id=sensor_b.sensor_id)

    # Sensor A gets bad quality
    obs_a = Observation(
        run_id=uuid4(),
        asset_id=test_sensor.target.asset_id,
        sensor_id=test_sensor.sensor_id,
        tick=20,
        unit="Pa",
        value=None,
        quality="MISSING",
        profile_digest="digest",
    )
    evaluate_sensor_observation(obs_a, test_sensor, state_a)
    assert state_a.bad_quality_streak == 1
    assert state_b.bad_quality_streak == 0
