from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from tests.test_package_champion import _create_mock_feasible_phase1b_run

from industrial_reliability.api import create_app
from industrial_reliability.champion import load_champion
from industrial_reliability.package_champion import build_champion_package
from industrial_reliability.runtime_messages import (
    CoverageEvidenceV1,
    FeatureVectorV1,
)


@pytest.mark.integration
def test_http_scores_every_packaged_golden_case(tmp_path: Path) -> None:
    run_dir, feat_path = _create_mock_feasible_phase1b_run(tmp_path)
    pkg_dir = tmp_path / "pkg"
    build_result = build_champion_package(run_dir, feat_path, pkg_dir)
    scorer = load_champion(pkg_dir, build_result.manifest_sha256)
    client = TestClient(create_app(scorer))

    golden_data = json.loads((pkg_dir / "golden-cases.json").read_text(encoding="utf-8"))
    for case in golden_data["cases"]:
        w_start = datetime.fromisoformat(case["window_start"])
        w_end = datetime.fromisoformat(case["window_end"])
        fv = FeatureVectorV1(
            schema_version="feature-vector-v1",
            message_id=uuid4(),
            replay_session_id=uuid4(),
            source_dataset_sha256=scorer.source_dataset_sha256,
            contract_sha256=scorer.contract_sha256,
            source_timestamp=w_end,
            emitted_at=datetime.now(UTC),
            window_id=uuid4(),
            machine_id="compressor-01",
            window_start=w_start,
            window_end=w_end,
            feature_names=tuple(case["feature_names"]),
            feature_values=tuple(case["feature_values"]),
            coverage=CoverageEvidenceV1(
                observations_by_bin=(30, 30, 30, 30, 30, 30),
                bin_ends=(
                    w_start + (w_end - w_start) / 6 * 1,
                    w_start + (w_end - w_start) / 6 * 2,
                    w_start + (w_end - w_start) / 6 * 3,
                    w_start + (w_end - w_start) / 6 * 4,
                    w_start + (w_end - w_start) / 6 * 5,
                    w_end,
                ),
            ),
        )
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
