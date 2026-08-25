from __future__ import annotations

import inspect
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from openai import OpenAI

from industrial_reliability.rca_evidence import EvidenceBundleV1, EvidenceItemV1
from industrial_reliability.rca_openai import (
    OpenAiRcaGenerator,
    ProviderRcaDraft,
    evidence_only_report,
)
from industrial_reliability.runtime_messages import RcaObservationV1


@pytest.fixture
def evidence_bundle() -> EvidenceBundleV1:
    now = datetime.now(UTC)
    item_1 = EvidenceItemV1(
        evidence_id="evidence-111111111111111111111111",
        tool_name="get_alert",
        observed_at=now,
        facts={"alert_id": "alert-1", "score": 1400.0, "threshold": 1200.0},
    )
    item_2 = EvidenceItemV1(
        evidence_id="evidence-222222222222222222222222",
        tool_name="get_score_evidence",
        observed_at=now,
        facts={"feature_tp2_mean_deviation": 1.5},
    )
    item_3 = EvidenceItemV1(
        evidence_id="evidence-333333333333333333333333",
        tool_name="get_model_provenance",
        observed_at=now,
        facts={"model_version": "champion-statistical-v1"},
    )
    item_4 = EvidenceItemV1(
        evidence_id="evidence-444444444444444444444444",
        tool_name="get_system_health",
        observed_at=now,
        facts={"health_status": "normal"},
    )
    return EvidenceBundleV1(
        schema_version="rca-evidence-bundle-v1",
        alert_id="alert-1",
        replay_session_id="session-1",
        model_version="champion-statistical-v1",
        contract_sha256="0" * 64,
        source_dataset_sha256="1" * 64,
        items=(item_1, item_2, item_3, item_4),
        bundle_sha256="2" * 64,
    )


def test_installed_sdk_supports_responses_parse() -> None:
    client = OpenAI(api_key="test-only-not-sent")
    parameters = inspect.signature(client.responses.parse).parameters
    assert {"model", "input", "text_format"} <= set(parameters)


def test_missing_key_returns_evidence_only(
    monkeypatch: pytest.MonkeyPatch, evidence_bundle: EvidenceBundleV1
) -> None:
    monkeypatch.delenv("RCA_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RCA_OPENAI_MODEL", raising=False)
    assert OpenAiRcaGenerator.from_env() is None

    report = evidence_only_report(evidence_bundle, "provider_not_configured")
    assert report.status == "UNAVAILABLE"
    assert report.provider_model is None
    assert set(report.evidence_ids) == {item.evidence_id for item in evidence_bundle.items}
    assert "persisted evidence only" in report.summary.lower()
    assert any("does not prove a mechanical root cause" in u for u in report.uncertainty)


def test_successful_provider_call_returns_complete(
    evidence_bundle: EvidenceBundleV1,
) -> None:
    fake_client = Mock()
    fake_response = Mock()
    fake_response.output_parsed = ProviderRcaDraft(
        summary="High compressor discharge pressure observed.",
        observations=(
            RcaObservationV1(
                claim="tp2_mean deviated from normal range.",
                evidence_ids=("evidence-222222222222222222222222",),
            ),
        ),
        uncertainty=("Anomaly evidence does not prove a mechanical root cause.",),
        next_checks=("Check discharge valve and cooling circuits.",),
    )
    fake_client.responses.parse.return_value = fake_response

    generator = OpenAiRcaGenerator(client=fake_client, model="gpt-4o")
    report = generator.generate(evidence_bundle)

    assert report.status == "COMPLETE"
    assert report.provider_model == "gpt-4o"
    assert report.summary == "High compressor discharge pressure observed."
    assert len(report.observations) == 1
    assert report.observations[0].evidence_ids == ("evidence-222222222222222222222222",)


def test_unknown_provider_citation_rejects_entire_draft(
    evidence_bundle: EvidenceBundleV1,
) -> None:
    fake_client = Mock()
    fake_response = Mock()
    fake_response.output_parsed = ProviderRcaDraft(
        summary="Alert exceeded threshold.",
        observations=(
            RcaObservationV1(
                claim="A bearing failed.",
                evidence_ids=("invented-evidence-id",),
            ),
        ),
        uncertainty=("Anomaly evidence does not prove a mechanical root cause.",),
        next_checks=("Inspect the compressor.",),
    )
    fake_client.responses.parse.return_value = fake_response

    generator = OpenAiRcaGenerator(client=fake_client, model="gpt-4o")
    report = generator.generate(evidence_bundle)

    assert report.status == "UNAVAILABLE"
    assert report.provider_model is None
    assert all("invented-evidence-id" not in obs.evidence_ids for obs in report.observations)


def test_secret_never_appears_in_repr_or_error(
    monkeypatch: pytest.MonkeyPatch, evidence_bundle: EvidenceBundleV1
) -> None:
    monkeypatch.setenv("RCA_OPENAI_API_KEY", "sk-secret-test-key-12345")
    monkeypatch.setenv("RCA_OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("RCA_TIMEOUT_SECONDS", "25")

    gen = OpenAiRcaGenerator.from_env()
    assert gen is not None
    rep = repr(gen)
    assert "sk-secret-test-key-12345" not in rep
    assert "sk-secret" not in str(gen)

    # Trigger failure
    gen._client.responses.parse = Mock(
        side_effect=RuntimeError("Failed with sk-secret-test-key-12345")
    )
    report = gen.generate(evidence_bundle)
    assert report.status == "UNAVAILABLE"
    assert "sk-secret" not in repr(report)


def test_invalid_timeout_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RCA_OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("RCA_OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("RCA_TIMEOUT_SECONDS", "not-a-number")

    gen = OpenAiRcaGenerator.from_env()
    assert gen is not None
    assert gen._timeout_seconds == 20.0


def test_empty_draft_or_empty_citations_trigger_fallback(
    evidence_bundle: EvidenceBundleV1,
) -> None:
    fake_client = Mock()
    fake_response = Mock()
    fake_response.output_parsed = None
    fake_client.responses.parse.return_value = fake_response

    gen = OpenAiRcaGenerator(client=fake_client, model="gpt-4o")
    report = gen.generate(evidence_bundle)
    assert report.status == "UNAVAILABLE"

    # Schema parsing failure (e.g. empty citations)
    fake_client.responses.parse.side_effect = ValueError("Schema validation error: empty citations")
    report2 = gen.generate(evidence_bundle)
    assert report2.status == "UNAVAILABLE"
