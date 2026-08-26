from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.helpers_champion import create_mock_phase1b_champion_run
from tests.test_champion import golden_case_to_feature_vector

from industrial_reliability.api import create_app
from industrial_reliability.champion import load_champion


@pytest.mark.integration
def test_http_scores_every_packaged_golden_case(tmp_path: Path) -> None:
    mock_run = create_mock_phase1b_champion_run(tmp_path)
    scorer = load_champion(mock_run.package_dir, mock_run.manifest_sha256)
    client = TestClient(create_app(scorer))

    golden_data = json.loads(
        (mock_run.package_dir / "golden-cases.json").read_text(encoding="utf-8")
    )
    for case in golden_data["cases"]:
        fv = golden_case_to_feature_vector(case, scorer)
        request_body = {
            "model_version": scorer.model_version,
            "feature_vector": json.loads(fv.model_dump_json()),
        }
        response = client.post("/v1/score", json=request_body)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["score"] == pytest.approx(case["expected_score"], abs=1e-9)
        assert body["data"]["is_anomaly"] == case["expected_is_anomaly"]
        assert len(body["data"]["evidence_vector"]) == len(case["expected_evidence"])
