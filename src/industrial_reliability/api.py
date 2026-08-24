"""Stateless scoring and alert evidence APIs exposed with FastAPI."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from industrial_reliability.champion import (
    ChampionScorer,
    ScoringContractError,
    load_champion,
)
from industrial_reliability.persistence import RuntimeStore
from industrial_reliability.runtime_messages import (
    ApiErrorV1,
    ErrorResponseV1,
    ScoreDecisionV1,
    ScoreRequestV1,
    ScoreResponseV1,
)

RUNTIME_NAMESPACE = NAMESPACE_URL


def create_app(
    scorer: ChampionScorer,
    store: RuntimeStore | None = None,
) -> FastAPI:
    app = FastAPI(title="Industrial Reliability Scoring and Alert API", version="1.0")

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

    @app.get("/v1/replays/{replay_session_id}")
    def get_replay(replay_session_id: UUID) -> JSONResponse:
        if store is None:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "STORE_UNAVAILABLE",
                        "message": "Database store not configured",
                    },
                },
            )
        record = store.get_replay(replay_session_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "data": None,
                    "error": {"code": "REPLAY_NOT_FOUND", "message": "Replay session not found"},
                },
            )
        data = asdict(record)
        data["replay_session_id"] = str(data["replay_session_id"])
        data["source_timestamp"] = (
            data["source_timestamp"].isoformat() if data["source_timestamp"] else None
        )
        data["updated_at"] = data["updated_at"].isoformat() if data["updated_at"] else None
        return JSONResponse(status_code=200, content={"success": True, "data": data, "error": None})

    @app.get("/v1/replays/{replay_session_id}/alerts")
    def list_alerts(
        replay_session_id: UUID,
        after: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> JSONResponse:
        if store is None:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "STORE_UNAVAILABLE",
                        "message": "Database store not configured",
                    },
                },
            )
        alerts = store.list_alerts(replay_session_id, after=after, limit=limit)
        serialized_alerts = []
        for a in alerts:
            d = asdict(a)
            d["alert_id"] = str(d["alert_id"])
            d["replay_session_id"] = str(d["replay_session_id"])
            d["latest_decision_id"] = str(d["latest_decision_id"])
            d["first_detection"] = (
                d["first_detection"].isoformat() if d["first_detection"] else None
            )
            d["last_detection"] = d["last_detection"].isoformat() if d["last_detection"] else None
            d["resolved_at"] = d["resolved_at"].isoformat() if d["resolved_at"] else None
            serialized_alerts.append(d)
        return JSONResponse(
            status_code=200,
            content={"success": True, "data": {"alerts": serialized_alerts}, "error": None},
        )

    @app.get("/v1/alerts/{alert_id}")
    def get_alert(alert_id: UUID) -> JSONResponse:
        if store is None:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "STORE_UNAVAILABLE",
                        "message": "Database store not configured",
                    },
                },
            )
        detail = store.get_alert_detail(alert_id)
        if detail is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "data": None,
                    "error": {"code": "ALERT_NOT_FOUND", "message": "Alert not found"},
                },
            )
        d_summary = asdict(detail.alert)
        d_summary["alert_id"] = str(d_summary["alert_id"])
        d_summary["replay_session_id"] = str(d_summary["replay_session_id"])
        d_summary["latest_decision_id"] = str(d_summary["latest_decision_id"])
        d_summary["first_detection"] = (
            d_summary["first_detection"].isoformat() if d_summary["first_detection"] else None
        )
        d_summary["last_detection"] = (
            d_summary["last_detection"].isoformat() if d_summary["last_detection"] else None
        )
        d_summary["resolved_at"] = (
            d_summary["resolved_at"].isoformat() if d_summary["resolved_at"] else None
        )

        data = {
            "alert": d_summary,
            "events": detail.events,
            "evidence": detail.evidence,
            "decisions": detail.decisions,
            "rca": None,
        }
        return JSONResponse(status_code=200, content={"success": True, "data": data, "error": None})

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

    db_url = os.environ.get("DATABASE_URL")
    store = RuntimeStore(db_url) if db_url else None

    return create_app(scorer, store)
