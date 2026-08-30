from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pyarrow.parquet as pq


def _canonical_json(data: dict[str, Any]) -> bytes:
    # Convert inf/-inf to string representations for standard JSON encoding
    def _sanitize(obj: Any) -> Any:
        if isinstance(obj, float):
            if np.isneginf(obj):
                return "-inf"
            if np.isposinf(obj):
                return "inf"
            return obj
        if isinstance(obj, list):
            return [_sanitize(x) for x in obj]
        if isinstance(obj, tuple):
            return [_sanitize(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in sorted(obj.items())}
        return obj

    sanitized = _sanitize(data)
    return json.dumps(sanitized, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _compute_drift_hash(data: dict[str, Any]) -> str:
    copy = dict(data)
    copy["self_sha256"] = ""
    return hashlib.sha256(_canonical_json(copy)).hexdigest()


@dataclass(frozen=True)
class DriftReferenceV1:
    model_version: str
    source_dataset_sha256: str
    contract_sha256: str
    active_feature_names: tuple[str, ...]
    num_train_samples: int
    bin_edges: dict[str, list[float]]
    reference_proportions: dict[str, list[float]]
    self_sha256: str
    schema_version: Literal["drift-reference-v1"] = "drift-reference-v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def population_stability_index(
    actual_samples: np.ndarray | list[float],
    bin_edges: list[float],
    reference_proportions: list[float],
    eps: float = 1e-6,
) -> float:
    arr = np.asarray(actual_samples, dtype=float)
    if len(arr) == 0:
        return 0.0

    edges = np.asarray(bin_edges, dtype=float)
    # Ensure -inf and inf at boundaries
    counts, _ = np.histogram(arr, bins=edges)
    total = np.sum(counts)
    if total == 0:
        return 0.0

    actual_props = np.clip(counts / total, eps, 1.0)
    ref_props = np.clip(np.asarray(reference_proportions, dtype=float), eps, 1.0)

    # Re-normalize after clipping
    actual_props = actual_props / np.sum(actual_props)
    ref_props = ref_props / np.sum(ref_props)

    psi_values = (actual_props - ref_props) * np.log(actual_props / ref_props)
    return float(np.sum(psi_values))


def max_population_stability_index(
    current_feature_matrix: dict[str, list[float]] | Any,
    ref: DriftReferenceV1,
) -> float:
    psi_list: list[float] = []
    for feat in ref.active_feature_names:
        if feat in current_feature_matrix:
            values = current_feature_matrix[feat]
            edges = ref.bin_edges[feat]
            props = ref.reference_proportions[feat]
            psi = population_stability_index(values, edges, props)
            psi_list.append(psi)
    if not psi_list:
        raise ValueError("drift reference and current features have no feature overlap")
    return max(psi_list)


def build_reference(features_parquet_path: Path, manifest: dict[str, Any]) -> DriftReferenceV1:
    resolved_path = features_parquet_path.resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError(f"Features file not found at {resolved_path}")

    # ZERO HOLDOUT LEAKAGE: Load only train split
    tbl = pq.read_table(
        resolved_path,
        filters=[("split", "==", "train")],
    )

    feature_names = tuple(
        manifest.get("feature_names") or manifest.get("active_feature_names") or ()
    )
    num_samples = tbl.num_rows
    if num_samples == 0:
        raise ValueError("No training samples found in features parquet for split='train'")

    bin_edges: dict[str, list[float]] = {}
    reference_proportions: dict[str, list[float]] = {}

    for feat in feature_names:
        col = tbl.column(feat).to_numpy()
        # Compute 9 internal quantiles for 10 bins
        quantiles = np.quantile(col, np.linspace(0.1, 0.9, 9))
        edges = [-np.inf, *quantiles.tolist(), np.inf]
        bin_edges[feat] = edges

        # Compute empirical reference proportions with 10 bins
        counts, _ = np.histogram(col, bins=edges)
        props = (counts / np.sum(counts)).tolist()
        reference_proportions[feat] = props

    data = {
        "schema_version": "drift-reference-v1",
        "model_version": manifest["model_version"],
        "source_dataset_sha256": manifest["source_dataset_sha256"],
        "contract_sha256": manifest["contract_sha256"],
        "active_feature_names": feature_names,
        "num_train_samples": int(num_samples),
        "bin_edges": bin_edges,
        "reference_proportions": reference_proportions,
        "self_sha256": "",
    }
    self_hash = _compute_drift_hash(data)
    data["self_sha256"] = self_hash

    return DriftReferenceV1(
        model_version=data["model_version"],
        source_dataset_sha256=data["source_dataset_sha256"],
        contract_sha256=data["contract_sha256"],
        active_feature_names=data["active_feature_names"],
        num_train_samples=data["num_train_samples"],
        bin_edges=data["bin_edges"],
        reference_proportions=data["reference_proportions"],
        self_sha256=data["self_sha256"],
    )


def save_reference(ref: DriftReferenceV1, target_path: Path) -> Path:
    target = target_path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(f".tmp.{os.getpid()}")

    payload = _canonical_json(ref.to_dict())
    tmp_path.write_bytes(payload)
    tmp_path.replace(target)
    return target


def load_reference(path: Path, expected_manifest: dict[str, Any] | None = None) -> DriftReferenceV1:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Drift reference file not found at {resolved}")

    raw = json.loads(resolved.read_text(encoding="utf-8"))

    # Convert string "-inf" / "inf" back to float
    def _desanitize(obj: Any) -> Any:
        if obj == "-inf":
            return -np.inf
        if obj == "inf":
            return np.inf
        if isinstance(obj, list):
            return [_desanitize(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _desanitize(v) for k, v in obj.items()}
        return obj

    data = _desanitize(raw)

    self_hash = data.get("self_sha256", "")
    computed_hash = _compute_drift_hash(data)
    if self_hash != computed_hash:
        raise ValueError(
            f"Drift reference at {resolved} is tampered or corrupted: expected SHA {self_hash}, computed {computed_hash}"
        )

    if expected_manifest is not None:
        if data["model_version"] != expected_manifest["model_version"]:
            raise ValueError(
                f"Model version mismatch in drift reference: expected {expected_manifest['model_version']}, got {data['model_version']}"
            )
        if data["source_dataset_sha256"] != expected_manifest["source_dataset_sha256"]:
            raise ValueError(
                f"Dataset SHA mismatch in drift reference: expected {expected_manifest['source_dataset_sha256']}, got {data['source_dataset_sha256']}"
            )
        if data["contract_sha256"] != expected_manifest["contract_sha256"]:
            raise ValueError(
                f"Contract SHA mismatch in drift reference: expected {expected_manifest['contract_sha256']}, got {data['contract_sha256']}"
            )
        expected_features = tuple(
            expected_manifest.get("feature_names")
            or expected_manifest.get("active_feature_names")
            or ()
        )
        if tuple(data["active_feature_names"]) != expected_features:
            raise ValueError(
                "feature order mismatch in drift reference: "
                f"expected {expected_features}, got {tuple(data['active_feature_names'])}"
            )

    return DriftReferenceV1(
        model_version=data["model_version"],
        source_dataset_sha256=data["source_dataset_sha256"],
        contract_sha256=data["contract_sha256"],
        active_feature_names=tuple(data["active_feature_names"]),
        num_train_samples=int(data["num_train_samples"]),
        bin_edges=data["bin_edges"],
        reference_proportions=data["reference_proportions"],
        self_sha256=data["self_sha256"],
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build or verify train-only drift reference.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_p = subparsers.add_parser("build-reference", help="Build train-only drift reference")
    build_p.add_argument(
        "--manifest", type=Path, required=True, help="Path to champion manifest.json"
    )
    build_p.add_argument("--features", type=Path, required=True, help="Path to features.parquet")
    build_p.add_argument(
        "--output", type=Path, required=True, help="Path to output drift-reference.json"
    )

    args = parser.parse_args()

    if args.command == "build-reference":
        manifest_data = json.loads(args.manifest.resolve().read_text(encoding="utf-8"))
        ref = build_reference(args.features.resolve(), manifest_data)
        out_path = save_reference(ref, args.output.resolve())
        print(f"Successfully built drift reference at {out_path}")
        print(f"Self SHA-256: {ref.self_sha256}")


if __name__ == "__main__":
    main()
