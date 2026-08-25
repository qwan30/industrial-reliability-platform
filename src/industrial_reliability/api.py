"""Stateless scoring, alert evidence, replay control, and SSE stream APIs exposed with FastAPI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, model_validator

from industrial_reliability.champion import (
    ChampionProvenanceVerifier,
    ChampionScorer,
    ScoringContractError,
    load_champion,
)
from industrial_reliability.console_stream import (
    ConsoleEventBroker,
    ConsoleEventV1,
)
from industrial_reliability.kafka_io import KafkaSettings, encode_message
from industrial_reliability.metrics import RuntimeMetrics, mount_api_metrics
from industrial_reliability.persistence import (
    AlertDetailRecord,
    AlertSummaryRecord,
    ReplaySessionRecord,
    RuntimeStore,
)
from industrial_reliability.rca_evidence import AlertNotFound, gather_evidence
from industrial_reliability.rca_openai import OpenAiRcaGenerator, evidence_only_report
from industrial_reliability.runtime_kafka import (
    AioKafkaCommandProducer,
)
from industrial_reliability.runtime_messages import (
    REPLAY_COMMANDS_TOPIC,
    ApiErrorV1,
    ErrorResponseV1,
    ReplayCommandV1,
    ScoreDecisionV1,
    ScoreRequestV1,
    ScoreResponseV1,
)

RUNTIME_NAMESPACE = NAMESPACE_URL
ERR_STORE_UNAVAILABLE_MSG = "Database store not configured"
_background_tasks: set[asyncio.Task[Any]] = set()


class StartReplayRequestV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    range_start: datetime
    range_end: datetime
    speed: Literal[1, 100, 1000]

    @model_validator(mode="after")
    def bounded_range(self) -> StartReplayRequestV1:
        if self.range_start >= self.range_end:
            raise ValueError("range_start must precede range_end")
        return self


class ReplayControlRequestV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    action: Literal["PAUSE", "RESUME", "STOP"]


def encode_sse(
    event: str,
    data: Any,
    event_id: str | None = None,
) -> bytes:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    if isinstance(data, str):
        lines.append(f"data: {data}")
    else:
        lines.append(f"data: {json.dumps(data, separators=(',', ':'), allow_nan=False)}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")


def _serialize_replay(record: ReplaySessionRecord) -> dict[str, Any]:
    data = asdict(record)
    data["replay_session_id"] = str(data["replay_session_id"])
    data["source_timestamp"] = (
        data["source_timestamp"].isoformat() if data["source_timestamp"] else None
    )
    data["updated_at"] = data["updated_at"].isoformat() if data["updated_at"] else None
    return data


def _serialize_alert_summary(alert: AlertSummaryRecord) -> dict[str, Any]:
    d = asdict(alert)
    d["alert_id"] = str(d["alert_id"])
    d["replay_session_id"] = str(d["replay_session_id"])
    d["latest_decision_id"] = str(d["latest_decision_id"])
    d["first_detection"] = d["first_detection"].isoformat() if d["first_detection"] else None
    d["last_detection"] = d["last_detection"].isoformat() if d["last_detection"] else None
    d["resolved_at"] = d["resolved_at"].isoformat() if d["resolved_at"] else None
    return d


def _serialize_alert_detail(detail: AlertDetailRecord) -> dict[str, Any]:
    return {
        "alert": _serialize_alert_summary(detail.alert),
        "events": detail.events,
        "evidence": detail.evidence,
        "decisions": detail.decisions,
        "rca": detail.rca,
    }


def _store_unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "STORE_UNAVAILABLE",
                "message": ERR_STORE_UNAVAILABLE_MSG,
            },
        },
    )


def _publish_command(producer: Any, topic: str, key: str, cmd: ReplayCommandV1) -> None:
    if producer is None:
        return
    if hasattr(producer, "publish_command"):
        coro = producer.publish_command(cmd)
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(coro)
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        except RuntimeError:
            asyncio.run(coro)
    else:
        payload_bytes = encode_message(cmd)
        if hasattr(producer, "send"):
            producer.send(topic, key=key.encode("utf-8"), value=payload_bytes)
        elif hasattr(producer, "produce"):
            producer.produce(topic, key=key.encode("utf-8"), value=payload_bytes)


def create_app(
    scorer: ChampionScorer,
    store: RuntimeStore | None = None,
    producer: Any = None,
    broker: ConsoleEventBroker | None = None,
    provenance_verifier: ChampionProvenanceVerifier | None = None,
    metrics: RuntimeMetrics | None = None,
    rca_generator: OpenAiRcaGenerator | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if producer is not None and hasattr(producer, "start"):
            await producer.start()
        yield
        if producer is not None and hasattr(producer, "stop"):
            await producer.stop()

    app = FastAPI(
        title="Industrial Reliability Scoring and Alert API",
        version="1.0",
        lifespan=lifespan,
    )

    if metrics is not None:
        mount_api_metrics(app, metrics)

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
    def readyz() -> JSONResponse:
        if provenance_verifier is not None:
            ok, reason = provenance_verifier.verify()
            if not ok:
                return JSONResponse(
                    status_code=503,
                    content={
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "CHAMPION_PROVENANCE_MISMATCH",
                            "message": reason or "Champion provenance verification failed",
                        },
                    },
                )
        return JSONResponse(
            status_code=200,
            content={"success": True, "data": {"status": "ready"}, "error": None},
        )

    @app.get("/v1/models/{model_version}/provenance")
    def get_model_provenance(model_version: str) -> JSONResponse:
        if model_version != scorer.model_version:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "MODEL_VERSION_NOT_FOUND",
                        "message": f"Model version {model_version} not found",
                    },
                },
            )
        if provenance_verifier is not None:
            prov_data = provenance_verifier.get_provenance_data()
            return JSONResponse(
                status_code=200,
                content={"success": True, "data": prov_data, "error": None},
            )
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "model_version": scorer.model_version,
                    "active_feature_names": list(scorer.feature_names),
                    "threshold": scorer.threshold,
                },
                "error": None,
            },
        )

    @app.post("/v1/score")
    def score(request: ScoreRequestV1) -> ScoreResponseV1:
        started = time.perf_counter()
        if request.model_version != scorer.model_version:
            if metrics is not None:
                metrics.record_score_request("invalid_model", time.perf_counter() - started)
            raise ScoringContractError(
                f"Model version mismatch: expected {scorer.model_version}, got {request.model_version}"
            )

        feature = request.feature_vector
        try:
            result = scorer.score(feature)
        except Exception:
            if metrics is not None:
                metrics.record_score_request("invalid_contract", time.perf_counter() - started)
            raise

        if metrics is not None:
            metrics.record_score_request("ok", time.perf_counter() - started)

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

    @app.post("/v1/replays", status_code=202)
    def start_replay(body: StartReplayRequestV1) -> JSONResponse:
        session_id = uuid4()
        now = datetime.now(UTC)
        ds_sha = "0" * 64
        c_sha = "0" * 64
        if hasattr(scorer, "manifest") and isinstance(scorer.manifest, dict):
            ds_sha = scorer.manifest.get("source_dataset_sha256", ds_sha)
            c_sha = scorer.manifest.get("contract_sha256", c_sha)

        cmd = ReplayCommandV1(
            schema_version="replay-command-v1",
            message_id=uuid4(),
            replay_session_id=session_id,
            source_dataset_sha256=ds_sha,
            contract_sha256=c_sha,
            source_timestamp=body.range_start,
            emitted_at=now,
            command_id=uuid4(),
            action="START",
            speed=body.speed,
            range_start=body.range_start,
            range_end=body.range_end,
        )
        _publish_command(producer, REPLAY_COMMANDS_TOPIC, str(session_id), cmd)
        return JSONResponse(
            status_code=202,
            content={
                "success": True,
                "data": {"replay_session_id": str(session_id)},
                "error": None,
            },
        )

    @app.post("/v1/replays/{replay_session_id}/commands", status_code=202)
    def control_replay(replay_session_id: UUID, body: ReplayControlRequestV1) -> JSONResponse:
        now = datetime.now(UTC)
        cmd = ReplayCommandV1(
            schema_version="replay-command-v1",
            message_id=uuid4(),
            replay_session_id=replay_session_id,
            source_dataset_sha256="0" * 64,
            contract_sha256="0" * 64,
            source_timestamp=datetime(2020, 1, 1),
            emitted_at=now,
            command_id=uuid4(),
            action=body.action,
            speed=100,
            range_start=None,
            range_end=None,
        )
        _publish_command(producer, REPLAY_COMMANDS_TOPIC, str(replay_session_id), cmd)
        return JSONResponse(
            status_code=202,
            content={"success": True, "data": {"status": "accepted"}, "error": None},
        )

    @app.get("/v1/replays/{replay_session_id}")
    def get_replay(replay_session_id: UUID) -> JSONResponse:
        if store is None:
            return _store_unavailable_response()
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
        return JSONResponse(
            status_code=200,
            content={"success": True, "data": _serialize_replay(record), "error": None},
        )

    @app.get("/v1/replays/{replay_session_id}/alerts")
    def list_alerts(
        replay_session_id: UUID,
        after: UUID | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> JSONResponse:
        if store is None:
            return _store_unavailable_response()
        alerts = store.list_alerts(replay_session_id, after=after, limit=limit)
        serialized_alerts = [_serialize_alert_summary(a) for a in alerts]
        return JSONResponse(
            status_code=200,
            content={"success": True, "data": {"alerts": serialized_alerts}, "error": None},
        )

    @app.get("/v1/alerts/{alert_id}")
    def get_alert(alert_id: UUID) -> JSONResponse:
        if store is None:
            return _store_unavailable_response()
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
        return JSONResponse(
            status_code=200,
            content={"success": True, "data": _serialize_alert_detail(detail), "error": None},
        )

    @app.post("/v1/alerts/{alert_id}/rca")
    def generate_alert_rca(alert_id: UUID) -> JSONResponse:
        if store is None:
            return _store_unavailable_response()
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
        try:
            bundle = gather_evidence(str(alert_id), store)
        except AlertNotFound:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "data": None,
                    "error": {"code": "ALERT_NOT_FOUND", "message": "Alert not found"},
                },
            )

        existing_report = store.get_rca(alert_id, bundle.bundle_sha256)
        if existing_report is not None:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "data": existing_report.model_dump(mode="json"),
                    "error": None,
                },
            )

        gen = rca_generator or OpenAiRcaGenerator.from_env()
        if gen is None:
            report = evidence_only_report(bundle, reason="provider_not_configured")
        else:
            report = gen.generate(bundle)

        if report.status == "COMPLETE":
            with contextlib.suppress(Exception):
                report = store.save_complete_rca(report)

        return JSONResponse(
            status_code=200,
            content={"success": True, "data": report.model_dump(mode="json"), "error": None},
        )

    @app.get("/v1/replays/{replay_session_id}/stream")
    async def stream_replay(
        replay_session_id: UUID,
        request: Request,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        async def event_generator() -> AsyncIterator[bytes]:
            sid_str = str(replay_session_id)
            snapshot_data: dict[str, Any] = {}
            if store is not None:
                rep = store.get_replay(replay_session_id)
                alerts = store.list_alerts(replay_session_id)
                snapshot_data = {
                    "replay": _serialize_replay(rep) if rep else None,
                    "alerts": [_serialize_alert_summary(a) for a in alerts],
                }

            if last_event_id is not None and store is not None:
                missed_events = store.events_after(sid_str, after_event_id=last_event_id)
                if not missed_events:
                    yield encode_sse("resync_required", {}, event_id=None)
                    yield encode_sse("snapshot", snapshot_data, event_id=f"snap-{uuid4()}")
                else:
                    yield encode_sse("snapshot", snapshot_data, event_id=f"snap-{uuid4()}")
                    for ev in missed_events:
                        yield encode_sse(ev.event_type, ev.payload, event_id=ev.event_id)
            else:
                yield encode_sse("snapshot", snapshot_data, event_id=f"snap-{uuid4()}")

            if broker is None:
                return

            q = await broker.subscribe(sid_str)
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(q.get(), timeout=15.0)
                        if isinstance(item, str):
                            if item == "resync_required":
                                yield encode_sse("resync_required", {}, event_id=None)
                        elif isinstance(item, ConsoleEventV1):
                            yield encode_sse(item.event_type, item.payload, event_id=item.event_id)
                    except TimeoutError:
                        yield b": heartbeat\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                await broker.unsubscribe(sid_str, q)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


def create_app_from_env() -> FastAPI:
    pkg_dir_str = os.environ.get("SCORING_PACKAGE_DIR") or os.environ.get("CHAMPION_PACKAGE_DIR")
    manifest_sha = os.environ.get("SCORING_MANIFEST_SHA256") or os.environ.get(
        "CHAMPION_MANIFEST_SHA256"
    )
    if not pkg_dir_str or not manifest_sha:
        raise ValueError(
            "SCORING_PACKAGE_DIR and SCORING_MANIFEST_SHA256 must be set in the environment"
        )
    allow_research_raw = os.environ.get("ALLOW_RESEARCH_CANDIDATE", "").strip().lower()
    if allow_research_raw not in {"", "true", "false"}:
        raise ValueError(f"invalid ALLOW_RESEARCH_CANDIDATE: {allow_research_raw}")
    allow_research = allow_research_raw == "true"

    pkg_dir = Path(pkg_dir_str).resolve()
    scorer = load_champion(pkg_dir, manifest_sha, allow_research_candidate=allow_research)

    db_url = os.environ.get("DATABASE_URL")
    store = RuntimeStore(db_url) if db_url else None

    bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "").strip()
    producer: Any = None
    if bootstrap_servers:
        settings = KafkaSettings(
            bootstrap_servers=bootstrap_servers,
            client_id=os.environ.get("KAFKA_CLIENT_ID", "irp-api-v1"),
        )
        producer = AioKafkaCommandProducer(settings)

    return create_app(scorer, store, producer=producer)
