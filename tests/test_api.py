from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from industrial_reliability.api import create_app, create_app_from_env
from industrial_reliability.champion import load_champion
from industrial_reliability.package_champion import build_champion_package
from tests.test_champion import _make_feature_vector
from tests.test_package_champion import _create_mock_feasible_phase1b_run


@pytest.fixture
def scoring_client(tmp_path: Path) -> tuple[TestClient, dict[str, object], Path, str]:
    run_dir, feat_path = _create_mock_feasible_phase1b_run(tmp_path)
    pkg_dir = tmp_path / "pkg"
    build_result = build_champion_package(run_dir, feat_path, pkg_dir)
    scorer = load_champion(pkg_dir, build_result.manifest_sha256)
    app = create_app(scorer)
    client = TestClient(app)

    fv = _make_feature_vector(
        scorer.contract_sha256,
        scorer.source_dataset_sha256,
        scorer.feature_names,
        (1.0, 2.0),
    )
    request_payload = {
        "model_version": scorer.model_version,
        "feature_vector": json.loads(fv.model_dump_json()),
    }
    return client, request_payload, pkg_dir, build_result.manifest_sha256


def test_healthz_and_readyz(
    scoring_client: tuple[TestClient, dict[str, object], Path, str],
) -> None:
    client, _, _, _ = scoring_client
    r_health = client.get("/healthz")
    assert r_health.status_code == 200
    assert r_health.json() == {"success": True, "data": {"status": "ok"}, "error": None}

    r_ready = client.get("/readyz")
    assert r_ready.status_code == 200
    assert r_ready.json() == {"success": True, "data": {"status": "ready"}, "error": None}


def test_score_returns_versioned_decision(
    scoring_client: tuple[TestClient, dict[str, object], Path, str],
) -> None:
    client, valid_request, _, _ = scoring_client
    response = client.post("/v1/score", json=valid_request)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["schema_version"] == "score-decision-v1"
    assert body["data"]["is_anomaly"] == (body["data"]["score"] >= body["data"]["threshold"])
    assert body["data"]["window_id"] == valid_request["feature_vector"]["window_id"]
    assert body["data"]["model_version"] == valid_request["model_version"]


def test_score_identity_mismatch_is_conflict(
    scoring_client: tuple[TestClient, dict[str, object], Path, str],
) -> None:
    client, valid_request, _, _ = scoring_client
    bad_request = dict(valid_request)
    bad_request["model_version"] = "wrong-model-version"
    response = client.post("/v1/score", json=bad_request)
    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "SCORING_CONTRACT_MISMATCH"


def test_score_malformed_request_is_422(
    scoring_client: tuple[TestClient, dict[str, object], Path, str],
) -> None:
    client, _, _, _ = scoring_client
    response = client.post("/v1/score", json={"invalid": "payload"})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_create_app_from_env(
    scoring_client: tuple[TestClient, dict[str, object], Path, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, pkg_dir, manifest_sha = scoring_client
    monkeypatch.setenv("CHAMPION_PACKAGE_DIR", str(pkg_dir))
    monkeypatch.setenv("CHAMPION_MANIFEST_SHA256", manifest_sha)

    app = create_app_from_env()
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
