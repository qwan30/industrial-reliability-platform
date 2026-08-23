from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from tests.helpers import sample_contract, write_sample_csv

from industrial_reliability.contracts import PHASE1
from industrial_reliability.data import DataContractError, prepare_dataset, sha256_file


def _rewrite_cell(path: Path, row_index: int, column: str, value: object) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    rows[row_index + 1][rows[0].index(column)] = str(value)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)


def _contract_after_edit(path: Path):
    return replace(
        sample_contract(path),
        dataset_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        dataset_bytes=path.stat().st_size,
    )


def test_sha256_file_hashes_file_bytes(tmp_path: Path) -> None:
    path = tmp_path / "bytes.bin"
    path.write_bytes(b"bounded source")

    assert sha256_file(path) == "0780e278c78191da7696ca0fe6bc0c67f9f5e377600d3d4b93579f3afafd5d9b"


def test_prepare_dataset_splits_at_gap(tmp_path: Path, sample_csv: Path) -> None:
    output = tmp_path / "prepared"
    source_bytes = sample_csv.read_bytes()

    manifest = prepare_dataset(sample_csv, output, contract=sample_contract(sample_csv))

    assert [segment.rows for segment in manifest.segments] == [3, 3]
    assert manifest.gap_count == 1
    assert manifest.total_rows == 6
    assert sample_csv.read_bytes() == source_bytes
    assert [segment.path for segment in manifest.segments] == [
        "segments/segment-0000.parquet",
        "segments/segment-0001.parquet",
    ]
    assert [pq.read_table(output / segment.path).num_rows for segment in manifest.segments] == [3, 3]


def test_prepare_dataset_records_source_faithful_manifest(
    tmp_path: Path,
    sample_csv: Path,
) -> None:
    contract = sample_contract(sample_csv)
    output = tmp_path / "prepared"

    manifest = prepare_dataset(sample_csv, output, contract=contract)
    payload = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert manifest.dataset_sha256 == contract.dataset_sha256
    assert manifest.dataset_bytes == sample_csv.stat().st_size
    assert manifest.dataset_rows == 6
    assert manifest.source_columns == PHASE1.source_columns
    assert manifest.segments[0].start == datetime(2022, 1, 1, 6)
    assert manifest.segments[0].end == datetime(2022, 1, 1, 6, 0, 2)
    assert payload["manifest_sha256"] == manifest.manifest_sha256
    assert payload["segments"][0]["sha256"] == sha256_file(output / manifest.segments[0].path)
    without_hash = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    canonical = json.dumps(
        without_hash,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    assert manifest.manifest_sha256 == hashlib.sha256(canonical).hexdigest()
    assert set(payload) == set(asdict(manifest))


def test_prepare_dataset_rejects_hash_mismatch(tmp_path: Path, sample_csv: Path) -> None:
    with pytest.raises(DataContractError, match="SHA-256"):
        prepare_dataset(
            sample_csv,
            tmp_path / "prepared",
            contract=replace(sample_contract(sample_csv), dataset_sha256="0" * 64),
        )


def test_prepare_dataset_rejects_byte_count_mismatch(tmp_path: Path, sample_csv: Path) -> None:
    contract = sample_contract(sample_csv)
    with pytest.raises(DataContractError, match="byte count"):
        prepare_dataset(
            sample_csv,
            tmp_path / "prepared",
            contract=replace(contract, dataset_bytes=contract.dataset_bytes + 1),
        )


def test_prepare_dataset_rejects_wrong_header_order(tmp_path: Path, sample_csv: Path) -> None:
    with sample_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    rows[0][1], rows[0][2] = rows[0][2], rows[0][1]
    with sample_csv.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)

    with pytest.raises(DataContractError, match="header"):
        prepare_dataset(sample_csv, tmp_path / "prepared", contract=_contract_after_edit(sample_csv))


def test_prepare_dataset_rejects_wrong_row_count(tmp_path: Path, sample_csv: Path) -> None:
    contract = sample_contract(sample_csv)
    with pytest.raises(DataContractError, match="row count"):
        prepare_dataset(
            sample_csv,
            tmp_path / "prepared",
            contract=replace(contract, dataset_rows=contract.dataset_rows + 1),
        )


def test_prepare_dataset_rejects_malformed_timestamp(tmp_path: Path, sample_csv: Path) -> None:
    _rewrite_cell(sample_csv, 1, "timestamp", "not-a-timestamp")

    with pytest.raises(DataContractError, match="timestamp"):
        prepare_dataset(sample_csv, tmp_path / "prepared", contract=_contract_after_edit(sample_csv))


def test_prepare_dataset_rejects_non_binary_digital_value(
    tmp_path: Path,
    sample_csv: Path,
) -> None:
    _rewrite_cell(sample_csv, 1, "COMP", 2)

    with pytest.raises(DataContractError, match="binary"):
        prepare_dataset(sample_csv, tmp_path / "prepared", contract=_contract_after_edit(sample_csv))


def test_prepare_dataset_rejects_non_monotonic_timestamp(
    tmp_path: Path,
    sample_csv: Path,
) -> None:
    _rewrite_cell(sample_csv, 2, "timestamp", "2022-01-01 06:00:01")

    with pytest.raises(DataContractError, match="strictly increasing"):
        prepare_dataset(sample_csv, tmp_path / "prepared", contract=_contract_after_edit(sample_csv))


@pytest.mark.parametrize(
    ("column", "value"),
    [("gpsLong", -8.65934), ("gpsLat", 41.2124), ("gpsQuality", 1)],
)
def test_prepare_dataset_rejects_gps_sentinel_disagreement(
    tmp_path: Path,
    sample_csv: Path,
    column: str,
    value: object,
) -> None:
    _rewrite_cell(sample_csv, 0, column, value)

    with pytest.raises(DataContractError, match="GPS sentinel"):
        prepare_dataset(sample_csv, tmp_path / "prepared", contract=_contract_after_edit(sample_csv))


def test_prepare_dataset_allows_valid_coordinates_with_zero_speed(
    tmp_path: Path,
    sample_csv: Path,
) -> None:
    output = tmp_path / "prepared"

    prepare_dataset(sample_csv, output, contract=sample_contract(sample_csv))

    table = pq.read_table(output / "segments" / "segment-0000.parquet")
    assert table.column("gpsSpeed").to_pylist() == [0.0, 0.0, 0.0]
    assert table.column("gpsQuality").to_pylist() == [0, 1, 0]


@pytest.mark.parametrize("existing_kind", ["empty", "nonempty"])
def test_prepare_dataset_rejects_any_existing_destination(
    tmp_path: Path,
    sample_csv: Path,
    existing_kind: str,
) -> None:
    output = tmp_path / "prepared"
    output.mkdir()
    if existing_kind == "nonempty":
        (output / "unrelated.txt").write_text("owner data", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        prepare_dataset(sample_csv, output, contract=sample_contract(sample_csv))

    assert output.exists()
    assert not list(tmp_path.glob(".prepared.tmp-*"))


def test_prepare_dataset_rejects_partial_download_without_reading_it(tmp_path: Path) -> None:
    source = tmp_path / "dataset_train.csv.crdownload"
    source.write_text("partial", encoding="utf-8")

    with pytest.raises(DataContractError, match="partial download"):
        prepare_dataset(source, tmp_path / "prepared")

    assert not (tmp_path / "prepared").exists()


def test_prepare_dataset_cleans_temporary_directory_after_parse_error(tmp_path: Path) -> None:
    source = tmp_path / "malformed.csv"
    start = datetime(2022, 1, 1, 6)
    write_sample_csv(source, [start + timedelta(seconds=offset) for offset in range(3)])
    _rewrite_cell(source, 1, "timestamp", "bad")

    with pytest.raises(DataContractError):
        prepare_dataset(source, tmp_path / "prepared", contract=_contract_after_edit(source))

    assert not (tmp_path / "prepared").exists()
    assert not list(tmp_path.glob(".prepared.tmp-*"))
