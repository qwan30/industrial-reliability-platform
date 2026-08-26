from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from industrial_reliability.api import create_app
from industrial_reliability.champion import load_champion
from industrial_reliability.persistence import (
    AlertDetailRecord,
    AlertSummaryRecord,
    ReplaySessionRecord,
    RuntimeStore,
)
from tests.helpers_champion import create_mock_phase1b_champion_run


@pytest.fixture
def test_client(tmp_path: Path) -> tuple[TestClient, MagicMock]:
    mock_run = create_mock_phase1b_champion_run(tmp_path)
    scorer = load_champion(mock_run.package_dir, mock_run.manifest_sha256)

    mock_store = MagicMock(spec=RuntimeStore)
    app = create_app(scorer=scorer, store=mock_store)
    client = TestClient(app)
    return client, mock_store


def test_get_replay_found_and_not_found(test_client: tuple[TestClient, MagicMock]) -> None:
    client, mock_store = test_client
    session_id = uuid4()

    # Found
    mock_store.get_replay.return_value = ReplaySessionRecord(
        replay_session_id=session_id,
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        model_version="champion-statistical-v1",
        state="COMPLETED",
        last_sequence=100,
        source_timestamp=datetime(2020, 3, 1, 0, 0),
        error_code=None,
        updated_at=datetime.now(UTC),
    )
    resp = client.get(f"/v1/replays/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["replay_session_id"] == str(session_id)

    # Not found
    mock_store.get_replay.return_value = None
    resp_missing = client.get(f"/v1/replays/{uuid4()}")
    assert resp_missing.status_code == 404
    assert resp_missing.json()["error"]["code"] == "REPLAY_NOT_FOUND"


def test_list_replay_alerts_with_pagination(test_client: tuple[TestClient, MagicMock]) -> None:
    client, mock_store = test_client
    session_id = uuid4()
    alert_id = uuid4()

    mock_store.list_alerts.return_value = [
        AlertSummaryRecord(
            alert_id=alert_id,
            replay_session_id=session_id,
            machine_id="metropt3",
            state="OPEN",
            first_detection=datetime(2020, 4, 18, 0, 0),
            last_detection=datetime(2020, 4, 18, 0, 5),
            resolved_at=None,
            latest_decision_id=uuid4(),
            policy_sha256="d" * 64,
        )
    ]

    resp = client.get(f"/v1/replays/{session_id}/alerts?limit=25")
    assert resp.status_code == 200
    assert len(resp.json()["data"]["alerts"]) == 1
    assert resp.json()["data"]["alerts"][0]["alert_id"] == str(alert_id)


def test_get_alert_detail_found_and_not_found(test_client: tuple[TestClient, MagicMock]) -> None:
    client, mock_store = test_client
    alert_id = uuid4()
    session_id = uuid4()

    summary = AlertSummaryRecord(
        alert_id=alert_id,
        replay_session_id=session_id,
        machine_id="metropt3",
        state="OPEN",
        first_detection=datetime(2020, 4, 18, 0, 0),
        last_detection=datetime(2020, 4, 18, 0, 5),
        resolved_at=None,
        latest_decision_id=uuid4(),
        policy_sha256="d" * 64,
    )
    mock_store.get_alert_detail.return_value = AlertDetailRecord(
        alert=summary,
        events=[{"action": "OPENED"}],
        evidence=[{"feature_deviations": []}],
        decisions=[{"score": 1.5}],
        rca=None,
    )

    resp = client.get(f"/v1/alerts/{alert_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["alert"]["alert_id"] == str(alert_id)
    assert resp.json()["data"]["rca"] is None

    # Not found
    mock_store.get_alert_detail.return_value = None
    resp_missing = client.get(f"/v1/alerts/{uuid4()}")
    assert resp_missing.status_code == 404
    assert resp_missing.json()["error"]["code"] == "ALERT_NOT_FOUND"
