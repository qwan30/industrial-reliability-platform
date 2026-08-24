from __future__ import annotations

from datetime import datetime

import numpy as np

from industrial_reliability.causal_features import (
    TelemetrySample,
    _all_candidate_statistics,
    compute_feature_values,
    get_candidate_feature_names,
)


def test_candidate_feature_names_exclude_lps() -> None:
    analog = ("tp2", "tp3")
    digital = ("comp", "mpg")
    names = get_candidate_feature_names(analog, digital)
    assert "tp2_mean" in names
    assert "comp_active_ratio" in names
    assert "lps_mean" not in names


def test_analog_statistics_ddof_zero() -> None:
    analog = np.array([[1.0], [2.0], [3.0]], dtype=np.float64)
    digital = np.array([[0], [1], [0]], dtype=np.int8)
    stats = _all_candidate_statistics(analog, digital, ("s1",), ("d1",))

    assert stats["s1_last"] == 3.0
    assert stats["s1_mean"] == 2.0
    assert np.isclose(stats["s1_std"], np.sqrt(2 / 3))
    assert stats["s1_min"] == 1.0
    assert stats["s1_max"] == 3.0
    assert stats["s1_delta"] == 2.0
    assert stats["d1_last"] == 0.0
    assert np.isclose(stats["d1_active_ratio"], 1 / 3)
    assert stats["d1_transition_count"] == 2.0


def test_compute_feature_values_order() -> None:
    samples = [
        TelemetrySample(datetime(2020, 2, 1, 0, 0, 0), (1.0,), (0,)),
        TelemetrySample(datetime(2020, 2, 1, 0, 1, 0), (2.0,), (1,)),
    ]
    vals = compute_feature_values(samples, ["s1_last", "d1_active_ratio"], ("s1",), ("d1",))
    assert vals == (2.0, 0.5)
