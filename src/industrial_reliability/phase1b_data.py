"""Data preparation and fail-closed validation for the MetroPT-3 UCI archive."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from industrial_reliability.phase1b_contracts import PHASE1B, Phase1BContract, phase1b_contract_manifest


class MetroPT3ContractError(ValueError):
    """Raised when the input archive or data violates the frozen contract."""


@dataclass(frozen=True, slots=True)
class MetroPT3PreparationManifest:
    archive_sha256: str
    contract_sha256: str
    output_sha256: str
    normalized_rows: int
    canonical_columns: tuple[str, ...]
    identical_duplicates_removed: int
    first_timestamp: datetime
    last_timestamp: datetime
    manifest_sha256: str


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _resolve_path(base_dir: Path, filename: str) -> Path:
    base = base_dir.resolve()
    target = (base / filename).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"Path traversal detected: {filename}")
    return target


def _validate_and_publish(
    frame: pd.DataFrame,
    archive: Path,
    output_dir: Path,
    contract: Phase1BContract,
) -> MetroPT3PreparationManifest:
    if tuple(frame.columns) != contract.source_columns:
        raise MetroPT3ContractError(
            f"source header mismatch: expected {contract.source_columns}, got {tuple(frame.columns)}"
        )

    # Validate index column
    index_col = frame.columns[0]
    expected_indices = np.arange(len(frame))
    if not np.array_equal(frame[index_col].to_numpy(), expected_indices):
        raise MetroPT3ContractError("source index column is not contiguous 0..N-1")

    # Rename map from source to canonical
    rename_map = {
        "timestamp": "timestamp",
        "TP2": "tp2",
        "TP3": "tp3",
        "H1": "h1",
        "DV_pressure": "dv_pressure",
        "Reservoirs": "reservoirs",
        "Oil_temperature": "oil_temperature",
        "Motor_current": "motor_current",
        "COMP": "comp",
        "DV_eletric": "dv_electric",
        "Towers": "towers",
        "MPG": "mpg",
        "LPS": "lps",
        "Pressure_switch": "pressure_switch",
        "Oil_level": "oil_level",
        "Caudal_impulses": "caudal_impulses",
    }

    raw_data = frame.drop(columns=[index_col]).rename(columns=rename_map)
    if tuple(raw_data.columns) != contract.canonical_columns:
        raise MetroPT3ContractError("canonical columns mismatch")

    # Parse timestamps as naive
    try:
        timestamps = pd.to_datetime(raw_data["timestamp"], format="%Y-%m-%d %H:%M:%S", utc=False)
    except Exception as exc:
        raise MetroPT3ContractError(f"unparseable timestamps: {exc}") from exc

    raw_data["timestamp"] = timestamps

    # Check for NaN / non-finite in analog columns
    for col in contract.analog_columns:
        values = raw_data[col].to_numpy()
        if not np.all(np.isfinite(values)):
            raise MetroPT3ContractError(f"non-finite values in analog column {col}")

    # Check digital columns are binary 0/1 or bool
    for col in contract.digital_columns:
        values = raw_data[col].to_numpy()
        unique = np.unique(values)
        if not np.all(np.isin(unique, [0, 1, 0.0, 1.0, False, True])):
            raise MetroPT3ContractError(f"digital column {col} contains non-binary values: {unique}")

    # Handle duplicates
    dup_mask = raw_data.duplicated(subset=["timestamp"], keep=False)
    identical_duplicates_removed = 0
    if dup_mask.any():
        # Check if all duplicated timestamps are identical across all columns
        full_dup = raw_data.duplicated(keep="first")
        subset_dup = raw_data.duplicated(subset=["timestamp"], keep="first")
        if not full_dup[dup_mask].equals(subset_dup[dup_mask]):
            raise MetroPT3ContractError("conflicting duplicate timestamps detected")
        
        initial_len = len(raw_data)
        raw_data = raw_data.drop_duplicates(keep="first").reset_index(drop=True)
        identical_duplicates_removed = initial_len - len(raw_data)

    # Check strictly increasing timestamp
    ts_array = raw_data["timestamp"].to_numpy()
    if len(ts_array) > 1 and not np.all(ts_array[1:] > ts_array[:-1]):
        raise MetroPT3ContractError("timestamps are not strictly increasing")

    # Check row count
    if len(raw_data) != contract.expected_rows:
        raise MetroPT3ContractError(
            f"normalized row count mismatch: expected {contract.expected_rows}, got {len(raw_data)}"
        )

    # Atomic write to output_dir
    temp_output = output_dir.parent / f"{output_dir.name}_temp_{int(datetime.now().timestamp())}"
    temp_output.mkdir(parents=True, exist_ok=True)

    try:
        parquet_path = _resolve_path(temp_output, "telemetry.parquet")
        table = pa.Table.from_pandas(raw_data, preserve_index=False)
        pq.write_table(table, parquet_path, compression="snappy")
        output_sha256 = sha256_file(parquet_path)

        contract_manifest = phase1b_contract_manifest()
        first_ts = raw_data["timestamp"].iloc[0].to_pydatetime()
        last_ts = raw_data["timestamp"].iloc[-1].to_pydatetime()

        manifest_data = {
            "archive_sha256": sha256_file(archive),
            "contract_sha256": contract_manifest["contract_sha256"],
            "output_sha256": output_sha256,
            "normalized_rows": len(raw_data),
            "canonical_columns": list(contract.canonical_columns),
            "identical_duplicates_removed": identical_duplicates_removed,
            "first_timestamp": first_ts.isoformat(),
            "last_timestamp": last_ts.isoformat(),
        }

        canonical_json = json.dumps(manifest_data, sort_keys=True, separators=(",", ":"))
        manifest_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        manifest_data["manifest_sha256"] = manifest_sha256

        manifest_path = _resolve_path(temp_output, "manifest.json")
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        temp_output.rename(output_dir)
    except Exception:
        if temp_output.exists():
            shutil.rmtree(temp_output)
        raise

    return MetroPT3PreparationManifest(
        archive_sha256=manifest_data["archive_sha256"],
        contract_sha256=manifest_data["contract_sha256"],
        output_sha256=output_sha256,
        normalized_rows=len(raw_data),
        canonical_columns=contract.canonical_columns,
        identical_duplicates_removed=identical_duplicates_removed,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        manifest_sha256=manifest_sha256,
    )


def prepare_metropt3(
    archive: Path,
    output_dir: Path,
    contract: Phase1BContract = PHASE1B,
) -> MetroPT3PreparationManifest:
    if output_dir.exists():
        raise FileExistsError(f"destination already exists: {output_dir}")
    if not archive.exists():
        raise FileNotFoundError(f"archive not found: {archive}")
    if sha256_file(archive) != contract.archive_sha256:
        raise MetroPT3ContractError("archive SHA-256 does not match the frozen contract")
    if contract.license != "CC BY 4.0":
        raise MetroPT3ContractError(f"license does not match the frozen contract: {contract.license}")
    if contract.source_doi != "10.24432/C5VW3R":
        raise MetroPT3ContractError(f"DOI does not match the frozen contract: {contract.source_doi}")

    with ZipFile(archive) as bundle:
        members = tuple(item.filename for item in bundle.infolist() if not item.is_dir())
        if members != (contract.csv_member,):
            raise MetroPT3ContractError(f"CSV member mismatch: {members}")
        if Path(contract.csv_member).name != contract.csv_member:
            raise MetroPT3ContractError("CSV member must not escape the archive root")
        with bundle.open(contract.csv_member) as source:
            frame = pd.read_csv(source)

    return _validate_and_publish(frame, archive, output_dir, contract)
