from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd
import psycopg
import pytest
import uvicorn
from aiokafka import AIOKafkaProducer
from tests.helpers_champion import build_research_candidate_from_mock_run
from tests.helpers_replay import make_sample_replay_command

from industrial_reliability.alert_policy import compute_policy_sha256
from industrial_reliability.alert_service import (
    AlertService,
    AlertServiceSettings,
)
from industrial_reliability.api import create_app
from industrial_reliability.champion import ChampionScorer, load_champion
from industrial_reliability.kafka_io import (
    KafkaSettings,
    encode_message,
)
from industrial_reliability.persistence import RuntimeStore
from industrial_reliability.replay import ReplaySource
from industrial_reliability.replay_service import ReplayService
from industrial_reliability.runtime_messages import (
    REPLAY_COMMANDS_TOPIC,
)
from industrial_reliability.worker import (
    StreamingWorker,
    WorkerSettings,
)


@asynccontextmanager
async def running_scoring_api(scorer: ChampionScorer) -> AsyncIterator[str]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(scorer),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        if not server.started:
            raise TimeoutError("scoring API did not start")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)


def write_prepared_manifest(
    parquet: Path,
    source_dataset_sha256: str,
    contract_sha256: str,
) -> None:
    content = parquet.read_bytes()
    manifest = {
        "archive_sha256": source_dataset_sha256,
        "contract_sha256": contract_sha256,
        "output_sha256": hashlib.sha256(content).hexdigest(),
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    parquet.with_name("manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def write_prepared_parquet(path: Path, rows: int = 400) -> Path:
    path.mkdir(parents=True)
    start = datetime(2020, 3, 1)
    frame = pd.DataFrame(
        {
            "timestamp": [start + timedelta(seconds=10 * index) for index in range(rows)],
            "tp2": [10.0] * rows,
            "tp3": [9.0] * rows,
            "h1": [9.0] * rows,
            "dv_pressure": [9.0] * rows,
            "reservoirs": [8.0] * rows,
            "oil_temperature": [80.0] * rows,
            "motor_current": [9.0] * rows,
            "comp": [index % 2 for index in range(rows)],
            "dv_electric": [0] * rows,
            "towers": [1] * rows,
            "mpg": [0] * rows,
            "lps": [0] * rows,
            "pressure_switch": [0] * rows,
            "oil_level": [0] * rows,
            "caudal_impulses": [0] * rows,
        }
    )
    target = path / "telemetry.parquet"
    frame.to_parquet(target, index=False)
    return target


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verified_telemetry_reaches_one_durable_alert(
    tmp_path: Path,
) -> None:
    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://irp:irp_password@localhost:5432/irp"
    )
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
    require_live = os.environ.get("REQUIRE_INTEGRATION_SERVICES", "").lower() in ("true", "1")

    try:
        probe_producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
        await asyncio.wait_for(probe_producer.start(), timeout=1.5)
        await probe_producer.stop()
    except Exception as exc:
        if require_live:
            raise RuntimeError(
                f"Required integration Kafka broker unavailable at {bootstrap}: {exc}"
            ) from exc
        pytest.skip(f"Kafka broker unavailable at {bootstrap}: {exc}")

    try:
        store = RuntimeStore(database_url)
        store.check_connection(timeout=1.0)
    except Exception as exc:
        if require_live:
            raise RuntimeError(
                f"Required integration PostgreSQL unavailable at {database_url}: {exc}"
            ) from exc
        pytest.skip(f"PostgreSQL unavailable at {database_url}: {exc}")

    mock = build_research_candidate_from_mock_run(tmp_path)
    scorer = load_champion(
        mock.package_dir,
        mock.manifest_sha256,
        allow_research_candidate=True,
    )

    policy_path = mock.package_dir / "alert-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["persistence_decisions"] = 2
    policy["policy_sha256"] = compute_policy_sha256(policy)
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")

    parquet = write_prepared_parquet(tmp_path / "prepared")
    write_prepared_manifest(
        parquet,
        scorer.source_dataset_sha256,
        scorer.contract_sha256,
    )
    kafka = KafkaSettings(bootstrap_servers=bootstrap, client_id=f"data-path-{uuid4()}")

    migrations_dir = Path(__file__).resolve().parents[2] / "db" / "migrations"
    if not migrations_dir.is_dir():
        migrations_dir = Path("db/migrations")
    for migration in sorted(migrations_dir.glob("*.sql")):
        store.execute_script(migration.read_text(encoding="utf-8"))

    async with running_scoring_api(scorer) as scoring_url:
        replay = ReplayService(
            kafka,
            ReplaySource(parquet, expected_contract_sha256=scorer.contract_sha256),
            enable_pacing=False,
        )
        worker = StreamingWorker(
            WorkerSettings(
                bootstrap_servers=bootstrap,
                scoring_api_url=scoring_url,
                model_version=scorer.model_version,
                source_dataset_sha256=scorer.source_dataset_sha256,
                contract_sha256=scorer.contract_sha256,
                feature_names=tuple(scorer.feature_names),
                client_id=f"worker-{uuid4()}",
                group_id=f"worker-{uuid4()}",
            )
        )
        alerts = AlertService(
            AlertServiceSettings(
                kafka=KafkaSettings(bootstrap, f"alerts-{uuid4()}"),
                database_url=database_url,
                policy_path=policy_path,
            )
        )
        replay_task = asyncio.create_task(replay.run())
        worker_task = asyncio.create_task(worker.run())
        await alerts.start()
        try:
            await asyncio.sleep(1)
            session_id = uuid4()
            command = make_sample_replay_command(
                action="START",
                session_id=session_id,
                speed=1000,
                range_start=datetime(2020, 3, 1),
                range_end=datetime(2020, 3, 1) + timedelta(hours=1),
                source_dataset_sha256=scorer.source_dataset_sha256,
                contract_sha256=scorer.contract_sha256,
            )
            producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
            await producer.start()
            try:
                await producer.send_and_wait(
                    REPLAY_COMMANDS_TOPIC,
                    value=encode_message(command),
                    key=str(session_id).encode(),
                )
            finally:
                await producer.stop()

            for _ in range(300):
                if store.count("alerts", "replay_session_id", str(session_id)) >= 1:
                    break
                await asyncio.sleep(0.2)
            else:
                raise TimeoutError("durable alert was not created")
        finally:
            await alerts.stop()
            await replay.stop()
            await worker.stop()
            for task in (replay_task, worker_task):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    assert store.count("score_decisions", "replay_session_id", str(session_id)) >= 2
    assert store.count("alerts", "replay_session_id", str(session_id)) == 1
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM alert_outbox AS outbox
            JOIN alert_events AS event ON event.message_id = outbox.message_id
            JOIN alerts AS alert ON alert.alert_id = event.alert_id
            WHERE alert.replay_session_id = %s
            """,
            (str(session_id),),
        )
        row = cursor.fetchone()
        assert row is not None and row[0] >= 1
