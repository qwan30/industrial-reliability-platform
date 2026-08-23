from industrial_reliability.contracts import PHASE1, contract_manifest


def test_contract_excludes_leakage_columns() -> None:
    assert "LPS" not in PHASE1.predictor_columns
    assert not set(PHASE1.predictor_columns) & {
        "timestamp", "Pressure_switch", "Oil_level",
        "gpsLong", "gpsLat", "gpsSpeed", "gpsQuality",
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
