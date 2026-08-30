import pytest

from industrial_reliability.phase1b_contracts import (
    ANALOG_SIGNAL_BY_NAME,
    ANALOG_SIGNAL_CONTRACTS,
    PHASE1B_CONTRACT_SHA256,
    PHASE1B_PREPARED_OUTPUT_SHA256,
    PHASE1B_SOURCE_DATASET_SHA256,
    PHASE1C,
    AnalogSignalContract,
    metropt3_contract_manifest,
    phase1b_contract_manifest,
    phase1b_evaluation_events,
    validate_analog_value,
)


def test_phase1b_identity_constants_match_immutable_artifacts() -> None:
    assert PHASE1B_CONTRACT_SHA256 == (
        "149e164748522fe6dfa844a8de70b29ee1259122962e036ff6a563c1120047d8"
    )
    assert PHASE1B_SOURCE_DATASET_SHA256 == (
        "aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a"
    )
    assert PHASE1B_PREPARED_OUTPUT_SHA256 == (
        "0c31129cc4f4be982a6aec79f448485a2674b2fe79643186737143dccfe6d42a"
    )


def test_phase1c_is_the_only_executable_contract_v2() -> None:
    manifest = metropt3_contract_manifest(PHASE1C)
    assert PHASE1C.contract_version == "phase1b-contract-v2"
    assert manifest["contract_sha256"] == (
        "31f8689256951067e28c9cbb48a930c1617d8eea8c7133ba1a315f632842e1ad"
    )
    assert manifest["contract_sha256"] != PHASE1B_CONTRACT_SHA256
    assert phase1b_contract_manifest is metropt3_contract_manifest


def test_phase1b_freezes_source_and_leakage_boundaries() -> None:
    assert PHASE1C.source_doi == "10.24432/C5VW3R"
    assert (
        PHASE1C.archive_sha256 == "aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a"
    )
    assert PHASE1C.expected_rows == 1_516_948
    assert PHASE1C.license == "CC BY 4.0"
    assert PHASE1C.csv_member == "MetroPT3(AirCompressor).csv"
    assert "lps" not in PHASE1C.predictor_columns
    assert "timestamp" not in PHASE1C.predictor_columns
    assert PHASE1C.min_bin_observations == 24
    assert PHASE1C.lookback_bins == 6


def test_phase1b_events_normalize_minute_precision_half_open() -> None:
    events = phase1b_evaluation_events()
    assert len(events) == 4
    assert events[0].source_start.isoformat(timespec="minutes") == "2020-04-18T00:00"
    assert events[0].source_end.isoformat(timespec="minutes") == "2020-04-19T00:00"
    assert metropt3_contract_manifest(PHASE1C)["contract_sha256"]


def test_phase1b_contracts_version_units_and_time_semantics() -> None:
    assert PHASE1C.contract_version == "phase1b-contract-v2"
    assert PHASE1C.timestamp_semantics == "timezone-naive source clock"
    assert PHASE1C.nominal_cadence_seconds == 10
    manifest = metropt3_contract_manifest(PHASE1C)
    assert manifest["contract_version"] == "phase1b-contract-v2"
    assert manifest["timestamp_semantics"] == "timezone-naive source clock"
    assert manifest["nominal_cadence_seconds"] == 10


def test_analog_signal_contracts_definition() -> None:
    assert len(ANALOG_SIGNAL_CONTRACTS) == 7
    expected = {
        "tp2": ("bar", -1.0, 20.0),
        "tp3": ("bar", -1.0, 20.0),
        "h1": ("bar", -1.0, 20.0),
        "dv_pressure": ("bar", -1.0, 20.0),
        "reservoirs": ("bar", -1.0, 20.0),
        "oil_temperature": ("degC", -40.0, 150.0),
        "motor_current": ("A", 0.0, 50.0),
    }
    for c in ANALOG_SIGNAL_CONTRACTS:
        assert isinstance(c, AnalogSignalContract)
        unit, hard_min, hard_max = expected[c.name]
        assert c.unit == unit
        assert c.hard_min == hard_min
        assert c.hard_max == hard_max
        assert ANALOG_SIGNAL_BY_NAME[c.name] is c


def test_official_observed_extrema_are_inside_hard_envelopes() -> None:
    observed = {
        "tp2": (-0.032, 10.676),
        "tp3": (0.7300000000000004, 10.302),
        "h1": (-0.0360000000000013, 10.288),
        "dv_pressure": (-0.032, 9.844),
        "reservoirs": (0.7119999999999997, 10.3),
        "oil_temperature": (15.400000000000006, 89.05000000000001),
        "motor_current": (0.0199999999999995, 9.295),
    }
    for name, (minimum, maximum) in observed.items():
        assert validate_analog_value(name, minimum) == minimum
        assert validate_analog_value(name, maximum) == maximum


@pytest.mark.parametrize(
    "name,value",
    [
        ("tp2", 20.1),
        ("tp2", -1.1),
        ("tp3", 20.1),
        ("tp3", -1.1),
        ("h1", 20.1),
        ("h1", -1.1),
        ("dv_pressure", 20.1),
        ("dv_pressure", -1.1),
        ("reservoirs", 20.1),
        ("reservoirs", -1.1),
        ("oil_temperature", 150.1),
        ("oil_temperature", -40.1),
        ("motor_current", 50.1),
        ("motor_current", -0.1),
        ("tp2", float("nan")),
        ("tp2", float("inf")),
        ("tp2", float("-inf")),
    ],
)
def test_validate_analog_value_rejects_out_of_envelope(name: str, value: float) -> None:
    with pytest.raises(ValueError, match=f"{name} outside hard"):
        validate_analog_value(name, value)
