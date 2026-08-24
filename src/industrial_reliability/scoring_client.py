"""Bounded retry client for the Phase 2 stateless Scoring API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from industrial_reliability.runtime_messages import (
    ErrorResponseV1,
    FeatureVectorV1,
    ScoreDecisionV1,
    ScoreRequestV1,
    ScoreResponseV1,
)

logger = logging.getLogger(__name__)


class PermanentScoringError(RuntimeError):
    """Raised on non-retryable contract, schema, or model identity mismatches."""


class RetryableScoringError(RuntimeError):
    """Raised on transient network, timeout, 429, or 5xx server errors."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    delays_seconds: tuple[float, float] = (0.25, 1.0)


class ScoringClient:
    def __init__(
        self,
        base_url: str,
        model_version: str,
        retry_policy: RetryPolicy = RetryPolicy(),
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_version = model_version
        self.retry_policy = retry_policy
        self.sleep = sleep
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            transport=transport,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    def _validated_decision(
        self, response: httpx.Response, feature: FeatureVectorV1
    ) -> ScoreDecisionV1:
        if response.status_code == 200:
            try:
                envelope = ScoreResponseV1.model_validate_json(response.content)
            except (ValidationError, ValueError) as err:
                raise PermanentScoringError(
                    f"Scoring API returned invalid ScoreResponseV1: {err}"
                ) from err

            decision = envelope.data
            if decision.model_version != self.model_version:
                raise PermanentScoringError(
                    f"Scoring API model_version mismatch: expected {self.model_version}, got {decision.model_version}"
                )
            if decision.window_id != feature.window_id:
                raise PermanentScoringError(
                    f"Scoring API window_id mismatch: expected {feature.window_id}, got {decision.window_id}"
                )
            if decision.replay_session_id != feature.replay_session_id:
                raise PermanentScoringError(
                    f"Scoring API replay_session_id mismatch: expected {feature.replay_session_id}, got {decision.replay_session_id}"
                )
            if decision.source_dataset_sha256 != feature.source_dataset_sha256:
                raise PermanentScoringError(
                    f"Scoring API source_dataset_sha256 mismatch: expected {feature.source_dataset_sha256}, got {decision.source_dataset_sha256}"
                )
            if decision.contract_sha256 != feature.contract_sha256:
                raise PermanentScoringError(
                    f"Scoring API contract_sha256 mismatch: expected {feature.contract_sha256}, got {decision.contract_sha256}"
                )

            return decision

        # Non-200 responses
        if response.status_code in (429, 500, 502, 503, 504):
            raise RetryableScoringError(
                f"Transient Scoring API failure (HTTP {response.status_code}): {response.text[:200]}"
            )

        # 4xx or unexpected status
        try:
            err_envelope = ErrorResponseV1.model_validate_json(response.content)
            err_msg = f"{err_envelope.error.code}: {err_envelope.error.message}"
        except Exception:
            err_msg = response.text[:200]

        raise PermanentScoringError(
            f"Permanent Scoring API error (HTTP {response.status_code}): {err_msg}"
        )

    async def score(self, feature: FeatureVectorV1) -> ScoreDecisionV1:
        request = ScoreRequestV1(
            model_version=self.model_version,
            feature_vector=feature,
        )
        content = request.model_dump_json()

        for attempt in range(self.retry_policy.attempts):
            try:
                response = await self.client.post("/v1/score", content=content)
                return self._validated_decision(response, feature)
            except RetryableScoringError as retryable_err:
                if attempt + 1 >= self.retry_policy.attempts:
                    raise retryable_err
                delay = self.retry_policy.delays_seconds[attempt]
                logger.warning(
                    "Scoring request failed (attempt %d/%d): %s. Retrying in %.2fs",
                    attempt + 1,
                    self.retry_policy.attempts,
                    retryable_err,
                    delay,
                )
                await self.sleep(delay)
            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                if attempt + 1 >= self.retry_policy.attempts:
                    raise RetryableScoringError(
                        f"Scoring API network/timeout failure: {net_err}"
                    ) from net_err
                delay = self.retry_policy.delays_seconds[attempt]
                logger.warning(
                    "Scoring network error (attempt %d/%d): %s. Retrying in %.2fs",
                    attempt + 1,
                    self.retry_policy.attempts,
                    net_err,
                    delay,
                )
                await self.sleep(delay)

        raise AssertionError("Retry loop exhausted without returning or raising")
