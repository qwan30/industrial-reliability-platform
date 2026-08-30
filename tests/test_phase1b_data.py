from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from industrial_reliability.phase1b_contracts import PHASE1B
from industrial_reliability.phase1b_data import (
    MetroPT3ContractError,
    prepare_metropt3,
    sha256_file,
)


def _create_synthetic_csv(
    rows: int = 10, conflicting_dup: bool = False, identical_dup: bool = False
) -> bytes:
    start = datetime(2020, 2, 1, 0, 0, 0)
    data = []
    for i in range(rows):
        ts = (start + timedelta(seconds=i * 10)).strftime("%Y-%m-%d %H:%M:%S")
        row = [
            i,
            ts,
            1.0 + i * 0.1,  # TP2
            2.0 + i * 0.1,  # TP3
            3.0 + i * 0.1,  # H1
            4.0 + i * 0.1,  # DV_pressure
            5.0 + i * 0.1,  # Reservoirs
            6.0 + i * 0.1,  # Oil_temperature
            7.0 + i * 0.1,  # Motor_current
            1,  # COMP
            0,  # DV_eletric
            1,  # Towers
            0,  # MPG
            0,  # LPS
            1,  # Pressure_switch
            0,  # Oil_level
            1,  # Caudal_impulses
        ]
        data.append(row)

    if identical_dup and rows > 1:
        # duplicate first row with same timestamp and same values (index adjusted)
        dup_row = list(data[0])
        dup_row[0] = rows
        data.append(dup_row)

    if conflicting_dup and rows > 1:
        # duplicate first row timestamp with different values
        dup_row = list(data[0])
        dup_row[0] = rows
        dup_row[2] = 2.0
        data.append(dup_row)

    cols = list(PHASE1B.source_columns)
    df = pd.DataFrame(data, columns=cols)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _create_synthetic_zip(
    zip_path: Path,
    member_name: str = "MetroPT3(AirCompressor).csv",
    rows: int = 10,
    conflicting_dup: bool = False,
    identical_dup: bool = False,
) -> Path:
    csv_bytes = _create_synthetic_csv(
        rows=rows, conflicting_dup=conflicting_dup, identical_dup=identical_dup
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, csv_bytes)
    return zip_path


def test_prepare_metropt3_success(tmp_path: Path) -> None:
    zip_path = _create_synthetic_zip(tmp_path / "valid.zip", rows=10)
    zip_sha = sha256_file(zip_path)
    contract = replace(PHASE1B, archive_sha256=zip_sha, expected_rows=10)

    out_dir = tmp_path / "output"
    manifest = prepare_metropt3(zip_path, out_dir, contract)

    assert manifest.normalized_rows == 10
    assert (out_dir / "telemetry.parquet").exists()
    assert (out_dir / "manifest.json").exists()


def test_prepare_metropt3_collapses_identical_duplicates(tmp_path: Path) -> None:
    zip_path = _create_synthetic_zip(tmp_path / "dup.zip", rows=10, identical_dup=True)
    zip_sha = sha256_file(zip_path)
    contract = replace(PHASE1B, archive_sha256=zip_sha, expected_rows=10)

    out_dir = tmp_path / "output_dup"
    manifest = prepare_metropt3(zip_path, out_dir, contract)

    assert manifest.normalized_rows == 10
    assert manifest.identical_duplicates_removed == 1


def test_prepare_metropt3_fails_on_conflicting_duplicates(tmp_path: Path) -> None:
    zip_path = _create_synthetic_zip(tmp_path / "conflict.zip", rows=10, conflicting_dup=True)
    zip_sha = sha256_file(zip_path)
    contract = replace(PHASE1B, archive_sha256=zip_sha, expected_rows=10)

    out_dir = tmp_path / "output_conflict"
    with pytest.raises(MetroPT3ContractError, match="conflicting duplicate"):
        prepare_metropt3(zip_path, out_dir, contract)


def test_prepare_metropt3_fails_closed_on_identity_mismatch(tmp_path: Path) -> None:
    zip_path = _create_synthetic_zip(tmp_path / "source.zip", rows=10)
    zip_sha = sha256_file(zip_path)

    # Hash mismatch
    contract_wrong_hash = replace(PHASE1B, archive_sha256="0" * 64, expected_rows=10)
    with pytest.raises(MetroPT3ContractError, match="archive SHA-256"):
        prepare_metropt3(zip_path, tmp_path / "out1", contract_wrong_hash)

    # License mismatch
    contract_wrong_lic = replace(
        PHASE1B, archive_sha256=zip_sha, license="GPL-3.0", expected_rows=10
    )
    with pytest.raises(MetroPT3ContractError, match="license"):
        prepare_metropt3(zip_path, tmp_path / "out2", contract_wrong_lic)

    # DOI mismatch
    contract_wrong_doi = replace(
        PHASE1B, archive_sha256=zip_sha, source_doi="wrong-doi", expected_rows=10
    )
    with pytest.raises(MetroPT3ContractError, match="DOI"):
        prepare_metropt3(zip_path, tmp_path / "out3", contract_wrong_doi)

    # Row count mismatch
    contract_wrong_rows = replace(PHASE1B, archive_sha256=zip_sha, expected_rows=999)
    with pytest.raises(MetroPT3ContractError, match="normalized row count"):
        prepare_metropt3(zip_path, tmp_path / "out4", contract_wrong_rows)


def test_prepare_metropt3_destination_exists_error(tmp_path: Path) -> None:
    zip_path = _create_synthetic_zip(tmp_path / "exists.zip", rows=5)
    zip_sha = sha256_file(zip_path)
    contract = replace(PHASE1B, archive_sha256=zip_sha, expected_rows=5)

    out_dir = tmp_path / "existing_dir"
    out_dir.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        prepare_metropt3(zip_path, out_dir, contract)


@pytest.mark.parametrize(
    "source_column,value",
    [
        ("TP2", 21.0),
        ("TP3", -2.0),
        ("Oil_temperature", 151.0),
        ("Motor_current", 51.0),
    ],
)
def test_preparation_rejects_hard_physical_envelope(
    tmp_path: Path,
    source_column: str,
    value: float,
) -> None:
    frame = pd.read_csv(io.BytesIO(_create_synthetic_csv()))
    frame.loc[0, source_column] = value
    archive = tmp_path / "invalid.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("MetroPT3(AirCompressor).csv", frame.to_csv(index=False))
    contract = replace(PHASE1B, archive_sha256=sha256_file(archive), expected_rows=10)
    with pytest.raises(MetroPT3ContractError, match=source_column.lower().split("_")[0]):
        prepare_metropt3(archive, tmp_path / "out", contract)
