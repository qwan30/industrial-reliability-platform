"""Shared artifact integrity verification for industrial reliability artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from industrial_reliability.phase1b_data import sha256_file


class ArtifactIntegrityError(ValueError):
    """Raised when an artifact or manifest fails cryptographic integrity checks."""


@dataclass(frozen=True, slots=True)
class PreparedArtifactIdentity:
    source_dataset_sha256: str
    contract_sha256: str
    parquet_sha256: str
    manifest_sha256: str


def load_self_hashed_manifest(path: Path) -> dict[str, Any]:
    """Load and cryptographically verify a self-hashed manifest JSON file."""
    with path.open("r", encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)

    supplied = str(data.get("manifest_sha256", ""))
    unhashed = {key: value for key, value in data.items() if key != "manifest_sha256"}
    canonical = json.dumps(unhashed, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    if supplied != actual:
        raise ArtifactIntegrityError(
            f"{path.name} manifest self-hash mismatch: expected {supplied}, got {actual}"
        )
    return data


def verify_file_sha256(path: Path, expected: str, label: str) -> str:
    """Verify that a file on disk matches the expected SHA-256 digest."""
    actual = sha256_file(path)
    if actual != expected:
        raise ArtifactIntegrityError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")
    return actual


def verify_prepared_parquet(
    path: Path,
    *,
    expected_contract_sha256: str,
    expected_source_dataset_sha256: str,
    expected_output_sha256: str,
) -> PreparedArtifactIdentity:
    manifest = load_self_hashed_manifest(path.with_name("manifest.json"))
    contract = str(manifest.get("contract_sha256", ""))
    source = str(manifest.get("archive_sha256", ""))
    declared_output = str(manifest.get("output_sha256", ""))
    if contract != expected_contract_sha256:
        raise ArtifactIntegrityError(
            f"prepared contract SHA-256 mismatch: expected {expected_contract_sha256}, got {contract}"
        )
    if source != expected_source_dataset_sha256:
        raise ArtifactIntegrityError(
            f"prepared source SHA-256 mismatch: expected {expected_source_dataset_sha256}, got {source}"
        )
    if declared_output != expected_output_sha256:
        raise ArtifactIntegrityError(
            f"expected prepared output SHA-256 {expected_output_sha256}, got {declared_output}"
        )
    parquet_sha = verify_file_sha256(path, expected_output_sha256, "telemetry.parquet")
    return PreparedArtifactIdentity(
        source_dataset_sha256=source,
        contract_sha256=contract,
        parquet_sha256=parquet_sha,
        manifest_sha256=str(manifest["manifest_sha256"]),
    )

