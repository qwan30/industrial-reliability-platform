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


def compute_policy_sha256(policy_data: dict[str, Any]) -> str:
    copy_payload = {k: v for k, v in policy_data.items() if k != "policy_sha256"}
    canonical_json = json.dumps(
        copy_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def verify_policy_integrity(policy: LockedAlertPolicyV1) -> None:
    expected_sha = compute_policy_sha256(policy.to_dict())
    if policy.policy_sha256 != expected_sha:
        raise ValueError(
            f"Alert policy integrity check failed: expected self-hash {expected_sha}, got {policy.policy_sha256}"
        )


def _step_anomaly(
    ts: datetime,
    is_active: bool,
    anomaly_streak: int,
    last_resolution: datetime | None,
    persistence: int,
    merge_gap_seconds: int,
) -> tuple[bool, int, int]:
    new_anomaly_streak = anomaly_streak + 1
    new_active = is_active
    episode_inc = 0

    if not is_active and new_anomaly_streak >= persistence:
        is_merged = (
            last_resolution is not None
            and merge_gap_seconds > 0
            and (ts - last_resolution).total_seconds() <= merge_gap_seconds
        )
        if not is_merged:
            episode_inc = 1
        new_active = True

    return new_active, new_anomaly_streak, episode_inc


def _step_normal(
    ts: datetime,
    is_active: bool,
    normal_streak: int,
    cooldown: int,
) -> tuple[bool, int, datetime | None]:
    new_normal_streak = normal_streak + 1
    new_active = is_active
    new_resolution = None

    if is_active and new_normal_streak >= cooldown:
        new_active = False
        new_resolution = ts

    return new_active, new_normal_streak, new_resolution


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
        ts_val = row["window_end"]
        ts = datetime.fromisoformat(ts_val) if isinstance(ts_val, str) else ts_val

        if is_anom:
            normal_streak = 0
            is_active, anomaly_streak, ep_inc = _step_anomaly(
                ts, is_active, anomaly_streak, last_resolution, persistence, merge_gap_seconds
            )
            episodes += ep_inc
        else:
            anomaly_streak = 0
            is_active, normal_streak, res = _step_normal(ts, is_active, normal_streak, cooldown)
            if res is not None:
                last_resolution = res

        if is_active:
            alert_window_count += 1

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

    start_val = sorted_df["window_start"].min()
    end_val = sorted_df["window_end"].max()
    start_time = datetime.fromisoformat(start_val) if isinstance(start_val, str) else start_val
    end_time = datetime.fromisoformat(end_val) if isinstance(end_val, str) else end_val

    duration_days = max((end_time - start_time).total_seconds() / 86400.0, 1.0 / 288.0)
    false_episodes_per_day = episodes / duration_days
    time_in_alert = alert_window_count / max(len(sorted_df), 1)

    return PolicyMetrics(
        false_episodes_per_day=false_episodes_per_day,
        time_in_alert=time_in_alert,
    )


def select_policy(frame: pd.DataFrame, allow_fallback: bool = False) -> PolicySelection:
    unique_splits = set(frame["split"].unique())
    if unique_splits != {"calibration"} and not allow_fallback:
        raise ValueError(
            f"policy selection accepts calibration rows only, got splits: {unique_splits}"
        )

    best_selection: PolicySelection | None = None
    best_cost = float("inf")

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
        cost = metrics.false_episodes_per_day + 100 * metrics.time_in_alert
        if cost < best_cost:
            best_cost = cost
            best_selection = PolicySelection(
                persistence=persistence,
                cooldown=cooldown,
                merge_gap_seconds=merge_gap,
                metrics=metrics,
            )

    if allow_fallback and best_selection is not None:
        return best_selection

    raise ValueError("no predeclared alert policy satisfies the calibration gates")


def lock_alert_policy(manifest_path: Path, output_path: Path) -> LockedAlertPolicyV1:
    resolved_manifest = manifest_path.resolve()
    manifest_root = resolved_manifest.parent

    manifest_data = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    model_id = manifest_data["model_id"]
    model_version = manifest_data.get("model_version", f"champion-{model_id}-v1")
    source_dataset_sha256 = manifest_data["source_dataset_sha256"]
    contract_sha256 = manifest_data["contract_sha256"]
    threshold = float(manifest_data["threshold"])
    stride_seconds = int(manifest_data.get("stride_seconds", 300))
    is_research = manifest_data.get("operational_status") == "RESEARCH_ONLY"

    scores_file = manifest_root.joinpath("scores.parquet").resolve()
    if not scores_file.is_relative_to(manifest_root) or not scores_file.is_file():
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
        if is_research:
            # Strictly use train split fallback for research candidate — NEVER touch holdout!
            champion_calib = scores_df[
                (scores_df["model_id"] == model_id) & (scores_df["split"] == "train")
            ]
            if len(champion_calib) == 0:
                raise ValueError(
                    f"No calibration or train rows found for model {model_id} in {scores_file}"
                )
        else:
            raise ValueError(
                f"No calibration rows found for champion model {model_id} in {scores_file}"
            )

    source_split = "calibration" if "calibration" in champion_calib["split"].values else "train"
    selection = select_policy(champion_calib, allow_fallback=is_research)

    payload: dict[str, Any] = {
        "schema_version": "alert-policy-v1",
        "source_split": source_split,
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

    resolved_output = output_path.resolve()
    output_root = resolved_output.parent
    output_root.mkdir(parents=True, exist_ok=True)
    temp_output = output_root.joinpath(f"{resolved_output.name}.tmp").resolve()
    if not temp_output.is_relative_to(output_root):
        raise ValueError("Invalid output path")

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
        manifest_p = args.manifest.resolve()
        output_p = args.output.resolve()
        policy = lock_alert_policy(manifest_p, output_p)
        print(
            f"Locked alert policy {policy.policy_sha256}: "
            f"persistence={policy.persistence_decisions}, cooldown={policy.cooldown_decisions}, merge_gap={policy.merge_gap_seconds}"
        )


if __name__ == "__main__":
    main()
