from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, generate_latest

from industrial_reliability.metrics import (
    ALERT_ACTIONS,
    SCORE_OUTCOMES,
    SEGMENT_BREAK_REASONS,
    TELEMETRY_OUTCOMES,
    build_runtime_metrics,
    mount_api_metrics,
)


def test_metric_contract_has_only_bounded_labels() -> None:
    registry = CollectorRegistry()
    metrics = build_runtime_metrics(registry)
    metrics.telemetry_events.labels(outcome="quarantined").inc()
    metrics.segment_breaks.labels(reason="gap").inc()
    metrics.dependency_ready.labels(dependency="postgres").set(0)

    text = generate_latest(registry).decode()
    assert 'irp_telemetry_events_total{outcome="quarantined"} 1.0' in text
    assert 'irp_segment_breaks_total{reason="gap"} 1.0' in text
    assert 'irp_dependency_ready{dependency="postgres"} 0.0' in text
    assert "replay_session_id=" not in text
    assert "alert_id=" not in text
    assert "machine_id=" not in text
    assert "feature_id=" not in text


def test_metric_contract_rejects_unknown_enum_values() -> None:
    metrics = build_runtime_metrics(CollectorRegistry())
    with pytest.raises(ValueError, match="unsupported telemetry outcome: made-up"):
        metrics.record_telemetry("made-up")

    with pytest.raises(ValueError, match="unsupported segment break reason: unknown"):
        metrics.record_segment_break("unknown")

    with pytest.raises(ValueError, match="unsupported score outcome: bad"):
        metrics.record_score_request(outcome="bad", duration=0.01)

    with pytest.raises(ValueError, match="unsupported alert action: fired"):
        metrics.record_alert_action("fired")

    with pytest.raises(ValueError, match="unsupported dependency: redis"):
        metrics.set_dependency_ready("redis", True)


def test_runtime_metrics_helper_methods() -> None:
    registry = CollectorRegistry()
    metrics = build_runtime_metrics(registry)

    for outcome in TELEMETRY_OUTCOMES:
        metrics.record_telemetry(outcome)
    for reason in SEGMENT_BREAK_REASONS:
        metrics.record_segment_break(reason)
    for outcome in SCORE_OUTCOMES:
        metrics.record_score_request(outcome=outcome, duration=0.005)
    for action in ALERT_ACTIONS:
        metrics.record_alert_action(action)

    metrics.set_dependency_ready("postgres", True)
    metrics.set_dependency_ready("kafka", False)
    metrics.set_consumer_lag(42.0)
    metrics.record_valid_window(coverage_ratio=0.98)
    metrics.record_anomaly_decision(score=1.45, is_anomaly=True)
    metrics.set_active_alerts(3)
    metrics.set_feature_psi_max(0.12)
    metrics.record_replay_session_failure("SCORING_UNAVAILABLE")

    text = generate_latest(registry).decode()
    assert 'irp_telemetry_events_total{outcome="accepted"} 1.0' in text
    assert 'irp_segment_breaks_total{reason="gap"} 1.0' in text
    assert 'irp_score_requests_total{outcome="ok"} 1.0' in text
    assert 'irp_alert_events_total{action="opened"} 1.0' in text
    assert 'irp_dependency_ready{dependency="postgres"} 1.0' in text
    assert 'irp_dependency_ready{dependency="kafka"} 0.0' in text
    assert "irp_kafka_consumer_lag 42.0" in text
    assert "irp_valid_windows_total 1.0" in text
    assert "irp_window_coverage_ratio 0.98" in text
    assert "irp_anomaly_score 1.45" in text
    assert "irp_anomaly_decisions_total 1.0" in text
    assert "irp_alerts_active 3.0" in text
    assert "irp_feature_psi_max 0.12" in text
    assert 'irp_replay_session_failures_total{error_code="SCORING_UNAVAILABLE"} 1.0' in text


def test_mount_api_metrics() -> None:
    app = FastAPI()
    registry = CollectorRegistry()
    metrics = build_runtime_metrics(registry)
    metrics.record_score_request("ok", 0.002)
    mount_api_metrics(app, metrics)

    client = TestClient(app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert 'irp_score_requests_total{outcome="ok"} 1.0' in response.text


def test_api_create_app_with_metrics() -> None:
    from unittest.mock import Mock

    from industrial_reliability.api import create_app
    from industrial_reliability.runtime_messages import FeatureVectorV1

    scorer = Mock()
    scorer.model_version = "champion-statistical-v1"
    scorer.feature_names = ("tp2_mean", "dv_pressure_mean")
    scorer.threshold = 1.25
    from industrial_reliability.runtime_messages import CoverageEvidenceV1, EvidenceValueV1

    scorer.score = Mock(
        return_value=Mock(
            score=1.5,
            threshold=1.25,
            is_anomaly=True,
            evidence_vector=(
                EvidenceValueV1(
                    feature_name="tp2_mean",
                    feature_value=1.0,
                    robust_deviation=0.0,
                ),
            ),
        )
    )

    registry = CollectorRegistry()
    metrics = build_runtime_metrics(registry)
    app = create_app(scorer=scorer, metrics=metrics)
    client = TestClient(app)

    # 1. Successful score request
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    now_naive = datetime(2020, 2, 25, 0, 30)
    feat = FeatureVectorV1(
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
    score_resp = client.post(
        "/v1/score",
        json={
            "model_version": "champion-statistical-v1",
            "feature_vector": feat.model_dump(mode="json"),
        },
    )
    assert score_resp.status_code == 200

    # 2. Check /metrics output
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    assert 'irp_score_requests_total{outcome="ok"} 1.0' in metrics_resp.text

    # 3. Model version mismatch error
    mismatch_resp = client.post(
        "/v1/score",
        json={"model_version": "wrong-version", "feature_vector": feat.model_dump(mode="json")},
    )
    assert mismatch_resp.status_code == 409

    metrics_resp_2 = client.get("/metrics")
    assert 'irp_score_requests_total{outcome="invalid_model"} 1.0' in metrics_resp_2.text
