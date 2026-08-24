"""Integrity-checked runtime champion model loader and stateless scorer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from industrial_reliability.package_champion import ChampionManifest
from industrial_reliability.phase1b_data import sha256_file
from industrial_reliability.runtime_messages import (
    EvidenceValueV1,
    FeatureVectorV1,
)


class ChampionIntegrityError(ValueError):
    """Raised when the champion package, manifest, or child artifact fails verification."""


class ScoringContractError(ValueError):
    """Raised when an incoming feature vector violates the model's contract or feature order."""


@dataclass(frozen=True, slots=True)
class ScoredVector:
    score: float
    threshold: float
    is_anomaly: bool
    evidence_vector: tuple[EvidenceValueV1, ...]


class ChampionScorer:
    def __init__(
        self,
        *,
        manifest: ChampionManifest,
        detector: Any,
        median: np.ndarray,
        mad: np.ndarray,
    ) -> None:
        self.manifest = manifest
        self.detector = detector
        self.median = median
        self.mad = mad
        self.model_version = manifest.model_version
        self.feature_names = manifest.feature_names
        self.threshold = manifest.threshold
        self.contract_sha256 = manifest.contract_sha256
        self.source_dataset_sha256 = manifest.source_dataset_sha256

    def _validate_identity(self, feature: FeatureVectorV1) -> None:
        if feature.contract_sha256 != self.contract_sha256:
            raise ScoringContractError(
                f"Contract mismatch: expected {self.contract_sha256}, got {feature.contract_sha256}"
            )
        if feature.source_dataset_sha256 != self.source_dataset_sha256:
            raise ScoringContractError(
                f"Dataset mismatch: expected {self.source_dataset_sha256}, got {feature.source_dataset_sha256}"
            )
        if feature.feature_names != self.feature_names:
            raise ScoringContractError(
                f"Feature order mismatch: expected {self.feature_names}, got {feature.feature_names}"
            )

    def score(self, feature: FeatureVectorV1) -> ScoredVector:
        self._validate_identity(feature)
        matrix = np.asarray([feature.feature_values], dtype=np.float64)
        raw_score = float(self.detector.score(matrix)[0])
        deviations = np.divide(
            np.abs(matrix[0] - self.median),
            1.4826 * self.mad,
            out=np.zeros_like(matrix[0]),
            where=~np.isclose(self.mad, 0.0),
        )
        evidence = tuple(
            EvidenceValueV1(
                feature_name=name,
                feature_value=float(value),
                robust_deviation=float(delta),
            )
            for name, value, delta in zip(self.feature_names, matrix[0], deviations, strict=True)
        )
        is_anomaly = raw_score >= self.threshold
        return ScoredVector(
            score=raw_score,
            threshold=self.threshold,
            is_anomaly=is_anomaly,
            evidence_vector=evidence,
        )


def _resolve_safe_child(package_dir: Path, filename: str) -> Path:
    base = package_dir.resolve()
    target = (base / filename).resolve()
    if target.parent != base:
        raise ChampionIntegrityError(f"Path traversal detected: {filename}")
    return target


def load_champion(package_dir: Path, expected_manifest_sha256: str) -> ChampionScorer:
    resolved_pkg = package_dir.resolve()
    manifest_path = (resolved_pkg / "manifest.json").resolve()
    if not manifest_path.is_file():
        raise ChampionIntegrityError(f"manifest.json missing in {resolved_pkg}")

    actual_manifest_sha = sha256_file(manifest_path)
    if actual_manifest_sha != expected_manifest_sha256:
        raise ChampionIntegrityError(
            f"manifest SHA-256 mismatch: expected {expected_manifest_sha256}, got {actual_manifest_sha}"
        )

    manifest = ChampionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    for name, expected_hash in manifest.artifact_sha256.items():
        child_path = _resolve_safe_child(resolved_pkg, name)
        if not child_path.is_file():
            raise ChampionIntegrityError(f"Artifact {name} missing in package")
        actual_hash = sha256_file(child_path)
        if actual_hash != expected_hash:
            raise ChampionIntegrityError(f"{name} SHA-256 mismatch")

    detector_path = _resolve_safe_child(resolved_pkg, "detector.joblib")
    detector = joblib.load(detector_path)

    baseline_path = _resolve_safe_child(resolved_pkg, "evidence-baseline.npz")
    baseline = np.load(baseline_path, allow_pickle=False)

    baseline_features = tuple(str(x) for x in baseline["feature_names"])
    if baseline_features != manifest.feature_names:
        raise ChampionIntegrityError("evidence-baseline feature_names mismatch with manifest")

    median = baseline["median"]
    mad = baseline["mad"]
    if len(median) != len(manifest.feature_names) or len(mad) != len(manifest.feature_names):
        raise ChampionIntegrityError("evidence-baseline dimensions mismatch with feature count")

    return ChampionScorer(
        manifest=manifest,
        detector=detector,
        median=median,
        mad=mad,
    )
