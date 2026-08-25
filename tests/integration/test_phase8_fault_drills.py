from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from prometheus_client import CollectorRegistry

from industrial_reliability.fault_report import (
    DrillMetricDeltasV1,
    DrillResultV1,
    classify_drill,
    publish_drill_report,
)
from industrial_reliability.metrics import build_runtime_metrics
from industrial_reliability.runtime_messages import (
    CoverageEvidenceV1,
    EvidenceValueV1,
    FeatureVectorV1,
    ScoreDecisionV1,
)
from industrial_reliability.scoring_client import RetryableScoringError
from industrial_reliability.worker import StreamingWorker, WorkerSettings


@pytest.mark.asyncio
async def test_in_process_phase8_fault_drills_matrix(tmp_path: Path) -> None:
    # -------------------------------------------------------------
    # DRILL 1: Service Outage (Scoring API Down) -> Expect SERVICE
    # -------------------------------------------------------------
    reg_1 = CollectorRegistry()
    metrics_1 = build_runtime_metrics(reg_1)

    mock_scoring_failing = Mock()
    mock_scoring_failing.score = AsyncMock(
        side_effect=RetryableScoringError("Connection refused by scoring API")
    )
    mock_scoring_failing.close = AsyncMock()

    settings_1 = WorkerSettings(
        bootstrap_servers="localhost:9092",
        scoring_api_url="http://localhost:8000",
        model_version="champion-statistical-v1",
        source_dataset_sha256="0" * 64,
        contract_sha256="0" * 64,
        feature_names=("tp2_mean", "dv_pressure_mean"),
    )
    worker_1 = StreamingWorker(
        settings=settings_1, scoring_client=mock_scoring_failing, metrics=metrics_1
    )
    worker_1.producer = AsyncMock()

    now_naive = datetime(2020, 2, 25, 0, 30)
    feat_1 = FeatureVectorV1(
        message_id=uuid4(),
        replay_session_id=uuid4(),
        source_dataset_sha256="0" * 64,
        contract_sha256="0" * 64,
        source_timestamp=now_naive,
        emitted_at=datetime.now(UTC),
        window_id=uuid4(),
        window_start=now_naive - timedelta(minutes=30),
        window_end=now_naive,
        machine_id="metropt3",
        feature_names=("tp2_mean", "dv_pressure_mean"),
        feature_values=(1.0, 2.0),
        coverage=CoverageEvidenceV1(
            observations_by_bin=(30, 30, 30, 30, 30, 30),
            bin_ends=(
                now_naive - timedelta(minutes=25),
                now_naive - timedelta(minutes=20),
                now_naive - timedelta(minutes=15),
                now_naive - timedelta(minutes=10),
                now_naive - timedelta(minutes=5),
                now_naive,
            ),
        ),
    )

    from industrial_reliability.worker import SessionFailedError

    with pytest.raises(SessionFailedError):
        await worker_1._process_feature(feat_1)

    deltas_1 = DrillMetricDeltasV1(
        score_unavailable_delta=metrics_1.score_requests.labels(outcome="unavailable")._value.get(),
        score_ok_delta=metrics_1.score_requests.labels(outcome="ok")._value.get(),
        telemetry_quarantined_delta=metrics_1.telemetry_events.labels(
            outcome="quarantined"
        )._value.get(),
        anomaly_decisions_delta=metrics_1.anomaly_decisions._value.get(),
    )
    class_1, summary_1 = classify_drill(deltas_1)
    res_1 = DrillResultV1(
        drill_type="scoring-outage",
        expected_classification="SERVICE",
        actual_classification=class_1,
        passed=class_1 == "SERVICE",
        deltas=deltas_1,
        evidence_summary=summary_1,
    )
    assert res_1.passed is True

    # -------------------------------------------------------------
    # DRILL 2: Malformed Telemetry (Bad Bytes) -> Expect DATA
    # -------------------------------------------------------------
    reg_2 = CollectorRegistry()
    metrics_2 = build_runtime_metrics(reg_2)
    worker_2 = StreamingWorker(settings=settings_1, scoring_client=AsyncMock(), metrics=metrics_2)
    worker_2.producer = AsyncMock()

    # Feed invalid bytes
    mock_bad_record = Mock(
        value=b"NOT_A_VALID_JSON_RECORD{{{",
        topic="industrial.metropt3.telemetry.v1",
        partition=0,
        offset=123,
    )
    await worker_2._handle_telemetry_record(mock_bad_record)

    deltas_2 = DrillMetricDeltasV1(
        telemetry_quarantined_delta=metrics_2.telemetry_events.labels(
            outcome="quarantined"
        )._value.get(),
        score_unavailable_delta=metrics_2.score_requests.labels(outcome="unavailable")._value.get(),
        anomaly_decisions_delta=metrics_2.anomaly_decisions._value.get(),
    )
    class_2, summary_2 = classify_drill(deltas_2)
    res_2 = DrillResultV1(
        drill_type="malformed-telemetry",
        expected_classification="DATA",
        actual_classification=class_2,
        passed=class_2 == "DATA",
        deltas=deltas_2,
        evidence_summary=summary_2,
    )
    assert res_2.passed is True

    # -------------------------------------------------------------
    # DRILL 3: Known Abnormal Machine Replay -> Expect MACHINE
    # -------------------------------------------------------------
    reg_3 = CollectorRegistry()
    metrics_3 = build_runtime_metrics(reg_3)

    decision_id = uuid4()
    mock_scoring_ok = Mock()
    mock_scoring_ok.score = AsyncMock(
        return_value=ScoreDecisionV1(
            message_id=decision_id,
            replay_session_id=feat_1.replay_session_id,
            source_dataset_sha256="0" * 64,
            contract_sha256="0" * 64,
            source_timestamp=feat_1.source_timestamp,
            emitted_at=datetime.now(UTC),
            decision_id=decision_id,
            window_id=feat_1.window_id,
            model_version="champion-statistical-v1",
            score=3500.0,
            threshold=1200.0,
            is_anomaly=True,
            evidence_vector=(
                EvidenceValueV1(
                    feature_name="tp2_mean",
                    feature_value=9.5,
                    robust_deviation=8.3,
                ),
            ),
        )
    )
    mock_scoring_ok.close = AsyncMock()

    worker_3 = StreamingWorker(
        settings=settings_1, scoring_client=mock_scoring_ok, metrics=metrics_3
    )
    worker_3.producer = AsyncMock()

    await worker_3._process_feature(feat_1)
    metrics_3.record_alert_action("opened")

    deltas_3 = DrillMetricDeltasV1(
        score_ok_delta=metrics_3.score_requests.labels(outcome="ok")._value.get(),
        anomaly_decisions_delta=metrics_3.anomaly_decisions._value.get(),
        alert_events_delta=metrics_3.alert_events.labels(action="opened")._value.get(),
        telemetry_quarantined_delta=metrics_3.telemetry_events.labels(
            outcome="quarantined"
        )._value.get(),
        score_unavailable_delta=metrics_3.score_requests.labels(outcome="unavailable")._value.get(),
    )
    class_3, summary_3 = classify_drill(deltas_3)
    res_3 = DrillResultV1(
        drill_type="known-abnormal-replay",
        expected_classification="MACHINE",
        actual_classification=class_3,
        passed=class_3 == "MACHINE",
        deltas=deltas_3,
        evidence_summary=summary_3,
    )
    assert res_3.passed is True

    # Publish full drill report
    json_path = tmp_path / "phase-8-observability-reliability.json"
    md_path = tmp_path / "phase-8-observability-reliability.md"
    report = publish_drill_report([res_1, res_2, res_3], json_path=json_path, md_path=md_path)
    assert report.all_passed is True
