"""FastAPI application for Virtual Lab v2 API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from industrial_reliability.lab.catalog import (
    clone_lab_definition,
    get_catalog,
    get_reference_lab_definition,
)
from industrial_reliability.lab.contracts import (
    CommandReceipt,
    CommandRequest,
    LabDefinition,
    LabValidationResult,
    RunSpec,
    validate_lab,
)
from industrial_reliability.lab.store import (
    CommandIdentityConflictError,
    CommandRevisionConflictError,
    InvalidRunStateError,
    LabNotFoundError,
    LabNotRunnableError,
    LabRevisionConflictError,
    LabStore,
    RunNotFoundError,
)

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Resolve database URL with fallback precedence."""
    return (
        os.environ.get("LAB_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql://irp:irp_password@127.0.0.1:5432/irp"
    )


def get_asset_manifest_path() -> Path:
    """Find catalog.json manifest path."""
    env_path = os.environ.get("LAB_ASSET_MANIFEST")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    # Check default repo locations
    local_path = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "operator-console"
        / "public"
        / "lab-assets"
        / "catalog.json"
    )
    if local_path.is_file():
        return local_path
    docker_path = Path("/app/lab-assets/catalog.json")
    if docker_path.is_file():
        return docker_path
    return local_path


# Envelope helpers
def success_response(data: Any, status_code: int = status.HTTP_200_OK) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": True, "data": data, "error": None},
    )


def error_response(
    code: str, message: str, details: Any = None, status_code: int = status.HTTP_400_BAD_REQUEST
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "error": {"code": code, "message": message, "details": details},
        },
    )


class CreateLabRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    template: Literal["REFERENCE", "BLANK"] = "REFERENCE"


class UpdateLabRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    definition: LabDefinition


class ValidateLabRequest(BaseModel):
    revision: int = Field(ge=1)


class ForkRunRequest(BaseModel):
    checkpoint_tick: int = Field(ge=0)
    reset: bool = False
    seed: int | None = None


def create_app(pool: ConnectionPool | None = None, store: Any | None = None) -> FastAPI:
    """Application factory for Virtual Lab v2 API."""
    db_pool = pool
    custom_store = store

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal db_pool
        if custom_store is not None:
            app.state.pool = db_pool
            app.state.store = custom_store
            yield
            return

        if db_pool is None:
            dsn = get_database_url()
            db_pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=8, open=False)
            db_pool.open()
        app.state.pool = db_pool
        app.state.store = LabStore(db_pool)
        yield
        if db_pool:
            db_pool.close()

    app = FastAPI(
        title="Industrial Reliability Virtual Lab API", version="2.0.0", lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/v2/healthz")
    async def healthz() -> dict[str, Any]:
        """Liveness probe: returns 200 without checking external database."""
        return {"success": True, "data": {"status": "HEALTHY"}, "error": None}

    @app.get("/v2/readyz")
    async def readyz(request: Request) -> JSONResponse:
        """Readiness probe checking DB and Worker heartbeat."""
        store_pool: ConnectionPool = request.app.state.pool
        db_healthy = False
        worker_healthy = False
        kafka_healthy = False

        try:
            with (
                store_pool.connection(timeout=2.0) as conn,
                conn.cursor(row_factory=dict_row) as cur,
            ):
                cur.execute("SELECT 1")
                db_healthy = True

                # Check worker heartbeat within 5s
                cur.execute(
                    """
                    SELECT heartbeat_at, kafka_connected
                    FROM lab_worker_health
                    ORDER BY heartbeat_at DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if row:
                    hb = row["heartbeat_at"]
                    age = (datetime.now(UTC) - hb).total_seconds()
                    if age <= 5.0:
                        worker_healthy = True
                        kafka_healthy = bool(row["kafka_connected"])
        except Exception as e:
            logger.warning("Readiness probe DB connection failure: %s", e)
            return error_response(
                code="DEPENDENCY_UNAVAILABLE",
                message="Database unreachable",
                details={
                    "database": "UNAVAILABLE",
                    "worker": "UNKNOWN",
                    "kafka": "UNKNOWN",
                },
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        deps = {
            "database": "HEALTHY" if db_healthy else "UNAVAILABLE",
            "worker": "HEALTHY" if worker_healthy else "UNAVAILABLE",
            "kafka": "HEALTHY" if kafka_healthy else "UNAVAILABLE",
        }

        if db_healthy and worker_healthy and kafka_healthy:
            return success_response(deps, status_code=status.HTTP_200_OK)

        return error_response(
            code="NOT_READY",
            message="One or more dependencies are not ready",
            details=deps,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @app.get("/v2/catalog")
    async def get_lab_catalog() -> JSONResponse:
        """Get equipment catalog and asset manifest."""
        cat = get_catalog()
        manifest_path = get_asset_manifest_path()
        manifest_data: dict[str, Any] = {}
        if manifest_path.is_file():
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Could not read asset manifest: %s", e)

        return success_response({**cat, "manifest": manifest_data})

    @app.get("/v2/templates/reference")
    async def get_reference_template() -> JSONResponse:
        """Get the read-only reference lab template definition."""
        ref = get_reference_lab_definition()
        return success_response(ref.model_dump(mode="json"))

    @app.get("/v2/labs")
    async def list_labs(
        request: Request, after: UUID | None = None, limit: int = Query(default=50, ge=1, le=100)
    ) -> JSONResponse:
        """List lab definitions with pagination."""
        store: LabStore = request.app.state.store
        labs = store.list_labs(after=after, limit=limit)
        return success_response(labs)

    @app.post("/v2/labs")
    async def create_lab(request: Request, payload: CreateLabRequest) -> JSONResponse:
        """Create a new lab definition from template (REFERENCE or BLANK)."""
        store: LabStore = request.app.state.store
        new_id = uuid4()
        if payload.template == "REFERENCE":
            ref = get_reference_lab_definition()
            lab_def = clone_lab_definition(ref, new_id, payload.name)
        else:
            lab_def = LabDefinition(
                schema_version="lab-definition-v1",
                lab_id=new_id,
                revision=1,
                name=payload.name,
                assets=(),
                pipes=(),
                sensors=(),
                scene_revision="scene-v1",
            )

        saved = store.save_lab(lab_def, expected_revision=1)
        return success_response(saved.model_dump(mode="json"), status_code=status.HTTP_201_CREATED)

    @app.get("/v2/labs/{lab_id}")
    async def get_lab(request: Request, lab_id: UUID) -> JSONResponse:
        """Get latest definition for a lab."""
        store: LabStore = request.app.state.store
        definition = store.get_lab(lab_id)
        if not definition:
            return error_response(
                "LAB_NOT_FOUND", f"Lab {lab_id} not found", status_code=status.HTTP_404_NOT_FOUND
            )
        return success_response(definition.model_dump(mode="json"))

    @app.put("/v2/labs/{lab_id}")
    async def update_lab(request: Request, lab_id: UUID, payload: UpdateLabRequest) -> JSONResponse:
        """Update lab definition with optimistic revision check."""
        store: LabStore = request.app.state.store
        if payload.definition.lab_id != lab_id:
            return error_response(
                "ID_MISMATCH",
                f"Payload lab_id {payload.definition.lab_id} does not match path {lab_id}",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            saved = store.save_lab(payload.definition, expected_revision=payload.expected_revision)
            return success_response(saved.model_dump(mode="json"))
        except LabRevisionConflictError as e:
            return error_response(
                "LAB_REVISION_CONFLICT", str(e), status_code=status.HTTP_409_CONFLICT
            )

    @app.post("/v2/labs/{lab_id}/validate")
    async def validate_lab_revision(
        request: Request, lab_id: UUID, payload: ValidateLabRequest
    ) -> JSONResponse:
        """Validate a saved lab revision for run eligibility."""
        store: LabStore = request.app.state.store
        definition = store.get_lab(lab_id, revision=payload.revision)
        if not definition:
            return error_response(
                "LAB_NOT_FOUND",
                f"Lab {lab_id} rev {payload.revision} not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        result: LabValidationResult = validate_lab(definition)
        return success_response(result.model_dump(mode="json"))

    @app.post("/v2/runs")
    async def create_run(request: Request, spec: RunSpec) -> JSONResponse:
        """Create a new simulation run from RunSpec."""
        store: LabStore = request.app.state.store
        try:
            run = store.start_run(spec)
            return success_response(
                {
                    "run_id": str(run.run_id),
                    "status": run.status,
                    "snapshot_url": f"/v2/runs/{run.run_id}",
                    "stream_url": f"/v2/runs/{run.run_id}/stream",
                },
                status_code=status.HTTP_201_CREATED,
            )
        except LabNotFoundError as e:
            return error_response("LAB_NOT_FOUND", str(e), status_code=status.HTTP_404_NOT_FOUND)
        except LabNotRunnableError as e:
            return error_response("LAB_NOT_RUNNABLE", str(e), status_code=status.HTTP_409_CONFLICT)

    @app.get("/v2/runs/{run_id}")
    async def get_run_snapshot(request: Request, run_id: UUID) -> JSONResponse:
        """Get latest committed snapshot for a run."""
        store: LabStore = request.app.state.store
        snapshot = store.get_snapshot(run_id)
        if not snapshot:
            return error_response(
                "RUN_NOT_FOUND", f"Run {run_id} not found", status_code=status.HTTP_404_NOT_FOUND
            )
        return success_response(snapshot.model_dump(mode="json"))

    @app.post("/v2/runs/{run_id}/commands")
    async def submit_command(
        request: Request, run_id: UUID, command: CommandRequest
    ) -> JSONResponse:
        """Submit an operational or lifecycle command."""
        store: LabStore = request.app.state.store
        try:
            receipt: CommandReceipt = store.submit_command(run_id, command)
            return success_response(
                receipt.model_dump(mode="json"), status_code=status.HTTP_202_ACCEPTED
            )
        except RunNotFoundError as e:
            return error_response("RUN_NOT_FOUND", str(e), status_code=status.HTTP_404_NOT_FOUND)
        except InvalidRunStateError as e:
            return error_response("INVALID_RUN_STATE", str(e), status_code=status.HTTP_409_CONFLICT)
        except CommandRevisionConflictError as e:
            return error_response(
                "CONTROL_REVISION_CONFLICT", str(e), status_code=status.HTTP_409_CONFLICT
            )
        except CommandIdentityConflictError as e:
            return error_response(
                "COMMAND_IDENTITY_CONFLICT", str(e), status_code=status.HTTP_409_CONFLICT
            )

    @app.get("/v2/runs/{run_id}/history")
    async def get_run_history(
        request: Request,
        run_id: UUID,
        from_tick: int = Query(default=0, ge=0),
        to_tick: int | None = Query(default=None, ge=0),
        limit: int = Query(default=300, ge=1, le=1000),
    ) -> JSONResponse:
        """Get 1Hz historical frames for investigation."""
        store: LabStore = request.app.state.store
        run = store.get_run(run_id)
        if not run:
            return error_response(
                "RUN_NOT_FOUND", f"Run {run_id} not found", status_code=status.HTTP_404_NOT_FOUND
            )
        frames = store.get_history(run_id, from_tick=from_tick, to_tick=to_tick, limit=limit)
        return success_response(frames)

    @app.get("/v2/runs/{run_id}/stream")
    async def stream_run(
        request: Request,
        run_id: UUID,
        after_sequence: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        """Server-Sent Events stream for run state and durable events."""
        store: LabStore = request.app.state.store
        run = store.get_run(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

        last_seen_seq = after_sequence
        last_event_id_hdr = request.headers.get("Last-Event-ID")
        if last_event_id_hdr:
            try:
                # Format: run_id:sequence
                parts = last_event_id_hdr.split(":")
                if len(parts) == 2 and parts[0] == str(run_id):
                    last_seen_seq = max(last_seen_seq, int(parts[1]))
            except ValueError:
                pass

        async def event_generator() -> AsyncIterator[str]:
            nonlocal last_seen_seq
            # Emit initial snapshot
            initial_snap = store.get_snapshot(run_id)
            if initial_snap:
                yield f"event: snapshot\ndata: {json.dumps(initial_snap.model_dump(mode='json'))}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                # Fetch pending events
                events = store.events_after(run_id, sequence=last_seen_seq, limit=100)
                for ev in events:
                    last_seen_seq = ev.sequence
                    durable_id = f"{run_id}:{ev.sequence}"
                    yield (
                        f"id: {durable_id}\n"
                        f"event: {ev.kind.lower()}\n"
                        f"data: {json.dumps(ev.model_dump(mode='json'))}\n\n"
                    )

                # Send heartbeat
                yield ": heartbeat\n\n"
                await asyncio.sleep(1.0)

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
    """Default entrypoint factory loading environment configuration."""
    return create_app()
