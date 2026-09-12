"""Unit tests for Virtual Lab grounded Root Cause Analysis (RCA) generator."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from industrial_reliability.lab.contracts import (
    LabAlert,
    Observation,
)
from industrial_reliability.lab.evidence import create_alert_evidence
from industrial_reliability.lab.rca import generate_fallback_report, generate_lab_rca
from industrial_reliability.rca_openai import OpenAiRcaGenerator, ProviderRcaDraft
from industrial_reliability.runtime_messages import RcaObservationV1


@pytest.fixture
def sample_alert_and_evidence():
    run_id = uuid4()
    asset_id = uuid4()
    sensor_id = uuid4()

    alert = LabAlert(
        alert_id=uuid4(),
        run_id=run_id,
        asset_id=asset_id,
        sensor_id=sensor_id,
        origin="PROCESS_LIMIT",
        kind="ABOVE_LIMIT",
        state="OPEN",
        first_tick=20,
        last_tick=60,
    )

    obs1 = Observation(
        run_id=run_id,
        asset_id=asset_id,
        sensor_id=sensor_id,
        tick=20,
        unit="Pa",
        value=890000.0,
        quality="GOOD",
        profile_digest="p_digest",
    )
    obs2 = Observation(
        run_id=run_id,
        asset_id=asset_id,
        sensor_id=sensor_id,
        tick=40,
        unit="Pa",
        value=910000.0,
        quality="GOOD",
        profile_digest="p_digest",
    )
    obs3 = Observation(
        run_id=run_id,
        asset_id=asset_id,
        sensor_id=sensor_id,
        tick=60,
        unit="Pa",
        value=920000.0,
        quality="GOOD",
        profile_digest="p_digest",
    )

    run = MagicMock()
    run.run_id = run_id
    run.definition_digest = "def_digest"
    run.profile_digest = "prof_digest"
    run.baseline_id = None

    evidence = create_alert_evidence(alert, (obs1, obs2, obs3), run)
    return alert, evidence


def test_fallback_report_generation(sample_alert_and_evidence) -> None:
    alert, evidence = sample_alert_and_evidence

    report = generate_fallback_report(alert, evidence, reason="PROVIDER_UNCONFIGURED")

    assert report.alert_id == alert.alert_id
    assert report.status == "COMPLETE"
    assert "PROVIDER_UNCONFIGURED" in report.uncertainty[1]
    assert len(report.observations) >= 1
    assert report.observations[0].evidence_ids[0] == evidence.evidence_id
    assert report.provider_model is None


def test_generate_lab_rca_without_generator(sample_alert_and_evidence) -> None:
    alert, evidence = sample_alert_and_evidence

    report = generate_lab_rca(alert, evidence, generator=None)
    assert report.status == "COMPLETE"
    assert report.alert_id == alert.alert_id
    assert report.provider_model is None


def test_generate_lab_rca_with_mock_provider(sample_alert_and_evidence) -> None:
    alert, evidence = sample_alert_and_evidence

    mock_generator = MagicMock(spec=OpenAiRcaGenerator)
    mock_generator._model = "gpt-4o"
    mock_generator.generate_draft.return_value = ProviderRcaDraft(
        summary="High pressure discharge exceeded 8.5 bar upper limit.",
        observations=(
            RcaObservationV1(
                claim="Pressure reached 9.2 bar across ticks 20..60.",
                evidence_ids=(str(evidence.evidence_id),),
            ),
        ),
        uncertainty=("Mechanical valve status unverified by downstream flow telemetry.",),
        next_checks=("Inspect control valve opening command setpoints.",),
    )

    report = generate_lab_rca(alert, evidence, generator=mock_generator)
    assert report.status == "COMPLETE"
    assert report.provider_model == "gpt-4o"
    assert "High pressure discharge" in report.summary
    assert report.observations[0].evidence_ids[0] == evidence.evidence_id


def test_generate_lab_rca_provider_failure_falls_back(sample_alert_and_evidence) -> None:
    alert, evidence = sample_alert_and_evidence

    mock_generator = MagicMock(spec=OpenAiRcaGenerator)
    mock_generator.generate_draft.side_effect = RuntimeError("OpenAI API rate limit exceeded")

    report = generate_lab_rca(alert, evidence, generator=mock_generator)
    assert report.status == "COMPLETE"
    assert "RuntimeError" in report.uncertainty[1]
    assert report.provider_model is None
