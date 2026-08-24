"""Calibration-locked alert policy module for Phase 5."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd

from industrial_reliability.phase1b_data import sha256_file

PERSISTENCE_CANDIDATES = (1, 2, 3)
COOLDOWN_CANDIDATES = (1, 2, 3, 6)
MERGE_GAP_SECONDS_CANDIDATES = (0, 300, 900)


@dataclass(frozen=True, slots=True)
class PolicyMetrics:
    false_episodes_per_day: float
    time_in_alert: float


@dataclass(frozen=True, slots=True)
class PolicySelection:
    persistence: int
    cooldown: int
    merge_gap_seconds: int
    metrics: PolicyMetrics


@dataclass(frozen=True, slots=True)
class LockedAlertPolicyV1:
    schema_version: str
    source_split: str
    source_scores_sha256: str
    source_dataset_sha256: str
    contract_sha256: str
    model_id: str
    model_version: str
    threshold: float
    stride_seconds: int
    persistence_decisions: int
    cooldown_decisions: int
    merge_gap_seconds: int
    calibration_false_episodes_per_day: float
    calibration_time_in_alert: float
    policy_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _simulate_alert_stream(
    sorted_df: pd.DataFrame,
    persistence: int,
    cooldown: int,
    merge_gap_seconds: int,
) -> tuple[int, int]:
    is_active = False
    anomaly_streak = 0
    normal_streak = 0
    last_resolution: datetime | None = None
    episodes = 0
    alert_window_count = 0

    for _, row in sorted_df.iterrows():
        is_anom = bool(row["is_anomaly"])
        ts = row["window_end"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        if is_anom:
            normal_streak = 0
            anomaly_streak += 1
            if not is_active and anomaly_streak >= persistence:
                is_merged = (
                    last_resolution is not None
                    and merge_gap_seconds > 0
                    and (ts - last_resolution).total_seconds() <= merge_gap_seconds
                )
                if not is_merged:
                    episodes += 1
                is_active = True
            if is_active:
                alert_window_count += 1
        else:
            anomaly_streak = 0
            normal_streak += 1
            if is_active:
                alert_window_count += 1
                if normal_streak >= cooldown:
                    is_active = False
                    last_resolution = ts

    return episodes, alert_window_count


def evaluate_candidate(
    frame: pd.DataFrame,
    persistence: int,
    cooldown: int,
    merge_gap_seconds: int,
) -> PolicyMetrics:
    if len(frame) == 0:
        return PolicyMetrics(false_episodes_per_day=0.0, time_in_alert=0.0)

    sorted_df = frame.sort_values("window_end").reset_index(drop=True)
    episodes, alert_window_count = _simulate_alert_stream(
        sorted_df, persistence, cooldown, merge_gap_seconds
    )

    start_time = sorted_df["window_start"].min()
    end_time = sorted_df["window_end"].max()
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)

    duration_days = max((end_time - start_time).total_seconds() / 86400.0, 1.0 / 288.0)
    false_episodes_per_day = episodes / duration_days
    time_in_alert = alert_window_count / max(len(sorted_df), 1)

    return PolicyMetrics(
        false_episodes_per_day=false_episodes_per_day,
        time_in_alert=time_in_alert,
    )


def select_policy(frame: pd.DataFrame, *, stride_seconds: int = 300) -> PolicySelection:
    unique_splits = set(frame["split"].unique())
    if unique_splits != {"calibration"}:
        raise ValueError(
            f"policy selection accepts calibration rows only, got splits: {unique_splits}"
        )

    for persistence, cooldown, merge_gap in product(
        PERSISTENCE_CANDIDATES,
        COOLDOWN_CANDIDATES,
        MERGE_GAP_SECONDS_CANDIDATES,
    ):
        metrics = evaluate_candidate(
            frame,
            persistence=persistence,
            cooldown=cooldown,
            merge_gap_seconds=merge_gap,
        )
        if metrics.false_episodes_per_day <= 1.0 and metrics.time_in_alert <= 0.05:
            return PolicySelection(
                persistence=persistence,
                cooldown=cooldown,
                merge_gap_seconds=merge_gap,
                metrics=metrics,
            )

    raise ValueError("no predeclared alert policy satisfies the calibration gates")


def lock_alert_policy(manifest_path: Path, output_path: Path) -> LockedAlertPolicyV1:
    resolved_manifest = manifest_path.resolve()
    resolved_output = output_path.resolve()

    manifest_data = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    model_id = manifest_data["model_id"]
    model_version = manifest_data.get("model_version", f"champion-{model_id}-v1")
    source_dataset_sha256 = manifest_data["source_dataset_sha256"]
    contract_sha256 = manifest_data["contract_sha256"]
    threshold = float(manifest_data["threshold"])
    stride_seconds = int(manifest_data.get("stride_seconds", 300))

    scores_file = resolved_manifest.parent / "scores.parquet"
    if not scores_file.is_file():
        raise ValueError(f"Scores file not found at {scores_file}")

    actual_scores_sha = sha256_file(scores_file)
    expected_scores_sha = manifest_data.get("artifact_sha256", {}).get("scores.parquet")
    if expected_scores_sha and actual_scores_sha != expected_scores_sha:
        raise ValueError(
            f"scores.parquet SHA-256 mismatch: expected {expected_scores_sha}, got {actual_scores_sha}"
        )

    scores_df = pd.read_parquet(scores_file)
    champion_calib = scores_df[
        (scores_df["model_id"] == model_id) & (scores_df["split"] == "calibration")
    ]
    if len(champion_calib) == 0:
        raise ValueError(
            f"No calibration rows found for champion model {model_id} in {scores_file}"
        )

    selection = select_policy(champion_calib, stride_seconds=stride_seconds)

    payload: dict[str, Any] = {
        "schema_version": "alert-policy-v1",
        "source_split": "calibration",
        "source_scores_sha256": actual_scores_sha,
        "source_dataset_sha256": source_dataset_sha256,
        "contract_sha256": contract_sha256,
        "model_id": model_id,
        "model_version": model_version,
        "threshold": threshold,
        "stride_seconds": stride_seconds,
        "persistence_decisions": selection.persistence,
        "cooldown_decisions": selection.cooldown,
        "merge_gap_seconds": selection.merge_gap_seconds,
        "calibration_false_episodes_per_day": selection.metrics.false_episodes_per_day,
        "calibration_time_in_alert": selection.metrics.time_in_alert,
    }

    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    policy_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    payload["policy_sha256"] = policy_sha256

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = resolved_output.with_suffix(".tmp")
    temp_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    temp_output.replace(resolved_output)

    return LockedAlertPolicyV1(**payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Alert Policy Locking CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    lock_parser = subparsers.add_parser(
        "lock", help="Lock alert policy from champion calibration data"
    )
    lock_parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to champion manifest.json",
    )
    lock_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for alert-policy.json",
    )

    args = parser.parse_args()
    if args.command == "lock":
        policy = lock_alert_policy(args.manifest.resolve(), args.output.resolve())
        print(
            f"Locked alert policy {policy.policy_sha256}: "
            f"persistence={policy.persistence_decisions}, cooldown={policy.cooldown_decisions}, merge_gap={policy.merge_gap_seconds}"
        )


if __name__ == "__main__":
    main()
