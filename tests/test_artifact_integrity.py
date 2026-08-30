from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from industrial_reliability.artifact_integrity import (
    ArtifactIntegrityError,
    PreparedArtifactIdentity,
    load_self_hashed_manifest,
    verify_file_sha256,
    verify_prepared_parquet,
)


def _create_self_hashed_manifest_file(path: Path, payload: dict) -> dict:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    manifest_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    full_manifest = {**payload, "manifest_sha256": manifest_sha256}
    path.write_text(json.dumps(full_manifest, indent=2), encoding="utf-8")
    return full_manifest


def test_load_self_hashed_manifest_success(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    payload = {
        "archive_sha256": "1111" * 16,
        "contract_sha256": "2222" * 16,
        "output_sha256": "3333" * 16,
    }
    expected_data = _create_self_hashed_manifest_file(manifest_path, payload)

    loaded = load_self_hashed_manifest(manifest_path)
    assert loaded == expected_data
    assert loaded["manifest_sha256"] == expected_data["manifest_sha256"]


def test_verify_file_sha256_success_and_failure(tmp_path: Path) -> None:
    sample_file = tmp_path / "sample.bin"
    content = b"industrial reliability integrity payload"
    sample_file.write_bytes(content)
    expected_sha = hashlib.sha256(content).hexdigest()

    result = verify_file_sha256(sample_file, expected_sha, "sample.bin")
    assert result == expected_sha

    wrong_sha = "0" * 64
    with pytest.raises(
        ArtifactIntegrityError,
        match=f"sample.bin SHA-256 mismatch: expected {wrong_sha}, got {expected_sha}",
    ):
        verify_file_sha256(sample_file, wrong_sha, "sample.bin")


def test_manifest_metadata_tamper_fails(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    payload = {
        "archive_sha256": "1111" * 16,
        "contract_sha256": "2222" * 16,
        "output_sha256": "3333" * 16,
    }
    manifest_data = _create_self_hashed_manifest_file(manifest_path, payload)

    # Tamper with metadata without updating manifest_sha256
    manifest_data["contract_sha256"] = "9999" * 16
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    with pytest.raises(
        ArtifactIntegrityError,
        match=r"manifest\.json manifest self-hash mismatch: expected [a-f0-9]{64}, got [a-f0-9]{64}",
    ):
        load_self_hashed_manifest(manifest_path)


def test_contract_sha256_mismatch_fails(tmp_path: Path) -> None:
    output_dir = tmp_path / "prepared"
    output_dir.mkdir()
    parquet_path = output_dir / "telemetry.parquet"
    parquet_path.write_bytes(b"dummy parquet bytes")
    parquet_sha = hashlib.sha256(b"dummy parquet bytes").hexdigest()

    actual_contract_sha = "aaaa" * 16
    expected_contract_sha = "bbbb" * 16

    payload = {
        "archive_sha256": "1111" * 16,
        "contract_sha256": actual_contract_sha,
        "output_sha256": parquet_sha,
    }
    _create_self_hashed_manifest_file(output_dir / "manifest.json", payload)

    with pytest.raises(
        ArtifactIntegrityError,
        match=f"prepared contract SHA-256 mismatch: expected {expected_contract_sha}, got {actual_contract_sha}",
    ):
        verify_prepared_parquet(parquet_path, expected_contract_sha)


def test_verified_prepared_parquet_rejects_byte_tamper(tmp_path: Path) -> None:
    output_dir = tmp_path / "prepared"
    output_dir.mkdir()
    parquet_path = output_dir / "telemetry.parquet"
    parquet_content = b"original parquet content 12345"
    parquet_path.write_bytes(parquet_content)
    parquet_sha = hashlib.sha256(parquet_content).hexdigest()

    contract_sha = "cccc" * 16
    archive_sha = "dddd" * 16
    payload = {
        "archive_sha256": archive_sha,
        "contract_sha256": contract_sha,
        "output_sha256": parquet_sha,
    }
    manifest_data = _create_self_hashed_manifest_file(output_dir / "manifest.json", payload)

    # Verify initial valid state
    identity = verify_prepared_parquet(parquet_path, contract_sha)
    assert isinstance(identity, PreparedArtifactIdentity)
    assert identity.source_dataset_sha256 == archive_sha
    assert identity.contract_sha256 == contract_sha
    assert identity.parquet_sha256 == parquet_sha
    assert identity.manifest_sha256 == manifest_data["manifest_sha256"]

    # Tamper a single byte in the parquet file
    tampered_content = b"original parquet content 1234X"
    parquet_path.write_bytes(tampered_content)
    tampered_sha = hashlib.sha256(tampered_content).hexdigest()

    with pytest.raises(
        ArtifactIntegrityError,
        match=f"telemetry.parquet SHA-256 mismatch: expected {parquet_sha}, got {tampered_sha}",
    ):
        verify_prepared_parquet(parquet_path, contract_sha)
