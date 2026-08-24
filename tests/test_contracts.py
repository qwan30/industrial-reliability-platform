import hashlib
import json
from dataclasses import asdict
from datetime import datetime

from industrial_reliability.contracts import PHASE1, contract_manifest


def test_contract_excludes_leakage_columns() -> None:
    assert "LPS" not in PHASE1.predictor_columns
    assert not set(PHASE1.predictor_columns) & {
        "timestamp",
        "Pressure_switch",
        "Oil_level",
        "gpsLong",
        "gpsLat",
        "gpsSpeed",
        "gpsQuality",
    }


def test_contract_is_chronological_and_hashable() -> None:
    assert PHASE1.train.end <= PHASE1.calibration.start
    assert PHASE1.calibration.end <= PHASE1.holdout.start
    manifest = contract_manifest(PHASE1)
    assert manifest["contract_version"] == "phase1-v1"
    assert len(manifest["contract_sha256"]) == 64


def test_contract_freezes_dataset_schema_and_events() -> None:
    assert PHASE1.dataset_rows == 10_773_588
    assert PHASE1.source_columns[0] == "timestamp"
    assert PHASE1.source_columns[-1] == "gpsQuality"
    assert len(PHASE1.source_columns) == 21
    assert [event.paper_count for event in PHASE1.events] == [14_820, 1_800, 281_800]
    assert PHASE1.events[2].disagreement is not None


def test_contract_freezes_feasibility_gate_defaults() -> None:
    assert (
        PHASE1.min_detected_events,
        PHASE1.max_false_episodes_per_day,
        PHASE1.max_time_in_alert,
    ) == (2, 1.0, 0.05)


def test_contract_freezes_execution_policies() -> None:
    assert PHASE1.dataset_path == "data/raw/metropt/dataset_train.csv"
    assert PHASE1.dataset_release_status == (
        "local dataset and checksum are unofficial; official-release equivalence is unknown"
    )
    assert PHASE1.dataset_license_status == "authoritative license unknown"
    assert PHASE1.dataset_use_status == "approved for private feasibility analysis only"
    assert PHASE1.timestamp_policy == "naive_unspecified"
    assert PHASE1.split_window_policy == "complete_raw_lookback_inside_split"
    assert PHASE1.window_lookback_seconds == 1_800
    assert PHASE1.boundary_purge_policy == "purge_full_lookback"
    assert PHASE1.window_validity_policy == "exactly_1800_consecutive_one_second_observations"
    assert PHASE1.gap_max_delta_seconds == 1
    assert PHASE1.gap_policy == "reject_window_crossing_delta_greater_than_one_second"
    assert PHASE1.random_split_policy == "forbidden_chronological_train_calibration_holdout"
    assert PHASE1.fit_data_policy == "train_only"
    assert PHASE1.threshold_data_policy == "calibration_only"
    assert PHASE1.holdout_policy == "evaluate_once_no_retuning"
    assert PHASE1.evaluation_policy == "event_level_and_window_metrics"
    assert PHASE1.reporting_policy == (
        "absolute_event_detections_per_event_lead_false_episodes_per_day_window_pr_auc_time_in_alert"
    )
    assert PHASE1.model_selection_policy == (
        "simplest_model_meeting_gate_ties_statistical_then_isolation_forest_then_autoencoder"
    )


def _canonicalize(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_canonicalize(item) for item in value]
    return value


def test_contract_hash_matches_independent_canonical_reconstruction() -> None:
    manifest = contract_manifest(PHASE1)
    expected_payload = json.dumps(
        _canonicalize(asdict(PHASE1)),
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")

    assert b"contract_sha256" not in expected_payload
    assert manifest["contract_sha256"] == hashlib.sha256(expected_payload).hexdigest()
