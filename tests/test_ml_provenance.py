from dataclasses import replace
from pathlib import Path

import pytest

from industrial_reliability.ml_provenance import (
    PromotionReceiptV1,
    RunProvenanceV1,
    canonical_dumps,
    canonical_sha256,
    load_promotion_receipt,
    load_run_provenance,
    validate_git_sha,
    validate_hex64,
    verify_promotion_receipt,
    verify_run_provenance,
    write_promotion_receipt,
    write_run_provenance,
)


def sample_run_provenance() -> RunProvenanceV1:
    return RunProvenanceV1(
        schema_version="mlflow-run-provenance-v1",
        mlflow_run_id="run-123456789abc",
        experiment_name="industrial-reliability-offline",
        lifecycle_state="candidate",
        dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        feature_schema_sha256="c" * 64,
        source_git_sha="d" * 40,
        python_version="3.12.10",
        dependency_versions={"numpy": "2.2.0", "scikit-learn": "1.6.0"},
        champion_package_sha256="e" * 64,
        alert_policy_sha256="f" * 64,
        parameters={"model_id": "statistical", "window_size": 30},
        metrics={"false_alarm_rate": 0.005, "recall": 1.0},
        artifact_sha256={"detector.joblib": "1" * 64, "golden-cases.json": "2" * 64},
        provenance_sha256="",
    ).with_computed_hash()


def sample_promotion_receipt() -> PromotionReceiptV1:
    return PromotionReceiptV1(
        schema_version="mlflow-promotion-receipt-v1",
        mlflow_run_id="run-123456789abc",
        registered_model_name="industrial-reliability-anomaly-detector",
        registered_model_version="1",
        alias="champion",
        model_version="champion-statistical-v1",
        dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        champion_package_sha256="e" * 64,
        source_git_sha="d" * 40,
        approver="reliability-engineer-lead",
        promoted_at="2026-08-25T00:00:00Z",
        receipt_sha256="",
    ).with_computed_hash()


def test_canonical_dumps_rejects_nan_and_ensures_deterministic_ordering() -> None:
    data = {"b": 1, "a": {"d": 4, "c": 3}}
    dumped = canonical_dumps(data)
    assert dumped == '{"a":{"c":3,"d":4},"b":1}'
    assert canonical_sha256(data) == canonical_sha256({"a": {"c": 3, "d": 4}, "b": 1})

    with pytest.raises(ValueError, match="NaN or Infinity"):
        canonical_dumps({"bad": float("nan")})


def test_hex_validators() -> None:
    assert validate_hex64("a" * 64) == "a" * 64
    with pytest.raises(ValueError, match="64-character lowercase hex"):
        validate_hex64("A" * 64)
    with pytest.raises(ValueError, match="64-character lowercase hex"):
        validate_hex64("a" * 63)

    assert validate_git_sha("d" * 40) == "d" * 40
    with pytest.raises(ValueError, match="40-character lowercase hex"):
        validate_git_sha("d" * 39)


def test_run_provenance_round_trip_and_tamper_rejection(tmp_path: Path) -> None:
    prov = sample_run_provenance()
    out_path = tmp_path / "run-provenance.json"
    write_run_provenance(out_path, prov)

    loaded = load_run_provenance(out_path)
    assert loaded == prov
    verify_run_provenance(loaded)

    # Tamper with one field
    tampered = replace(loaded, dataset_sha256="0" * 64)
    with pytest.raises(ValueError, match="provenance hash mismatch"):
        verify_run_provenance(tampered)


def test_promotion_receipt_round_trip_and_tamper_rejection(tmp_path: Path) -> None:
    receipt = sample_promotion_receipt()
    out_path = tmp_path / "promotion-receipt.json"
    write_promotion_receipt(out_path, receipt)

    loaded = load_promotion_receipt(out_path)
    assert loaded == receipt
    verify_promotion_receipt(loaded)

    # Tamper with approver
    tampered = replace(loaded, approver="different-approver")
    with pytest.raises(ValueError, match="receipt hash mismatch"):
        verify_promotion_receipt(tampered)


def test_promotion_receipt_rejects_empty_approver_or_wrong_alias() -> None:
    with pytest.raises(ValueError, match="approver"):
        PromotionReceiptV1(
            schema_version="mlflow-promotion-receipt-v1",
            mlflow_run_id="run-123456789abc",
            registered_model_name="industrial-reliability-anomaly-detector",
            registered_model_version="1",
            alias="champion",
            model_version="champion-statistical-v1",
            dataset_sha256="a" * 64,
            contract_sha256="b" * 64,
            champion_package_sha256="e" * 64,
            source_git_sha="d" * 40,
            approver="   ",
            promoted_at="2026-08-25T00:00:00Z",
            receipt_sha256="",
        ).with_computed_hash()

    with pytest.raises(ValueError, match="alias"):
        PromotionReceiptV1(
            schema_version="mlflow-promotion-receipt-v1",
            mlflow_run_id="run-123456789abc",
            registered_model_name="industrial-reliability-anomaly-detector",
            registered_model_version="1",
            alias="candidate",  # type: ignore[arg-type]
            model_version="champion-statistical-v1",
            dataset_sha256="a" * 64,
            contract_sha256="b" * 64,
            champion_package_sha256="e" * 64,
            source_git_sha="d" * 40,
            approver="lead",
            promoted_at="2026-08-25T00:00:00Z",
            receipt_sha256="",
        ).with_computed_hash()


def test_write_promotion_receipt_rejects_overwrite(tmp_path: Path) -> None:
    receipt = sample_promotion_receipt()
    out_path = tmp_path / "promotion-receipt.json"
    write_promotion_receipt(out_path, receipt)
    with pytest.raises(FileExistsError):
        write_promotion_receipt(out_path, receipt)


def test_schema_version_and_lifecycle_state_rejection() -> None:
    prov = sample_run_provenance()
    with pytest.raises(ValueError, match="schema_version"):
        replace(prov, schema_version="bad-version")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="lifecycle_state"):
        replace(prov, lifecycle_state="invalid-state")  # type: ignore[arg-type]

    receipt = sample_promotion_receipt()
    with pytest.raises(ValueError, match="schema_version"):
        replace(receipt, schema_version="bad-version")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="registered_model_name"):
        replace(receipt, registered_model_name="wrong-model-name")  # type: ignore[arg-type]


def test_verify_promotion_receipt_with_package_manifest() -> None:
    receipt = sample_promotion_receipt()

    class MockManifest:
        manifest_sha256 = receipt.champion_package_sha256

    verify_promotion_receipt(receipt, MockManifest())

    class MismatchedManifest:
        manifest_sha256 = "0" * 64

    with pytest.raises(ValueError, match="Package manifest SHA mismatch"):
        verify_promotion_receipt(receipt, MismatchedManifest())


def test_canonical_dumps_nested_checks() -> None:
    assert canonical_dumps([1, 2, {"a": "b"}]) == '[1,2,{"a":"b"}]'
    with pytest.raises(ValueError, match="NaN or Infinity"):
        canonical_dumps([float("inf")])
