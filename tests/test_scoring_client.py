from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest

from industrial_reliability.runtime_messages import (
    ErrorResponseV1,
    EvidenceValueV1,
    FeatureVectorV1,
    ScoreDecisionV1,
    ScoreResponseV1,
)
from industrial_reliability.scoring_client import (
    PermanentScoringError,
    RetryableScoringError,
    ScoringClient,
)
from tests.test_runtime_messages import _valid_feature_vector_payload

MODEL_VERSION = "champion-statistical-v1"


def _sample_feature_vector() -> FeatureVectorV1:
    return FeatureVectorV1.model_validate(_valid_feature_vector_payload())


def _make_mock_response(status_code: int, data: dict[str, Any]) -> httpx.Response:
    request = httpx.Request("POST", "http://scoring-api:8000/v1/score")
    return httpx.Response(status_code=status_code, json=data, request=request)


def _make_valid_score_response(feature: FeatureVectorV1) -> dict[str, Any]:
    decision = ScoreDecisionV1(
        message_id=uuid4(),
        replay_session_id=feature.replay_session_id,
        source_dataset_sha256=feature.source_dataset_sha256,
        contract_sha256=feature.contract_sha256,
        source_timestamp=feature.source_timestamp,
        emitted_at=datetime.now(UTC),
        decision_id=uuid4(),
        window_id=feature.window_id,
        model_version=MODEL_VERSION,
        score=0.5,
        threshold=1.0,
        is_anomaly=False,
        evidence_vector=(
            EvidenceValueV1(feature_name="tp2_mean", feature_value=1.23, robust_deviation=0.2),
        ),
    )
    return ScoreResponseV1(data=decision).model_dump(mode="json")


@pytest.mark.asyncio
async def test_client_retries_timeout_then_returns_verified_decision() -> None:
    feature = _sample_feature_vector()
    valid_resp = _make_mock_response(200, _make_valid_score_response(feature))

    call_count = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ReadTimeout("Timeout connecting to scoring API")
        return valid_resp

    transport = httpx.MockTransport(mock_handler)
    sleep_calls = []

    async def mock_sleep(d: float) -> None:
        sleep_calls.append(d)

    client = ScoringClient(
        base_url="http://scoring-api:8000",
        model_version=MODEL_VERSION,
        transport=transport,
        sleep=mock_sleep,
    )

    decision = await client.score(feature)
    assert decision.window_id == feature.window_id
    assert decision.model_version == MODEL_VERSION
    assert call_count == 2
    assert sleep_calls == [0.25]
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 404, 409, 422])
async def test_client_does_not_retry_permanent_contract_errors(status: int) -> None:
    feature = _sample_feature_vector()
    err_body = ErrorResponseV1(
        error={"code": "CONTRACT_ERROR", "message": "Schema mismatch"}
    ).model_dump(mode="json")
    err_resp = _make_mock_response(status, err_body)

    call_count = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return err_resp

    transport = httpx.MockTransport(mock_handler)
    client = ScoringClient(
        base_url="http://scoring-api:8000",
        model_version=MODEL_VERSION,
        transport=transport,
    )

    with pytest.raises(PermanentScoringError):
        await client.score(feature)
    assert call_count == 1
    await client.close()


@pytest.mark.asyncio
async def test_client_exhausts_retries_after_3_attempts() -> None:
    feature = _sample_feature_vector()
    err_resp = _make_mock_response(503, {"error": "Service unavailable"})

    call_count = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return err_resp

    transport = httpx.MockTransport(mock_handler)
    sleep_calls = []

    async def mock_sleep(d: float) -> None:
        sleep_calls.append(d)

    client = ScoringClient(
        base_url="http://scoring-api:8000",
        model_version=MODEL_VERSION,
        transport=transport,
        sleep=mock_sleep,
    )

    with pytest.raises(RetryableScoringError):
        await client.score(feature)

    assert call_count == 3
    assert sleep_calls == [0.25, 1.0]
    await client.close()


@pytest.mark.asyncio
async def test_client_rejects_model_or_window_mismatch() -> None:
    feature = _sample_feature_vector()
    payload = _make_valid_score_response(feature)
    payload["data"]["model_version"] = "wrong-model-v2"
    tampered_resp = _make_mock_response(200, payload)

    transport = httpx.MockTransport(lambda req: tampered_resp)
    client = ScoringClient(
        base_url="http://scoring-api:8000",
        model_version=MODEL_VERSION,
        transport=transport,
    )

    with pytest.raises(PermanentScoringError, match="model_version mismatch"):
        await client.score(feature)
    await client.close()
