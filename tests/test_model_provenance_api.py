from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from industrial_reliability.api import create_app
from industrial_reliability.champion import ChampionProvenanceVerifier, load_champion
from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    write_promotion_receipt,
)
from industrial_reliability.phase1b_data import sha256_file
from tests.helpers_champion import create_mock_phase1b_champion_run


def _setup_test_champion(base_dir: Path) -> tuple[Path, Path, Path]:
    mock_run = create_mock_phase1b_champion_run(base_dir)
    run_dir, feat_path, pkg_dir = (
        mock_run.run_dir,
        mock_run.features_path,
        mock_run.package_dir,
    )

    receipt = PromotionReceiptV1(
        schema_version="mlflow-promotion-receipt-v1",
        mlflow_run_id="run-mlflow-001",
        registered_model_name="industrial-reliability-anomaly-detector",
        registered_model_version="1",
        alias="champion",
        model_version="champion-statistical-v1",
        dataset_sha256="b" * 64,
        contract_sha256="a" * 64,
        champion_package_sha256=sha256_file(pkg_dir / "manifest.json"),
        source_git_sha="0" * 40,
        approver="reliability-engineer",
        promoted_at="2026-08-25T00:00:00Z",
        receipt_sha256="",
    ).with_computed_hash()
    write_promotion_receipt(pkg_dir / "promotion-receipt.json", receipt)

    return run_dir, feat_path, pkg_dir


def test_readyz_passes_when_provenance_valid(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ready"


def test_readyz_fails_503_on_missing_receipt(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    (pkg_dir / "promotion-receipt.json").unlink()

    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "CHAMPION_PROVENANCE_MISMATCH"


def test_readyz_fails_503_on_tampered_receipt(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    receipt_data = json.loads((pkg_dir / "promotion-receipt.json").read_text(encoding="utf-8"))
    receipt_data["approver"] = "malicious-actor"
    (pkg_dir / "promotion-receipt.json").write_text(json.dumps(receipt_data), encoding="utf-8")

    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "CHAMPION_PROVENANCE_MISMATCH"


def test_readyz_fails_503_on_mlflow_alias_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)

    mock_client = Mock()
    mock_mv = Mock()
    mock_mv.run_id = "different-run-id"
    mock_client.get_model_version_by_alias.return_value = mock_mv

    verifier = ChampionProvenanceVerifier(
        package_dir=pkg_dir,
        tracking_uri="http://127.0.0.1:5000",
        mlflow_client=mock_client,
    )

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "CHAMPION_PROVENANCE_MISMATCH"


def test_get_model_provenance_endpoint(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get(f"/v1/models/{scorer.model_version}/provenance")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "manifest" in data
    assert "receipt" in data
    assert data["manifest"]["model_version"] == "champion-statistical-v1"

    # Test unknown version returns 404
    resp_404 = client.get("/v1/models/unknown-version-v9/provenance")
    assert resp_404.status_code == 404
    assert resp_404.json()["error"]["code"] == "MODEL_VERSION_NOT_FOUND"


def test_get_model_provenance_scrubs_secrets(tmp_path: Path) -> None:
    _, _, pkg_dir = _setup_test_champion(tmp_path)
    manifest_sha = sha256_file(pkg_dir / "manifest.json")
    scorer = load_champion(pkg_dir, manifest_sha)
    verifier = ChampionProvenanceVerifier(package_dir=pkg_dir)

    app = create_app(scorer=scorer, provenance_verifier=verifier)
    client = TestClient(app)

    resp = client.get(f"/v1/models/{scorer.model_version}/provenance")
    assert resp.status_code == 200
    raw_text = resp.text.lower()
    for sensitive_keyword in ["password", "secret", "token", "postgres://", "api_key"]:
        assert sensitive_keyword not in raw_text
