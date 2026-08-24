from __future__ import annotations

from industrial_reliability.phase1b_contracts import (
    PHASE1B,
    phase1b_contract_manifest,
    phase1b_evaluation_events,
)


def test_phase1b_freezes_source_and_leakage_boundaries() -> None:
    assert PHASE1B.source_doi == "10.24432/C5VW3R"
    assert (
        PHASE1B.archive_sha256
        == "aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a"
    )
    assert PHASE1B.expected_rows == 1_516_948
    assert PHASE1B.license == "CC BY 4.0"
    assert PHASE1B.csv_member == "MetroPT3(AirCompressor).csv"
    assert "lps" not in PHASE1B.predictor_columns
    assert "timestamp" not in PHASE1B.predictor_columns
    assert PHASE1B.min_bin_observations == 24
    assert PHASE1B.lookback_bins == 6


def test_phase1b_events_normalize_minute_precision_half_open() -> None:
    events = phase1b_evaluation_events()
    assert len(events) == 4
    assert events[0].source_start.isoformat(timespec="minutes") == "2020-04-18T00:00"
    assert events[0].source_end.isoformat(timespec="minutes") == "2020-04-19T00:00"
    assert phase1b_contract_manifest()["contract_sha256"]
