"""Fail-closed source ingestion, verification, and preparation for Phase 1B MetroPT-3."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from industrial_reliability.phase1b_contracts import (
    PHASE1B,
    Phase1BContract,
    phase1b_contract_manifest,
    validate_analog_value,
)


class MetroPT3ContractError(ValueError):
    """Raised when source identity, structure, or content violates the frozen contract."""


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
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"File not found: {resolved}")
    hasher = hashlib.sha256()
    with resolved.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _resolve_path(base_dir: Path, filename: str) -> Path:
    base = base_dir.resolve()
    target = (base / filename).resolve()
    if target.parent != base:
        raise ValueError(f"Path traversal detected: {filename}")
    return target


RENAME_MAP = {
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


def _validate_source_structure(frame: pd.DataFrame, contract: Phase1BContract) -> pd.DataFrame:
    if tuple(frame.columns) != contract.source_columns:
        raise MetroPT3ContractError(
            f"source header mismatch: expected {contract.source_columns}, got {tuple(frame.columns)}"
        )

    index_col = frame.columns[0]
    idx_series = frame[index_col]
    if not (idx_series.is_monotonic_increasing and idx_series.is_unique):
        raise MetroPT3ContractError("source index column is not monotonic increasing and unique")

    raw_data = frame.drop(columns=[index_col]).rename(columns=RENAME_MAP)
    if tuple(raw_data.columns) != contract.canonical_columns:
        raise MetroPT3ContractError("canonical columns mismatch")

    try:
        raw_data["timestamp"] = pd.to_datetime(
            raw_data["timestamp"], format="%Y-%m-%d %H:%M:%S", utc=False
        )
    except Exception as exc:
        raise MetroPT3ContractError(f"unparseable timestamps: {exc}") from exc

    return raw_data


def _validate_telemetry_values(raw_data: pd.DataFrame, contract: Phase1BContract) -> None:
    for col in contract.analog_columns:
        values = raw_data[col].to_numpy(dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise MetroPT3ContractError(f"non-finite values in analog column {col}")
        if len(values) > 0:
            min_val = float(np.min(values))
            max_val = float(np.max(values))
            try:
                validate_analog_value(col, min_val)
                validate_analog_value(col, max_val)
            except ValueError as exc:
                raise MetroPT3ContractError(str(exc)) from exc

    for col in contract.digital_columns:
        values = raw_data[col].to_numpy()
        unique = np.unique(values)
        if not np.all(np.isin(unique, [0, 1, 0.0, 1.0, False, True])):
            raise MetroPT3ContractError(
                f"digital column {col} contains non-binary values: {unique}"
            )


def _process_duplicates_and_ordering(
    raw_data: pd.DataFrame, contract: Phase1BContract
) -> tuple[pd.DataFrame, int]:
    dup_mask = raw_data.duplicated(subset=["timestamp"], keep=False)
    identical_duplicates_removed = 0
    if dup_mask.any():
        full_dup = raw_data.duplicated(keep="first")
        subset_dup = raw_data.duplicated(subset=["timestamp"], keep="first")
        if not full_dup[dup_mask].equals(subset_dup[dup_mask]):
            raise MetroPT3ContractError("conflicting duplicate timestamps detected")

        initial_len = len(raw_data)
        raw_data = raw_data.drop_duplicates(keep="first").reset_index(drop=True)
        identical_duplicates_removed = initial_len - len(raw_data)

    ts_array = raw_data["timestamp"].to_numpy()
    if len(ts_array) > 1 and not np.all(ts_array[1:] > ts_array[:-1]):
        raise MetroPT3ContractError("timestamps are not strictly increasing")

    if len(raw_data) != contract.expected_rows:
        raise MetroPT3ContractError(
            f"normalized row count mismatch: expected {contract.expected_rows}, got {len(raw_data)}"
        )

    return raw_data, identical_duplicates_removed


def _write_telemetry_and_manifest(
    raw_data: pd.DataFrame,
    archive: Path,
    output_dir: Path,
    contract: Phase1BContract,
    identical_duplicates_removed: int,
) -> MetroPT3PreparationManifest:
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
        shutil.rmtree(temp_output, ignore_errors=True)
        raise

    return MetroPT3PreparationManifest(
        archive_sha256=sha256_file(archive),
        contract_sha256=str(contract_manifest["contract_sha256"]),
        output_sha256=output_sha256,
        normalized_rows=len(raw_data),
        canonical_columns=contract.canonical_columns,
        identical_duplicates_removed=identical_duplicates_removed,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        manifest_sha256=manifest_sha256,
    )


def _validate_and_publish(
    frame: pd.DataFrame,
    archive: Path,
    output_dir: Path,
    contract: Phase1BContract,
) -> MetroPT3PreparationManifest:
    raw_data = _validate_source_structure(frame, contract)
    _validate_telemetry_values(raw_data, contract)
    clean_data, identical_dups = _process_duplicates_and_ordering(raw_data, contract)
    return _write_telemetry_and_manifest(clean_data, archive, output_dir, contract, identical_dups)


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
        raise MetroPT3ContractError(
            f"license does not match the frozen contract: {contract.license}"
        )
    if contract.source_doi != "10.24432/C5VW3R":
        raise MetroPT3ContractError(
            f"DOI does not match the frozen contract: {contract.source_doi}"
        )

    with ZipFile(archive) as bundle:
        members = tuple(item.filename for item in bundle.infolist() if not item.is_dir())
        if contract.csv_member not in members:
            raise MetroPT3ContractError(
                f"CSV member {contract.csv_member!r} not in archive: {members}"
            )
        if Path(contract.csv_member).name != contract.csv_member:
            raise MetroPT3ContractError("CSV member must not escape the archive root")
        with bundle.open(contract.csv_member) as source:
            frame = pd.read_csv(source)

    return _validate_and_publish(frame, archive, output_dir, contract)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Prepare MetroPT-3 dataset.")
    parser.add_argument("--archive", type=Path, required=True, help="Path to MetroPT-3 zip archive")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Destination directory for prepared data"
    )
    args = parser.parse_args()

    manifest = prepare_metropt3(args.archive, args.output_dir)
    print(
        f"Successfully prepared MetroPT-3 telemetry: {manifest.normalized_rows} rows -> {args.output_dir}"
    )


if __name__ == "__main__":
    main()
