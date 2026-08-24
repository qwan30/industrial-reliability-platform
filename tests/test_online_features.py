from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from industrial_reliability.online_features import (
    BuilderResult,
    OnlineFeatureBuilder,
)
from industrial_reliability.phase1b_contracts import PHASE1B
from industrial_reliability.phase1b_features import iter_phase1b_windows
from industrial_reliability.runtime_messages import TelemetryEventV1
from tests.helpers_replay import make_sample_telemetry_event


def _sample_dataframe_window(
    start_time: datetime, n_minutes: int = 40, samples_per_min: int = 6
) -> pd.DataFrame:
    records = []
    total_samples = n_minutes * samples_per_min
    for i in range(total_samples):
        ts = start_time + timedelta(seconds=10 * i)
        records.append(
            {
                "timestamp": ts,
                "tp2": 1.0 + i * 0.01,
                "tp3": 2.0 + i * 0.01,
                "h1": 3.0 + i * 0.01,
                "dv_pressure": 4.0 + i * 0.01,
                "reservoirs": 5.0 + i * 0.01,
                "oil_temperature": 6.0 + i * 0.01,
                "motor_current": 7.0 + i * 0.01,
                "comp": 1 if i % 2 == 0 else 0,
                "dv_electric": 0,
                "towers": 1,
                "mpg": 0,
                "lps": 1,
                "pressure_switch": 0,
                "oil_level": 1,
                "caudal_impulses": 0,
            }
        )
    return pd.DataFrame(records)


def _telemetry_events_from_df(df: pd.DataFrame, session_id: uuid4) -> list[TelemetryEventV1]:
    events = []
    for idx, row in df.iterrows():
        events.append(
            TelemetryEventV1(
                message_id=uuid4(),
                replay_session_id=session_id,
                source_dataset_sha256="a" * 64,
                contract_sha256="b" * 64,
                source_timestamp=row["timestamp"],
                emitted_at=datetime.now(UTC),
                machine_id="compressor-01",
                sequence=int(idx) + 1,
                tp2=float(row["tp2"]),
                tp3=float(row["tp3"]),
                h1=float(row["h1"]),
                dv_pressure=float(row["dv_pressure"]),
                reservoirs=float(row["reservoirs"]),
                oil_temperature=float(row["oil_temperature"]),
                motor_current=float(row["motor_current"]),
                comp=int(row["comp"]),
                dv_electric=int(row["dv_electric"]),
                towers=int(row["towers"]),
                mpg=int(row["mpg"]),
                lps=int(row["lps"]),
                pressure_switch=int(row["pressure_switch"]),
                oil_level=int(row["oil_level"]),
                caudal_impulses=int(row["caudal_impulses"]),
            )
        )
    return events


def test_online_features_equal_phase1b_offline_rows() -> None:
    session_id = uuid4()
    # In Phase 1B holdout split: 2020-03-01 04:00:00 is in holdout
    start_ts = datetime(2020, 3, 1, 4, 0, 0)
    df = _sample_dataframe_window(start_ts, n_minutes=45, samples_per_min=6)
    events = _telemetry_events_from_df(df, session_id)

    analog_cols = PHASE1B.analog_columns
    digital_cols = tuple(c for c in PHASE1B.digital_columns if c in PHASE1B.predictor_columns)
    from industrial_reliability.causal_features import get_candidate_feature_names

    feature_names = get_candidate_feature_names(analog_cols, digital_cols)

    builder = OnlineFeatureBuilder(
        replay_session_id=session_id,
        machine_id="compressor-01",
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        feature_names=feature_names,
    )

    emitted_features = []
    for ev in events:
        res = builder.push(ev)
        emitted_features.extend(res.features)

    complete_res = builder.complete(df["timestamp"].iloc[-1])
    emitted_features.extend(complete_res.features)

    offline_windows = list(iter_phase1b_windows(df, PHASE1B))

    assert len(emitted_features) == len(offline_windows)
    for actual, expected in zip(emitted_features, offline_windows, strict=True):
        assert actual.feature_names == expected.feature_names
        np.testing.assert_allclose(
            actual.feature_values, expected.feature_values, rtol=0.0, atol=1e-12
        )
        assert actual.window_start == expected.window_start
        assert actual.window_end == expected.window_end


@pytest.mark.parametrize(
    "fault",
    ["sequence_gap", "conflicting_duplicate", "timestamp_regression", "invalid_bin"],
)
def test_stream_fault_closes_segment(fault: str) -> None:
    session_id = uuid4()
    start_ts = datetime(2020, 3, 1, 4, 0, 0)
    df = _sample_dataframe_window(start_ts, n_minutes=15, samples_per_min=6)
    events = _telemetry_events_from_df(df, session_id)

    builder = OnlineFeatureBuilder(
        replay_session_id=session_id,
        machine_id="compressor-01",
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        feature_names=("tp2_mean", "dv_pressure_mean"),
    )

    for ev in events:
        builder.push(ev)

    # Now introduce fault event
    last_ev = events[-1]
    fault_res: BuilderResult

    if fault == "sequence_gap":
        bad_ev = make_sample_telemetry_event(
            sequence=last_ev.sequence + 5,
            session_id=session_id,
            source_timestamp=last_ev.source_timestamp + timedelta(seconds=10),
        )
        fault_res = builder.push(bad_ev)
        assert fault_res.segment_closed_reason == "sequence_gap"

    elif fault == "conflicting_duplicate":
        bad_ev = make_sample_telemetry_event(
            sequence=last_ev.sequence,
            session_id=session_id,
            source_timestamp=last_ev.source_timestamp,
        )
        fault_res = builder.push(bad_ev)
        assert fault_res.segment_closed_reason == "conflicting_duplicate"

    elif fault == "timestamp_regression":
        bad_ev = make_sample_telemetry_event(
            sequence=last_ev.sequence + 1,
            session_id=session_id,
            source_timestamp=last_ev.source_timestamp - timedelta(seconds=60),
        )
        fault_res = builder.push(bad_ev)
        assert fault_res.segment_closed_reason == "timestamp_regression"

    elif fault == "invalid_bin":
        # Jump forward by 20 minutes (skipping multiple bins)
        bad_ev = make_sample_telemetry_event(
            sequence=last_ev.sequence + 1,
            session_id=session_id,
            source_timestamp=last_ev.source_timestamp + timedelta(minutes=20),
        )
        fault_res = builder.push(bad_ev)
        assert fault_res.segment_closed_reason == "invalid_bin"


def test_exact_duplicate_is_noop() -> None:
    session_id = uuid4()
    builder = OnlineFeatureBuilder(
        replay_session_id=session_id,
        machine_id="compressor-01",
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        feature_names=("tp2_mean", "dv_pressure_mean"),
    )

    ev = make_sample_telemetry_event(sequence=1, session_id=session_id)
    res1 = builder.push(ev)
    assert res1.segment_closed_reason is None

    # Push exact duplicate
    res2 = builder.push(ev)
    assert res2.segment_closed_reason is None
    assert len(res2.features) == 0
