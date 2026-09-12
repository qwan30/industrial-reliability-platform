"""Mock backend services for Industrial Reliability Platform Operator Console and 3D Virtual Lab."""

import asyncio
import json
from pathlib import Path
import sys

# Ensure current working dir is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn

from industrial_reliability.lab.api import create_app as create_lab_app
from industrial_reliability.lab.catalog import get_reference_lab_definition
from tests.test_lab_api import FakeLabStore


class EnhancedFakeLabStore(FakeLabStore):
    """Fake store with reference lab preloaded and SSE events support."""

    def __init__(self):
        super().__init__()
        ref_lab = get_reference_lab_definition()
        self.labs[ref_lab.lab_id] = {1: ref_lab}

    def events_after(self, run_id, sequence=0, limit=100):
        return ()


def make_scoring_and_console_app() -> FastAPI:
    app = FastAPI(title="Operator Console Mock API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "database": "ok"}

    @app.get("/readyz")
    async def readyz():
        return {"status": "ready", "database": "ok"}

    @app.post("/v1/replays")
    async def create_replay():
        return {
            "success": True,
            "data": {
                "replay_session_id": "rep-demo-01",
                "machine_id": "metropt3",
                "state": "RUNNING",
                "speed": 100,
                "range_start": "2020-04-18T00:00:00",
                "range_end": "2020-04-18T00:10:00",
            },
            "error": None,
        }

    @app.get("/v1/replays/{replay_session_id}/stream")
    async def stream_replay(replay_session_id: str):
        async def event_generator():
            snap = {
                "session_id": replay_session_id,
                "machine_id": "metropt3",
                "state": "RUNNING",
                "speed": 100,
                "cursor_time": "2020-04-18T00:00:00Z",
                "alerts": [],
                "scores": [],
                "telemetry": [],
            }
            yield f"event: snapshot\ndata: {json.dumps(snap)}\n\n"
            while True:
                await asyncio.sleep(2.0)
                yield ": heartbeat\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    return app


def make_lab_app() -> FastAPI:
    store = EnhancedFakeLabStore()
    return create_lab_app(store=store)


async def main():
    console_app = make_scoring_and_console_app()
    lab_app = make_lab_app()

    config_8000 = uvicorn.Config(console_app, host="127.0.0.1", port=8000, log_level="warning")
    config_8010 = uvicorn.Config(lab_app, host="127.0.0.1", port=8010, log_level="warning")

    server_8000 = uvicorn.Server(config_8000)
    server_8010 = uvicorn.Server(config_8010)

    print("Starting Mock Backends on 8000 and 8010...")
    await asyncio.gather(server_8000.serve(), server_8010.serve())


if __name__ == "__main__":
    asyncio.run(main())
