"""Hard-gated packaging of the verified Phase 1B champion detector."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from industrial_reliability.phase1b_data import sha256_file

DETECTOR_FILENAME = "detector.joblib"
BASELINE_FILENAME = "evidence-baseline.npz"
GOLDEN_CASES_FILENAME = "golden-cases.json"
MANIFEST_FILENAME = "manifest.json"
HEX_64_PATTERN = r"^[0-9a-f]{64}$"


class ChampionPackageError(ValueError):
    """Raised when Phase 1B champion artifacts are infeasible, missing, or corrupted."""


class ThresholdProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    split: Literal["calibration"] = "calibration"
    quantile: float = 0.995
    method: Literal["higher"] = "higher"


class ChampionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["champion-package-v1"] = "champion-package-v1"
    source_champion_schema: Literal["phase1b-champion-v1"] = "phase1b-champion-v1"
    source_run_id: str
    model_id: Literal["statistical", "isolation_forest", "autoencoder"]
    model_version: str
    contract_sha256: str = Field(pattern=HEX_64_PATTERN)
    source_dataset_sha256: str = Field(pattern=HEX_64_PATTERN)
    feature_names: tuple[str, ...] = Field(min_length=1)
    threshold: float
    threshold_provenance: ThresholdProvenance
    golden_case_count: Literal[3] = 3
    artifact_sha256: Mapping[str, str]

    @field_validator("artifact_sha256")
    @classmethod
    def validate_artifact_hashes(cls, v: Mapping[str, str]) -> Mapping[str, str]:
        allowed_keys = {DETECTOR_FILENAME, BASELINE_FILENAME, GOLDEN_CASES_FILENAME}
        if set(v.keys()) != allowed_keys:
            raise ValueError(f"artifact_sha256 must contain exact keys: {allowed_keys}")
        for key, hash_val in v.items():
            if not isinstance(hash_val, str) or len(hash_val) != 64:
                raise ValueError(f"Invalid sha256 for {key}: {hash_val}")
        return MappingProxyType(dict(v))

    @field_serializer("artifact_sha256")
    def serialize_artifact_hashes(self, v: Mapping[str, str]) -> dict[str, str]:
        return dict(v)


@dataclass(frozen=True, slots=True)
class GoldenCase:
    case_id: str
    source_timestamp: datetime
    window_start: datetime
    window_end: datetime
    feature_names: tuple[str, ...]
    feature_values: tuple[float, ...]
    expected_score: float
    expected_threshold: float
    expected_is_anomaly: bool
    expected_evidence: tuple[tuple[str, float, float], ...]


@dataclass(frozen=True, slots=True)
class ChampionPackageResult:
    output_dir: Path
    manifest: ChampionManifest
    manifest_sha256: str


def _resolve_path(base_dir: Path, filename: str) -> Path:
    base = base_dir.resolve()
    target = (base / filename).resolve()
    if target.parent != base:
        raise ValueError(f"Path traversal detected: {filename}")
    return target


def _verify_phase1b_artifacts(
    run_dir: Path, features_path: Path, champion_dict: dict[str, Any]
) -> None:
    resolved_run = run_dir.resolve()
    resolved_feat = features_path.resolve()

    if not resolved_feat.is_file():
        raise ChampionPackageError(f"Features file not found: {resolved_feat}")
    if sha256_file(resolved_feat) != champion_dict.get("feature_output_sha256"):
        raise ChampionPackageError("features.parquet SHA-256 does not match champion manifest")

    artifact_hashes = champion_dict.get("artifact_sha256", {})
    expected_scores = artifact_hashes.get("scores_parquet")
    expected_model = artifact_hashes.get("model_binary")
    expected_baseline = artifact_hashes.get("evidence_baseline")

    scores_file = (resolved_run / "scores.parquet").resolve()
    baseline_file = (resolved_run / BASELINE_FILENAME).resolve()
    model_id = champion_dict.get("model_id")
    model_file = (resolved_run / "models" / f"{model_id}.joblib").resolve()

    if not scores_file.is_file() or sha256_file(scores_file) != expected_scores:
        raise ChampionPackageError("scores.parquet missing or SHA-256 mismatch")
    if not baseline_file.is_file() or sha256_file(baseline_file) != expected_baseline:
        raise ChampionPackageError(f"{BASELINE_FILENAME} missing or SHA-256 mismatch")
    if not model_file.is_file() or sha256_file(model_file) != expected_model:
        raise ChampionPackageError(f"Model binary {model_file.name} missing or SHA-256 mismatch")


def _verify_git_ancestor(git_sha: str | None) -> None:
    if not git_sha:
        return
    res = subprocess.run(
        ["git", "merge-base", "--is-ancestor", git_sha, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise ChampionPackageError(f"Champion git commit {git_sha} is not an ancestor of HEAD")


def _select_golden_cases(
    scores_parquet: Path,
    features_parquet: Path,
    champion_dict: dict[str, Any],
    baseline_npz: Path,
) -> list[GoldenCase]:
    features_df = pq.read_table(features_parquet.resolve()).to_pandas()
    scores_df = pq.read_table(scores_parquet.resolve()).to_pandas()
    baseline = np.load(baseline_npz.resolve(), allow_pickle=False)
    median = baseline["median"]
    mad = baseline["mad"]

    active_features = tuple(champion_dict["active_feature_names"])
    threshold = float(champion_dict["threshold"])
    model_id = champion_dict["model_id"]

    model_scores = scores_df[scores_df["model_id"] == model_id].copy()
    if model_scores.empty:
        raise ChampionPackageError(f"No scores for champion model {model_id}")

    # Merge features with scores on window_start / window_end with explicit how and validate
    merged = pd.merge(
        features_df,
        model_scores,
        on=["split", "window_start", "window_end"],
        how="inner",
        validate="one_to_one",
    )
    calib_merged = merged[merged["split"] == "calibration"].sort_values("window_start")
    if calib_merged.empty:
        # Fallback to all rows if calibration was not evaluated in scores table
        calib_merged = merged.sort_values("window_start")

    # 1. Earliest valid row
    row_earliest = calib_merged.iloc[0]

    # 2. Highest normal score row (score < threshold)
    normal_rows = calib_merged[calib_merged["score"] < threshold]
    if not normal_rows.empty:
        row_highest_normal = normal_rows.sort_values("score", ascending=False).iloc[0]
    else:
        row_highest_normal = calib_merged.iloc[len(calib_merged) // 2]

    # 3. Earliest anomalous score row (score >= threshold) or max score row
    anom_rows = calib_merged[calib_merged["score"] >= threshold]
    if not anom_rows.empty:
        row_anom = anom_rows.iloc[0]
    else:
        row_anom = calib_merged.sort_values("score", ascending=False).iloc[0]

    chosen_rows = [
        ("golden-calib-earliest", row_earliest),
        ("golden-calib-highest-normal", row_highest_normal),
        ("golden-calib-anomalous", row_anom),
    ]

    golden_cases: list[GoldenCase] = []
    for case_id, row in chosen_rows:
        feat_vals = tuple(float(row[col]) for col in active_features)
        vals_array = np.array(feat_vals, dtype=np.float64)
        deviations = np.divide(
            np.abs(vals_array - median),
            1.4826 * mad,
            out=np.zeros_like(vals_array),
            where=~np.isclose(mad, 0.0),
        )
        evidence = tuple(
            (name, float(val), float(dev))
            for name, val, dev in zip(active_features, feat_vals, deviations, strict=True)
        )
        w_start = (
            row["window_start"].to_pydatetime()
            if hasattr(row["window_start"], "to_pydatetime")
            else row["window_start"]
        )
        w_end = (
            row["window_end"].to_pydatetime()
            if hasattr(row["window_end"], "to_pydatetime")
            else row["window_end"]
        )
        golden_cases.append(
            GoldenCase(
                case_id=case_id,
                source_timestamp=w_end,
                window_start=w_start,
                window_end=w_end,
                feature_names=active_features,
                feature_values=feat_vals,
                expected_score=float(row["score"]),
                expected_threshold=threshold,
                expected_is_anomaly=bool(row["score"] >= threshold),
                expected_evidence=evidence,
            )
        )

    return golden_cases


def _serialize_golden_cases(cases: list[GoldenCase]) -> dict[str, Any]:
    return {
        "schema_version": "champion-golden-cases-v1",
        "cases": [
            {
                "case_id": c.case_id,
                "source_timestamp": c.source_timestamp.isoformat(),
                "window_start": c.window_start.isoformat(),
                "window_end": c.window_end.isoformat(),
                "feature_names": list(c.feature_names),
                "feature_values": list(c.feature_values),
                "expected_score": c.expected_score,
                "expected_threshold": c.expected_threshold,
                "expected_is_anomaly": c.expected_is_anomaly,
                "expected_evidence": [
                    {"feature_name": name, "feature_value": val, "robust_deviation": dev}
                    for name, val, dev in c.expected_evidence
                ],
            }
            for c in cases
        ],
    }


def build_champion_package(
    run_dir: Path,
    features_path: Path,
    output_dir: Path,
) -> ChampionPackageResult:
    resolved_run = run_dir.resolve()
    resolved_out = output_dir.resolve()

    if resolved_out.exists():
        raise FileExistsError(f"destination already exists: {resolved_out}")

    manifest_file = (resolved_run / "champion-manifest.json").resolve()
    if not manifest_file.is_file():
        raise ChampionPackageError(
            "Phase 2 requires a FEASIBLE champion (champion-manifest.json not found)"
        )

    champion = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (
        champion.get("schema_version") != "phase1b-champion-v1"
        or champion.get("verdict") != "FEASIBLE"
    ):
        raise ChampionPackageError("Phase 2 requires a FEASIBLE champion")

    _verify_phase1b_artifacts(resolved_run, features_path, champion)
    _verify_git_ancestor(champion.get("git_sha"))

    model_id = champion["model_id"]
    model_src = (resolved_run / "models" / f"{model_id}.joblib").resolve()
    baseline_src = (resolved_run / BASELINE_FILENAME).resolve()
    scores_src = (resolved_run / "scores.parquet").resolve()

    golden = _select_golden_cases(scores_src, features_path, champion, baseline_src)

    temp_output = (
        resolved_out.parent / f"{resolved_out.name}_temp_{int(datetime.now().timestamp())}"
    )
    temp_output.mkdir(parents=True, exist_ok=True)

    try:
        dest_model = _resolve_path(temp_output, DETECTOR_FILENAME)
        dest_baseline = _resolve_path(temp_output, BASELINE_FILENAME)
        dest_golden = _resolve_path(temp_output, GOLDEN_CASES_FILENAME)
        dest_manifest = _resolve_path(temp_output, MANIFEST_FILENAME)

        shutil.copy2(model_src, dest_model)
        shutil.copy2(baseline_src, dest_baseline)

        golden_payload = _serialize_golden_cases(golden)
        dest_golden.write_text(json.dumps(golden_payload, indent=2), encoding="utf-8")

        artifact_hashes = {
            DETECTOR_FILENAME: sha256_file(dest_model),
            BASELINE_FILENAME: sha256_file(dest_baseline),
            GOLDEN_CASES_FILENAME: sha256_file(dest_golden),
        }

        package_manifest = ChampionManifest(
            schema_version="champion-package-v1",
            source_champion_schema="phase1b-champion-v1",
            source_run_id=champion["run_id"],
            model_id=champion["model_id"],
            model_version=champion["model_version"],
            contract_sha256=champion["contract_sha256"],
            source_dataset_sha256=champion["source_dataset_sha256"],
            feature_names=tuple(champion["active_feature_names"]),
            threshold=float(champion["threshold"]),
            threshold_provenance=ThresholdProvenance(
                split="calibration",
                quantile=0.995,
                method="higher",
            ),
            golden_case_count=3,
            artifact_sha256=artifact_hashes,
        )

        manifest_json = package_manifest.model_dump_json(indent=2)
        dest_manifest.write_text(manifest_json, encoding="utf-8")
        manifest_sha256 = sha256_file(dest_manifest)

        temp_output.rename(resolved_out)
    except Exception:
        shutil.rmtree(temp_output, ignore_errors=True)
        raise

    return ChampionPackageResult(
        output_dir=resolved_out,
        manifest=package_manifest,
        manifest_sha256=manifest_sha256,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Package Phase 1B champion model.")
    parser.add_argument(
        "--run-dir", type=Path, required=True, help="Directory containing Phase 1B run artifacts"
    )
    parser.add_argument("--features", type=Path, required=True, help="Path to features.parquet")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Destination directory for champion package"
    )
    args = parser.parse_args()

    result = build_champion_package(args.run_dir, args.features, args.output_dir)
    print(f"Successfully built champion package at {result.output_dir}")
    print(f"Trust anchor manifest SHA-256: {result.manifest_sha256}")


if __name__ == "__main__":
    main()
