from __future__ import annotations

import numpy as np
import pytest
from sklearn.ensemble import IsolationForest

from industrial_reliability.contracts import PHASE1
from industrial_reliability.models import IsolationForestDetector, RobustStatisticalDetector


def seeded_training_matrix() -> np.ndarray:
    return np.random.default_rng(7).normal(size=(40, 3))


def test_robust_detector_scores_outlier_higher() -> None:
    train = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    model = RobustStatisticalDetector().fit(train)

    assert model.score(np.array([[100.0, 100.0]]))[0] > model.score(train).max()


def test_robust_detector_excludes_zero_mad_features() -> None:
    train = np.array([[0.0, 2.0], [1.0, 2.0], [2.0, 2.0]])
    model = RobustStatisticalDetector().fit(train)

    np.testing.assert_allclose(model.score(np.array([[1.0, 999.0]])), [0.0])


def test_robust_detector_rejects_training_with_only_zero_mad_features() -> None:
    with pytest.raises(ValueError, match="all training features have zero MAD"):
        RobustStatisticalDetector().fit(np.array([[2.0, 2.0], [2.0, 2.0]]))


def test_isolation_forest_is_deterministic() -> None:
    train = seeded_training_matrix()

    first = IsolationForestDetector().fit(train).score(train)
    second = IsolationForestDetector().fit(train).score(train)

    np.testing.assert_allclose(first, second)


def test_isolation_forest_returns_negative_score_samples() -> None:
    train = seeded_training_matrix()
    values = train[:3]
    expected = (
        -IsolationForest(
            n_estimators=PHASE1.isolation_forest_estimators,
            max_samples=PHASE1.isolation_forest_max_samples,
            contamination=PHASE1.isolation_forest_contamination,
            random_state=PHASE1.random_seed,
            n_jobs=PHASE1.isolation_forest_n_jobs,
        )
        .fit(train)
        .score_samples(values)
    )

    actual = IsolationForestDetector().fit(train).score(values)

    np.testing.assert_allclose(actual, expected)


@pytest.mark.parametrize("detector", [RobustStatisticalDetector, IsolationForestDetector])
def test_detectors_reject_scoring_before_fit(detector: type[object]) -> None:
    with pytest.raises(RuntimeError, match="fit"):
        detector().score(np.array([[0.0]]))  # type: ignore[attr-defined]


@pytest.mark.parametrize("detector", [RobustStatisticalDetector, IsolationForestDetector])
@pytest.mark.parametrize(
    "values",
    [np.array([0.0, 1.0]), np.array([[0.0], [np.nan]]), np.empty((2, 0))],
)
def test_detectors_reject_invalid_training_matrices(
    detector: type[object], values: np.ndarray
) -> None:
    with pytest.raises(ValueError):
        detector().fit(values)  # type: ignore[attr-defined]


@pytest.mark.parametrize("detector", [RobustStatisticalDetector, IsolationForestDetector])
def test_detectors_reject_invalid_or_wrong_width_scoring_matrices(detector: type[object]) -> None:
    model = detector().fit(np.array([[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]]))  # type: ignore[attr-defined]

    for values in (np.array([0.0, 1.0]), np.array([[np.inf, 1.0]]), np.array([[1.0]])):
        with pytest.raises(ValueError):
            model.score(values)


@pytest.mark.parametrize("detector", [RobustStatisticalDetector, IsolationForestDetector])
def test_detectors_leave_caller_arrays_unchanged(detector: type[object]) -> None:
    train = seeded_training_matrix()
    values = seeded_training_matrix()[:2]
    train_before = train.copy()
    values_before = values.copy()

    detector().fit(train).score(values)  # type: ignore[attr-defined]

    np.testing.assert_array_equal(train, train_before)
    np.testing.assert_array_equal(values, values_before)
