"""Train-only Phase 1 anomaly scorers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self, cast

import numpy as np
from numpy.typing import NDArray
from sklearn.ensemble import IsolationForest

from industrial_reliability.contracts import PHASE1


def _matrix(values: NDArray[np.float64], name: str) -> NDArray[np.float64]:
    try:
        matrix = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite two-dimensional numeric array") from error
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError(f"{name} must be a nonempty two-dimensional array")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} must contain only finite values")
    return matrix


def _immutable(values: NDArray[np.generic]) -> NDArray[np.generic]:
    values.setflags(write=False)
    return values


@dataclass(frozen=True, slots=True)
class RobustStatisticalDetector:
    """Score rows by their maximum absolute train-derived robust z-score."""

    _medians: NDArray[np.float64] | None = None
    _mads: NDArray[np.float64] | None = None
    _feature_mask: NDArray[np.bool_] | None = None

    def fit(self, train: NDArray[np.float64]) -> Self:
        values = _matrix(train, "train")
        medians = cast(NDArray[np.float64], np.median(values, axis=0))
        mads = cast(NDArray[np.float64], np.median(np.abs(values - medians), axis=0))
        feature_mask = mads != 0.0
        if not feature_mask.any():
            raise ValueError("all training features have zero MAD")
        return cast(
            Self,
            RobustStatisticalDetector(
                cast(NDArray[np.float64], _immutable(medians)),
                cast(NDArray[np.float64], _immutable(mads)),
                cast(NDArray[np.bool_], _immutable(feature_mask)),
            ),
        )

    def score(self, values: NDArray[np.float64]) -> NDArray[np.float64]:
        if self._medians is None or self._mads is None or self._feature_mask is None:
            raise RuntimeError("detector must be fit before score")
        matrix = _matrix(values, "values")
        if matrix.shape[1] != self._medians.size:
            raise ValueError("values must have the same feature count as train")
        z_scores = np.abs(
            (matrix[:, self._feature_mask] - self._medians[self._feature_mask])
            / (PHASE1.robust_mad_scale * self._mads[self._feature_mask])
        )
        return cast(NDArray[np.float64], np.max(z_scores, axis=1))


@dataclass(frozen=True, slots=True)
class IsolationForestDetector:
    """Score rows with the frozen deterministic Phase 1 Isolation Forest."""

    _model: IsolationForest | None = None
    _feature_count: int | None = None

    def fit(self, train: NDArray[np.float64]) -> Self:
        values = _matrix(train, "train")
        model = IsolationForest(
            n_estimators=PHASE1.isolation_forest_estimators,
            max_samples=PHASE1.isolation_forest_max_samples,
            contamination=PHASE1.isolation_forest_contamination,
            random_state=PHASE1.random_seed,
            n_jobs=PHASE1.isolation_forest_n_jobs,
        ).fit(values)
        return cast(Self, IsolationForestDetector(model, values.shape[1]))

    def score(self, values: NDArray[np.float64]) -> NDArray[np.float64]:
        if self._model is None or self._feature_count is None:
            raise RuntimeError("detector must be fit before score")
        matrix = _matrix(values, "values")
        if matrix.shape[1] != self._feature_count:
            raise ValueError("values must have the same feature count as train")
        return cast(NDArray[np.float64], -self._model.score_samples(matrix))
