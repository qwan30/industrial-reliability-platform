"""Packaging of the research-only candidate scoring model."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from industrial_reliability.alert_policy import lock_alert_policy
from industrial_reliability.package_champion import (
    BASELINE_FILENAME,
    DETECTOR_FILENAME,
    GOLDEN_CASES_FILENAME,
    MANIFEST_FILENAME,
    SCORES_PARQUET_FILENAME,
    ChampionManifest,
    ChampionPackageError,
    ChampionPackageResult,
    ThresholdProvenance,
    select_golden_cases,
    serialize_golden_cases,
)
from industrial_reliability.phase1b_data import sha256_file


def _validate_safe_path(path: Path) -> Path:
    return path.resolve()


def build_research_candidate_package(
    *,
    run_dir: Path,
    features_path: Path,
    feature_manifest_path: Path,
    output_dir: Path,
) -> ChampionPackageResult:
    safe_run_dir = _validate_safe_path(run_dir)
    safe_features_path = _validate_safe_path(features_path)
    safe_feature_manifest_path = _validate_safe_path(feature_manifest_path)
    safe_output_dir = _validate_safe_path(output_dir)

    run_manifest_file = safe_run_dir / "run_manifest.json"
    if not run_manifest_file.is_file():
        raise ChampionPackageError(f"Run manifest missing: {run_manifest_file}")
    if not safe_feature_manifest_path.is_file():
        raise ChampionPackageError(f"Feature manifest missing: {safe_feature_manifest_path}")

    run = json.loads(run_manifest_file.read_text(encoding="utf-8"))
    features = json.loads(safe_feature_manifest_path.read_text(encoding="utf-8"))
    if run.get("schema_version") != "phase1b-run-v1":
        raise ChampionPackageError("phase1b-run-v1 manifest required")
    if run.get("verdict") != "NOT FEASIBLE" or run.get("selected_model") is not None:
        raise ChampionPackageError("research package requires the immutable NOT FEASIBLE run")
    if sha256_file(safe_features_path) != run["feature_output_sha256"]:
        raise ChampionPackageError("features.parquet SHA-256 mismatch")
    if features.get("output_sha256") != run["feature_output_sha256"]:
        raise ChampionPackageError("feature manifest does not match the Phase 1B run")

    model_id = "statistical"
    model_path = safe_run_dir / "models" / f"{model_id}.joblib"
    scores_path = safe_run_dir / SCORES_PARQUET_FILENAME
    baseline_path = safe_run_dir / BASELINE_FILENAME
    for path in (model_path, scores_path, baseline_path):
        if not path.is_file():
            raise ChampionPackageError(f"required research artifact missing: {path.name}")

    source = {
        "run_id": run["run_id"],
        "model_id": model_id,
        "threshold": run["models"][model_id]["threshold"],
        "active_feature_names": features["active_feature_names"],
    }
    golden = select_golden_cases(scores_path, safe_features_path, source, baseline_path)
    if safe_output_dir.exists():
        raise FileExistsError(f"destination already exists: {safe_output_dir}")
    temp_output = safe_output_dir.parent / f"{safe_output_dir.name}.tmp.{os.getpid()}"
    temp_output.mkdir(parents=True, exist_ok=False)
    try:
        published_model = temp_output / DETECTOR_FILENAME
        published_baseline = temp_output / BASELINE_FILENAME
        published_golden = temp_output / GOLDEN_CASES_FILENAME
        published_scores = temp_output / SCORES_PARQUET_FILENAME
        shutil.copy2(model_path, published_model)
        shutil.copy2(baseline_path, published_baseline)
        shutil.copy2(scores_path, published_scores)
        published_golden.write_text(
            json.dumps(serialize_golden_cases(golden), indent=2),
            encoding="utf-8",
        )
        manifest = ChampionManifest(
            source_champion_schema="phase1b-run-v1",
            source_run_id=run["run_id"],
            package_role="RESEARCH_CANDIDATE",
            evaluation_verdict="NOT_FEASIBLE",
            operational_status="RESEARCH_ONLY",
            model_id="statistical",
            model_version="research-candidate-statistical-v1",
            contract_sha256=run["contract_sha256"],
            source_dataset_sha256=run["source_dataset_sha256"],
            feature_output_sha256=run["feature_output_sha256"],
            feature_names=tuple(features["active_feature_names"]),
            threshold=float(run["models"]["statistical"]["threshold"]),
            threshold_provenance=ThresholdProvenance(),
            artifact_sha256={
                DETECTOR_FILENAME: sha256_file(published_model),
                BASELINE_FILENAME: sha256_file(published_baseline),
                GOLDEN_CASES_FILENAME: sha256_file(published_golden),
                SCORES_PARQUET_FILENAME: sha256_file(published_scores),
            },
        )
        published_manifest = temp_output / MANIFEST_FILENAME
        published_manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        lock_alert_policy(published_manifest, temp_output / "alert-policy.json")
        manifest_sha256 = sha256_file(published_manifest)
        temp_output.replace(safe_output_dir)
    except Exception:
        shutil.rmtree(temp_output, ignore_errors=True)
        raise
    return ChampionPackageResult(safe_output_dir, manifest, manifest_sha256)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build research candidate scoring package from Phase 1B run."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Path to Phase 1B run directory",
    )
    parser.add_argument(
        "--features",
        type=Path,
        required=True,
        help="Path to features.parquet",
    )
    parser.add_argument(
        "--feature-manifest",
        type=Path,
        required=True,
        help="Path to feature_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Target output directory for the research candidate package",
    )
    args = parser.parse_args(argv)

    result = build_research_candidate_package(
        run_dir=args.run_dir,
        features_path=args.features,
        feature_manifest_path=args.feature_manifest,
        output_dir=args.output_dir,
    )
    print(f"Output directory: {result.output_dir.resolve()}")
    print(f"Manifest SHA-256: {result.manifest_sha256}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
