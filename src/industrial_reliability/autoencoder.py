"""Deterministic CPU dense autoencoder for Phase 1 anomaly scoring."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Self, cast

import numpy as np
import torch
from numpy.typing import NDArray
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from industrial_reliability.contracts import PHASE1
from industrial_reliability.models import _immutable, _matrix


def _seed_everything() -> torch.Generator:
    random.seed(PHASE1.random_seed)
    np.random.seed(PHASE1.random_seed)
    torch.manual_seed(PHASE1.random_seed)
    torch.use_deterministic_algorithms(PHASE1.autoencoder_deterministic)
    return torch.Generator(device=PHASE1.autoencoder_device).manual_seed(PHASE1.random_seed)


def _network(feature_count: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(feature_count, PHASE1.autoencoder_hidden_width),
        nn.ReLU(),
        nn.Linear(PHASE1.autoencoder_hidden_width, PHASE1.autoencoder_bottleneck_width),
        nn.ReLU(),
        nn.Linear(PHASE1.autoencoder_bottleneck_width, PHASE1.autoencoder_hidden_width),
        nn.ReLU(),
        nn.Linear(PHASE1.autoencoder_hidden_width, feature_count),
    )


@dataclass(frozen=True, slots=True)
class DenseAutoencoderDetector:
    """Fit the frozen Phase 1 dense autoencoder and return reconstruction errors."""

    epochs: int = PHASE1.autoencoder_epochs
    _scaler: StandardScaler | None = field(default=None, init=False, repr=False)
    _model: nn.Sequential | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.epochs, bool) or not isinstance(self.epochs, int) or self.epochs < 1:
            raise ValueError("epochs must be a positive integer")

    def fit(self, train: NDArray[np.float64]) -> Self:
        values = _matrix(train, "train")
        scaler = StandardScaler().fit(values)
        scaled = np.asarray(scaler.transform(values), dtype=np.float32)
        tensor = torch.from_numpy(scaled).to(PHASE1.autoencoder_device)
        generator = _seed_everything()
        loader = DataLoader(
            TensorDataset(tensor),
            batch_size=PHASE1.autoencoder_batch_size,
            shuffle=True,
            num_workers=PHASE1.autoencoder_num_workers,
            generator=generator,
        )
        model = _network(values.shape[1]).to(PHASE1.autoencoder_device)
        loss_function = nn.MSELoss()
        optimizer = torch.optim.Adam(
            model.parameters(),
            lr=PHASE1.autoencoder_learning_rate,
            weight_decay=0.0,
        )
        model.train()
        for _ in range(self.epochs):
            for (batch,) in loader:
                optimizer.zero_grad(set_to_none=True)
                loss = loss_function(model(batch), batch)
                loss.backward()
                optimizer.step()
        model.eval()
        fitted = cast(Self, DenseAutoencoderDetector(epochs=self.epochs))
        object.__setattr__(fitted, "_scaler", scaler)
        object.__setattr__(fitted, "_model", model)
        return fitted

    @property
    def scaler_mean(self) -> NDArray[np.float64]:
        scaler, _ = self._fitted()
        return cast(NDArray[np.float64], _immutable(scaler.mean_.copy()))

    @property
    def scaler_scale(self) -> NDArray[np.float64]:
        scaler, _ = self._fitted()
        return cast(NDArray[np.float64], _immutable(scaler.scale_.copy()))

    def score(self, values: NDArray[np.float64]) -> NDArray[np.float64]:
        contributions = self.contributions(values)
        return cast(NDArray[np.float64], contributions.mean(axis=1, dtype=np.float64))

    def contributions(self, values: NDArray[np.float64]) -> NDArray[np.float64]:
        scaler, model = self._fitted()
        matrix = _matrix(values, "values")
        if matrix.shape[1] != scaler.mean_.size:
            raise ValueError("values must have the same feature count as train")
        scaled = np.asarray(scaler.transform(matrix), dtype=np.float32)
        tensor = torch.from_numpy(scaled).to(PHASE1.autoencoder_device)
        with torch.inference_mode():
            reconstruction = model(tensor)
            errors = torch.square(reconstruction - tensor).cpu().numpy()
        return np.asarray(errors, dtype=np.float64)

    def _fitted(self) -> tuple[StandardScaler, nn.Sequential]:
        if self._scaler is None or self._model is None:
            raise RuntimeError("detector must be fit before scoring")
        return self._scaler, self._model
