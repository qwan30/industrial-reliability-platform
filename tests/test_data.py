from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import pytest

import industrial_reliability.data as data_module
from industrial_reliability.contracts import PHASE1
from industrial_reliability.data import DataContractError, prepare_dataset, sha256_file
from tests.helpers import sample_contract, sample_policy, write_sample_csv


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


def _write_source_with_cross_batch_delta(
    path: Path,
    delta_seconds: int,
) -> tuple[Path, int]:
    start = datetime(2022, 1, 1, 6)
    row_count = 12_000
    write_sample_csv(
        path,
        [start + timedelta(seconds=index) for index in range(row_count)],
    )
    assert path.stat().st_size > 1 << 20
    reader = pacsv.open_csv(
        path,
        read_options=pacsv.ReadOptions(block_size=1 << 20, use_threads=False),
    )
    try:
        boundary = reader.read_next_batch().num_rows
    finally:
        reader.close()
    assert 0 < boundary < row_count
    write_sample_csv(
        path,
        [
            start + timedelta(seconds=index if index < boundary else index + delta_seconds - 1)
            for index in range(row_count)
        ],
    )
    return path, boundary


def test_sample_policy_allows_preset_overrides() -> None:
    policy = sample_policy(window_seconds=30, stride_seconds=5)

    assert policy.window_seconds == 30
    assert policy.stride_seconds == 5


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
    assert [pq.read_table(output / segment.path).num_rows for segment in manifest.segments] == [
        3,
        3,
    ]


def test_prepare_dataset_splits_at_gap_between_real_arrow_batches(tmp_path: Path) -> None:
    source, boundary = _write_source_with_cross_batch_delta(
        tmp_path / "large.csv",
        delta_seconds=2,
    )

    manifest = prepare_dataset(
        source,
        tmp_path / "prepared",
        contract=sample_contract(source),
    )

    assert [segment.rows for segment in manifest.segments] == [boundary, 12_000 - boundary]
    assert manifest.gap_count == 1


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
    contract = replace(sample_contract(sample_csv), dataset_sha256="0" * 64)
    output = tmp_path / "prepared"
    with pytest.raises(DataContractError, match="SHA-256"):
        prepare_dataset(sample_csv, output, contract=contract)


def test_prepare_dataset_rejects_byte_count_mismatch(tmp_path: Path, sample_csv: Path) -> None:
    contract = sample_contract(sample_csv)
    contract_mod = replace(contract, dataset_bytes=contract.dataset_bytes + 1)
    output = tmp_path / "prepared"
    with pytest.raises(DataContractError, match="byte count"):
        prepare_dataset(sample_csv, output, contract=contract_mod)


def test_prepare_dataset_rejects_wrong_header_order(tmp_path: Path, sample_csv: Path) -> None:
    with sample_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    rows[0][1], rows[0][2] = rows[0][2], rows[0][1]
    with sample_csv.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)

    contract = _contract_after_edit(sample_csv)
    output = tmp_path / "prepared"
    with pytest.raises(DataContractError, match="header"):
        prepare_dataset(sample_csv, output, contract=contract)


def test_prepare_dataset_rejects_wrong_row_count(tmp_path: Path, sample_csv: Path) -> None:
    contract = sample_contract(sample_csv)
    contract_mod = replace(contract, dataset_rows=contract.dataset_rows + 1)
    output = tmp_path / "prepared"
    with pytest.raises(DataContractError, match="row count"):
        prepare_dataset(sample_csv, output, contract=contract_mod)


def test_prepare_dataset_rejects_malformed_timestamp(tmp_path: Path, sample_csv: Path) -> None:
    _rewrite_cell(sample_csv, 1, "timestamp", "not-a-timestamp")
    contract = _contract_after_edit(sample_csv)
    output = tmp_path / "prepared"

    with pytest.raises(DataContractError, match="timestamp"):
        prepare_dataset(sample_csv, output, contract=contract)


def test_prepare_dataset_rejects_non_binary_digital_value(
    tmp_path: Path,
    sample_csv: Path,
) -> None:
    _rewrite_cell(sample_csv, 1, "COMP", 2)
    contract = _contract_after_edit(sample_csv)
    output = tmp_path / "prepared"

    with pytest.raises(DataContractError, match="binary"):
        prepare_dataset(sample_csv, output, contract=contract)


def test_prepare_dataset_rejects_non_monotonic_timestamp(
    tmp_path: Path,
    sample_csv: Path,
) -> None:
    _rewrite_cell(sample_csv, 2, "timestamp", "2022-01-01 06:00:01")
    contract = _contract_after_edit(sample_csv)
    output = tmp_path / "prepared"

    with pytest.raises(DataContractError, match="strictly increasing"):
        prepare_dataset(sample_csv, output, contract=contract)


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
    contract = _contract_after_edit(sample_csv)
    output = tmp_path / "prepared"

    with pytest.raises(DataContractError, match="GPS sentinel"):
        prepare_dataset(sample_csv, output, contract=contract)


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

    contract = sample_contract(sample_csv)
    with pytest.raises(FileExistsError, match="already exists"):
        prepare_dataset(sample_csv, output, contract=contract)

    assert output.exists()
    assert not list(tmp_path.glob(".prepared.tmp-*"))


def test_prepare_dataset_rejects_partial_download_without_reading_it(tmp_path: Path) -> None:
    source = tmp_path / "dataset_train.csv.crdownload"
    source.write_text("partial", encoding="utf-8")
    output = tmp_path / "prepared"

    with pytest.raises(DataContractError, match="partial download"):
        prepare_dataset(source, output)

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


def test_prepare_dataset_preserves_validation_error_when_reader_close_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _ = _write_source_with_cross_batch_delta(
        tmp_path / "nonmonotonic.csv",
        delta_seconds=0,
    )
    real_open_csv = data_module.pacsv.open_csv

    class CloseFailingReader:
        def __init__(self, reader):
            self._reader = reader
            self.schema = reader.schema

        def __iter__(self):
            return iter(self._reader)

        def close(self) -> None:
            self._reader.close()
            raise RuntimeError("reader close failed")

    def open_csv(*args, **kwargs):
        return CloseFailingReader(real_open_csv(*args, **kwargs))

    monkeypatch.setattr(data_module.pacsv, "open_csv", open_csv)

    with pytest.raises(DataContractError, match="strictly increasing"):
        prepare_dataset(
            source,
            tmp_path / "prepared",
            contract=sample_contract(source),
        )

    assert not (tmp_path / "prepared").exists()
    assert not list(tmp_path.glob(".prepared.tmp-*"))


def test_prepare_dataset_cleans_temporary_directory_when_writer_close_fails(
    tmp_path: Path,
    sample_csv: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_parquet_writer = data_module.pq.ParquetWriter

    class CloseFailingWriter:
        def __init__(self, *args, **kwargs):
            self._writer = real_parquet_writer(*args, **kwargs)

        def write_batch(self, batch) -> None:
            self._writer.write_batch(batch)

        def close(self) -> None:
            self._writer.close()
            raise RuntimeError("writer close failed")

    monkeypatch.setattr(data_module.pq, "ParquetWriter", CloseFailingWriter)

    contract = sample_contract(sample_csv)
    output = tmp_path / "prepared"
    with pytest.raises(RuntimeError, match="writer close failed"):
        prepare_dataset(
            sample_csv,
            output,
            contract=contract,
        )

    assert not (tmp_path / "prepared").exists()
    assert not list(tmp_path.glob(".prepared.tmp-*"))
