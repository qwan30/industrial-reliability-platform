from __future__ import annotations

import numpy as np
import pytest

from industrial_reliability.autoencoder import DenseAutoencoderDetector
from tests.helpers import seeded_training_matrix


def test_autoencoder_scores_and_contributions_have_expected_shapes() -> None:
    train = seeded_training_matrix(rows=512, columns=6)
    detector = DenseAutoencoderDetector(epochs=2).fit(train)

    scores = detector.score(train)
    contributions = detector.contributions(train)

    assert scores.shape == (512,)
    assert contributions.shape == train.shape
    assert scores.dtype == np.float64
    assert contributions.dtype == np.float64
    np.testing.assert_allclose(scores, contributions.mean(axis=1), rtol=0, atol=1e-12)


def test_autoencoder_does_not_mutate_caller_data() -> None:
    train = seeded_training_matrix(rows=64, columns=4)
    values = seeded_training_matrix(rows=8, columns=4) + 1.0
    original_train = train.copy()
    original_values = values.copy()

    detector = DenseAutoencoderDetector(epochs=1).fit(train)
    detector.score(values)
    detector.contributions(values)

    np.testing.assert_array_equal(train, original_train)
    np.testing.assert_array_equal(values, original_values)


def test_autoencoder_is_deterministic() -> None:
    train = seeded_training_matrix(rows=128, columns=4)

    first = DenseAutoencoderDetector(epochs=2).fit(train)
    second = DenseAutoencoderDetector(epochs=2).fit(train)

    np.testing.assert_allclose(first.score(train), second.score(train), rtol=0, atol=1e-7)
    np.testing.assert_allclose(
        first.contributions(train),
        second.contributions(train),
        rtol=0,
        atol=1e-7,
    )


def test_autoencoder_seeded_shuffle_is_deterministic_across_multiple_batches() -> None:
    train = seeded_training_matrix(rows=257, columns=4)

    first = DenseAutoencoderDetector(epochs=2).fit(train).score(train)
    second = DenseAutoencoderDetector(epochs=2).fit(train).score(train)

    np.testing.assert_allclose(first, second, rtol=0, atol=1e-7)


def test_autoencoder_scaler_is_train_only_and_provenance_is_read_only() -> None:
    train = seeded_training_matrix(rows=128, columns=4)
    detector = DenseAutoencoderDetector(epochs=1).fit(train)
    mean_before = detector.scaler_mean
    scale_before = detector.scaler_scale

    np.testing.assert_allclose(mean_before, train.mean(axis=0), rtol=0, atol=1e-12)
    np.testing.assert_allclose(scale_before, train.std(axis=0), rtol=0, atol=1e-12)
    assert not mean_before.flags.writeable
    assert not scale_before.flags.writeable
    assert not np.shares_memory(mean_before, detector.scaler_mean)
    assert not np.shares_memory(scale_before, detector.scaler_scale)

    detector.score(train + 10_000.0)

    np.testing.assert_array_equal(detector.scaler_mean, mean_before)
    np.testing.assert_array_equal(detector.scaler_scale, scale_before)


def test_autoencoder_constructor_rejects_fitted_state_injection() -> None:
    with pytest.raises(TypeError):
        DenseAutoencoderDetector(
            epochs=1,
            _scaler=object(),  # type: ignore[arg-type]
            _model=object(),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("method", ["score", "contributions"])
def test_autoencoder_rejects_scoring_before_fit(method: str) -> None:
    detector = DenseAutoencoderDetector(epochs=1)
    func = getattr(detector, method)
    data = np.array([[0.0]])

    with pytest.raises(RuntimeError, match="fit"):
        func(data)


@pytest.mark.parametrize("attribute", ["scaler_mean", "scaler_scale"])
def test_autoencoder_rejects_scaler_provenance_before_fit(attribute: str) -> None:
    detector = DenseAutoencoderDetector(epochs=1)
    with pytest.raises(RuntimeError, match="fit"):
        getattr(detector, attribute)


@pytest.mark.parametrize(
    "values",
    [
        np.array([0.0, 1.0]),
        np.array([[0.0], [np.nan]]),
        np.empty((2, 0)),
        np.empty((0, 2)),
    ],
)
def test_autoencoder_rejects_invalid_training_matrices(values: np.ndarray) -> None:
    detector = DenseAutoencoderDetector(epochs=1)
    with pytest.raises(ValueError):
        detector.fit(values)


@pytest.mark.parametrize("epochs", [0, -1, 1.5, True])
def test_autoencoder_rejects_invalid_epoch_overrides(epochs: object) -> None:
    with pytest.raises(ValueError, match="epochs"):
        DenseAutoencoderDetector(epochs=epochs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "values",
    [np.array([0.0, 1.0]), np.array([[np.inf, 1.0]]), np.array([[1.0]])],
)
def test_autoencoder_rejects_invalid_or_wrong_width_scoring_matrices(
    values: np.ndarray,
) -> None:
    detector = DenseAutoencoderDetector(epochs=1).fit(
        np.array([[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]])
    )

    with pytest.raises(ValueError):
        detector.contributions(values)
