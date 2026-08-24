"""Stateless scoring API exposed with FastAPI."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from industrial_reliability.champion import (
    ChampionScorer,
    ScoringContractError,
    load_champion,
)
from industrial_reliability.runtime_messages import (
    ApiErrorV1,
    ErrorResponseV1,
    ScoreDecisionV1,
    ScoreRequestV1,
    ScoreResponseV1,
)

RUNTIME_NAMESPACE = NAMESPACE_URL


def create_app(scorer: ChampionScorer) -> FastAPI:
    app = FastAPI(title="Industrial Reliability Scoring API", version="1.0")

    @app.exception_handler(ScoringContractError)
    async def scoring_contract_error_handler(
        _request: Request, error: ScoringContractError
    ) -> JSONResponse:
        body = ErrorResponseV1(
            error=ApiErrorV1(code="SCORING_CONTRACT_MISMATCH", message=str(error))
        )
        return JSONResponse(status_code=409, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponseV1(
            error=ApiErrorV1(code="INVALID_REQUEST", message="request validation failed")
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"success": True, "data": {"status": "ok"}, "error": None}

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        return {"success": True, "data": {"status": "ready"}, "error": None}

    @app.post("/v1/score")
    def score(request: ScoreRequestV1) -> ScoreResponseV1:
        if request.model_version != scorer.model_version:
            raise ScoringContractError(
                f"Model version mismatch: expected {scorer.model_version}, got {request.model_version}"
            )

        feature = request.feature_vector
        result = scorer.score(feature)

        decision_id = uuid5(
            RUNTIME_NAMESPACE, f"decision:{feature.window_id}:{scorer.model_version}"
        )
        decision = ScoreDecisionV1(
            message_id=decision_id,
            replay_session_id=feature.replay_session_id,
            source_dataset_sha256=feature.source_dataset_sha256,
            contract_sha256=feature.contract_sha256,
            source_timestamp=feature.source_timestamp,
            emitted_at=datetime.now(UTC),
            decision_id=decision_id,
            window_id=feature.window_id,
            model_version=scorer.model_version,
            score=result.score,
            threshold=result.threshold,
            is_anomaly=result.is_anomaly,
            evidence_vector=result.evidence_vector,
        )
        return ScoreResponseV1(data=decision)

    return app


def create_app_from_env() -> FastAPI:
    pkg_dir_str = os.environ.get("CHAMPION_PACKAGE_DIR")
    manifest_sha = os.environ.get("CHAMPION_MANIFEST_SHA256")
    if not pkg_dir_str or not manifest_sha:
        raise ValueError(
            "CHAMPION_PACKAGE_DIR and CHAMPION_MANIFEST_SHA256 must be set in the environment"
        )
    pkg_dir = Path(pkg_dir_str).resolve()
    scorer = load_champion(pkg_dir, manifest_sha)
    return create_app(scorer)
