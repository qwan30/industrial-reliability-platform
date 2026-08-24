from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from industrial_reliability.runtime_messages import (
    ErrorResponseV1,
    EvidenceValueV1,
    FeatureVectorV1,
    QuarantineRecordV1,
    ReplayCommandV1,
    ReplayStatusV1,
    ScoreDecisionV1,
    ScoreResponseV1,
    TelemetryEventV1,
)


def _valid_coverage_payload() -> dict[str, object]:
    return {
        "observations_by_bin": (30, 30, 30, 30, 30, 30),
        "bin_ends": (
            datetime(2020, 2, 25, 0, 5),
            datetime(2020, 2, 25, 0, 10),
            datetime(2020, 2, 25, 0, 15),
            datetime(2020, 2, 25, 0, 20),
            datetime(2020, 2, 25, 0, 25),
            datetime(2020, 2, 25, 0, 30),
        ),
    }


def _valid_feature_vector_payload() -> dict[str, object]:
    return {
        "schema_version": "feature-vector-v1",
        "message_id": uuid4(),
        "replay_session_id": uuid4(),
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "source_timestamp": datetime(2020, 2, 25, 0, 30),
        "emitted_at": datetime.now(UTC),
        "window_id": uuid4(),
        "machine_id": "metropt-compressor-01",
        "window_start": datetime(2020, 2, 25, 0, 0),
        "window_end": datetime(2020, 2, 25, 0, 30),
        "feature_names": ("tp2_mean", "dv_pressure_mean"),
        "feature_values": (1.23, 4.56),
        "coverage": _valid_coverage_payload(),
    }


def test_feature_vector_rejects_extra_or_nonfinite_values() -> None:
    payload_nan = _valid_feature_vector_payload()
    payload_nan["feature_values"] = (float("nan"), 4.56)
    with pytest.raises(ValidationError):
        FeatureVectorV1.model_validate(payload_nan)

    payload_extra = _valid_feature_vector_payload()
    payload_extra["extra_field"] = "not_allowed"
    with pytest.raises(ValidationError):
        FeatureVectorV1.model_validate(payload_extra)


def test_score_request_requires_matching_feature_lengths() -> None:
    payload = _valid_feature_vector_payload()
    payload["feature_values"] = (1.23,)
    with pytest.raises(ValidationError, match="same length"):
        FeatureVectorV1.model_validate(payload)


def test_score_decision_and_envelope_serialization() -> None:
    payload = _valid_feature_vector_payload()
    fv = FeatureVectorV1.model_validate(payload)
    evidence = (
        EvidenceValueV1(feature_name="tp2_mean", feature_value=1.23, robust_deviation=0.5),
        EvidenceValueV1(feature_name="dv_pressure_mean", feature_value=4.56, robust_deviation=1.2),
    )
    decision = ScoreDecisionV1(
        message_id=uuid4(),
        replay_session_id=fv.replay_session_id,
        source_dataset_sha256=fv.source_dataset_sha256,
        contract_sha256=fv.contract_sha256,
        source_timestamp=fv.source_timestamp,
        emitted_at=datetime.now(UTC),
        decision_id=uuid4(),
        window_id=fv.window_id,
        model_version="champion-statistical-v1",
        score=0.75,
        threshold=1.0,
        is_anomaly=False,
        evidence_vector=evidence,
    )
    resp = ScoreResponseV1(data=decision)
    json_str = resp.model_dump_json()
    assert "champion-statistical-v1" in json_str
    assert resp.success is True

    err_payload = {
        "success": False,
        "data": None,
        "error": {"code": "SCORING_CONTRACT_MISMATCH", "message": "Model mismatch"},
    }
    err_resp = ErrorResponseV1.model_validate(err_payload)
    assert err_resp.success is False
    assert err_resp.error.code == "SCORING_CONTRACT_MISMATCH"


def test_replay_command_validation() -> None:
    msg_id = uuid4()
    session_id = uuid4()
    cmd_id = uuid4()
    now_utc = datetime.now(UTC)

    # Valid START command
    start_cmd = ReplayCommandV1(
        message_id=msg_id,
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=now_utc,
        command_id=cmd_id,
        action="START",
        speed=100,
        range_start=datetime(2020, 3, 1, 0, 0),
        range_end=datetime(2020, 3, 1, 1, 0),
    )
    assert start_cmd.action == "START"
    assert start_cmd.speed == 100

    # START without range must fail
    bad_start = {
        "message_id": msg_id,
        "replay_session_id": session_id,
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "source_timestamp": datetime(2020, 3, 1, 0, 0),
        "emitted_at": now_utc,
        "command_id": cmd_id,
        "action": "START",
        "speed": 100,
        "range_start": None,
        "range_end": None,
    }
    with pytest.raises(ValidationError, match="requires range_start and range_end"):
        ReplayCommandV1.model_validate(bad_start)

    # PAUSE with range must fail
    bad_pause = {
        "message_id": msg_id,
        "replay_session_id": session_id,
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "source_timestamp": datetime(2020, 3, 1, 0, 0),
        "emitted_at": now_utc,
        "command_id": cmd_id,
        "action": "PAUSE",
        "speed": 100,
        "range_start": datetime(2020, 3, 1, 0, 0),
        "range_end": datetime(2020, 3, 1, 1, 0),
    }
    with pytest.raises(ValidationError, match="must not specify range_start"):
        ReplayCommandV1.model_validate(bad_pause)


def test_replay_status_validation() -> None:
    msg_id = uuid4()
    session_id = uuid4()
    now_utc = datetime.now(UTC)

    # Valid RUNNING status
    status = ReplayStatusV1(
        message_id=msg_id,
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=now_utc,
        state="RUNNING",
        last_sequence=10,
    )
    assert status.state == "RUNNING"
    assert status.error_code is None

    # FAILED without error_code must fail
    bad_failed = {
        "message_id": msg_id,
        "replay_session_id": session_id,
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "source_timestamp": datetime(2020, 3, 1, 0, 0),
        "emitted_at": now_utc,
        "state": "FAILED",
        "last_sequence": 10,
        "error_code": None,
    }
    with pytest.raises(ValidationError, match="FAILED state requires non-empty error_code"):
        ReplayStatusV1.model_validate(bad_failed)


def test_telemetry_event_validation() -> None:
    msg_id = uuid4()
    session_id = uuid4()
    now_utc = datetime.now(UTC)

    te = TelemetryEventV1(
        message_id=msg_id,
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=now_utc,
        machine_id="compressor-01",
        sequence=1,
        tp2=1.0,
        tp3=2.0,
        h1=3.0,
        dv_pressure=4.0,
        reservoirs=5.0,
        oil_temperature=6.0,
        motor_current=7.0,
        comp=1,
        dv_electric=0,
        towers=1,
        mpg=0,
        lps=1,
        pressure_switch=0,
        oil_level=1,
        caudal_impulses=0,
    )
    assert te.sequence == 1
    assert te.comp == 1

    # Non-binary digital value must fail
    bad_te = {
        "message_id": msg_id,
        "replay_session_id": session_id,
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "source_timestamp": datetime(2020, 3, 1, 0, 0),
        "emitted_at": now_utc,
        "machine_id": "compressor-01",
        "sequence": 1,
        "tp2": 1.0,
        "tp3": 2.0,
        "h1": 3.0,
        "dv_pressure": 4.0,
        "reservoirs": 5.0,
        "oil_temperature": 6.0,
        "motor_current": 7.0,
        "comp": 2,
        "dv_electric": 0,
        "towers": 1,
        "mpg": 0,
        "lps": 1,
        "pressure_switch": 0,
        "oil_level": 1,
        "caudal_impulses": 0,
    }
    with pytest.raises(ValidationError):
        TelemetryEventV1.model_validate(bad_te)


def test_quarantine_record_validation() -> None:
    qr = QuarantineRecordV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        emitted_at=datetime.now(UTC),
        original_topic="irp.replay.commands.v1",
        partition=0,
        offset=42,
        payload_sha256="c" * 64,
        error_code="INVALID_JSON",
        error_detail="Unparseable bytes",
    )
    assert qr.original_topic == "irp.replay.commands.v1"
    assert qr.offset == 42
