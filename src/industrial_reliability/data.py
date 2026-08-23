"""Bounded validation and preparation of the local MetroPT source."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from industrial_reliability.contracts import PHASE1, Phase1Contract, contract_manifest


class DataContractError(ValueError):
    """Raised when source bytes or rows violate the frozen contract."""


@dataclass(frozen=True)
class SegmentManifest:
    segment_id: int
    path: str
    start: datetime
    end: datetime
    rows: int
    sha256: str


@dataclass(frozen=True)
class PreparationManifest:
    dataset_sha256: str
    dataset_bytes: int
    dataset_rows: int
    contract_sha256: str
    source_columns: tuple[str, ...]
    total_rows: int
    gap_count: int
    segments: tuple[SegmentManifest, ...]
    manifest_sha256: str


_BINARY_COLUMNS = (
    "COMP",
    "DV_eletric",
    "Towers",
    "MPG",
    "LPS",
    "Pressure_switch",
    "Oil_level",
    "Caudal_impulses",
)
_FLOAT_COLUMNS = (
    "TP2",
    "TP3",
    "H1",
    "DV_pressure",
    "Reservoirs",
    "Oil_temperature",
    "Flowmeter",
    "Motor_current",
    "gpsLong",
    "gpsLat",
    "gpsSpeed",
)
_EPOCH = datetime(1970, 1, 1)


def sha256_file(path: Path) -> str:
    """Hash a file without loading it into memory."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _serialize(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _column_types() -> dict[str, pa.DataType]:
    return {
        "timestamp": pa.timestamp("s"),
        **{column: pa.float64() for column in _FLOAT_COLUMNS},
        **{column: pa.int64() for column in (*_BINARY_COLUMNS, "gpsQuality")},
    }


def _validate_batch(batch: pa.RecordBatch) -> npt.NDArray[np.int64]:
    if any(column.null_count for column in batch.columns):
        raise DataContractError("source rows must not contain null values")

    for column in _FLOAT_COLUMNS:
        values = batch.column(batch.schema.get_field_index(column)).to_numpy(zero_copy_only=False)
        if not np.isfinite(values).all():
            raise DataContractError(f"{column} must contain only finite values")

    for column in _BINARY_COLUMNS:
        values = batch.column(batch.schema.get_field_index(column)).to_numpy(zero_copy_only=False)
        if not np.isin(values, (0, 1)).all():
            raise DataContractError(f"{column} must contain only binary values")

    longitude = batch.column(batch.schema.get_field_index("gpsLong")).to_numpy(
        zero_copy_only=False
    )
    latitude = batch.column(batch.schema.get_field_index("gpsLat")).to_numpy(
        zero_copy_only=False
    )
    quality = batch.column(batch.schema.get_field_index("gpsQuality")).to_numpy(
        zero_copy_only=False
    )
    if not (
        np.array_equal(longitude == 0, latitude == 0)
        and np.array_equal(longitude == 0, quality == 0)
    ):
        raise DataContractError("GPS sentinel disagreement among longitude, latitude, and quality")

    timestamps = batch.column(batch.schema.get_field_index("timestamp")).to_numpy(
        zero_copy_only=False
    )
    return cast(npt.NDArray[np.int64], timestamps.astype("datetime64[s]").astype(np.int64))


def _manifest_payload(
    *,
    dataset_sha256: str,
    dataset_bytes: int,
    dataset_rows: int,
    contract_sha256: str,
    source_columns: tuple[str, ...],
    total_rows: int,
    gap_count: int,
    segments: tuple[SegmentManifest, ...],
) -> dict[str, object]:
    return cast(
        dict[str, object],
        _serialize(
            {
                "dataset_sha256": dataset_sha256,
                "dataset_bytes": dataset_bytes,
                "dataset_rows": dataset_rows,
                "contract_sha256": contract_sha256,
                "source_columns": source_columns,
                "total_rows": total_rows,
                "gap_count": gap_count,
                "segments": [asdict(segment) for segment in segments],
            }
        ),
    )


def prepare_dataset(
    source: Path,
    output_dir: Path,
    contract: Phase1Contract = PHASE1,
) -> PreparationManifest:
    """Validate source identity and write one Parquet file per 1 Hz segment."""
    if output_dir.exists():
        raise FileExistsError(f"destination already exists: {output_dir}")
    if source.name.lower().endswith(".crdownload"):
        raise DataContractError("refusing to read a partial download")

    dataset_bytes = source.stat().st_size
    if dataset_bytes != contract.dataset_bytes:
        raise DataContractError(
            f"source byte count {dataset_bytes} does not match contract {contract.dataset_bytes}"
        )
    dataset_sha256 = sha256_file(source)
    if dataset_sha256 != contract.dataset_sha256:
        raise DataContractError("source SHA-256 does not match contract")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent)
    )
    segments_dir = temporary / "segments"
    segments_dir.mkdir()

    reader: pacsv.CSVStreamingReader | None = None
    writer: pq.ParquetWriter | None = None
    segment_id = 0
    segment_path: Path | None = None
    segment_start: datetime | None = None
    segment_end: datetime | None = None
    segment_rows = 0
    previous_timestamp: int | None = None
    total_rows = 0
    gap_count = 0
    segments: list[SegmentManifest] = []

    def close_segment() -> None:
        nonlocal writer, segment_id, segment_path, segment_start, segment_end, segment_rows
        if writer is None:
            return
        writer.close()
        writer = None
        assert segment_path is not None
        assert segment_start is not None
        assert segment_end is not None
        segments.append(
            SegmentManifest(
                segment_id=segment_id,
                path=segment_path.relative_to(temporary).as_posix(),
                start=segment_start,
                end=segment_end,
                rows=segment_rows,
                sha256=sha256_file(segment_path),
            )
        )
        segment_id += 1
        segment_path = None
        segment_start = None
        segment_end = None
        segment_rows = 0

    try:
        reader = pacsv.open_csv(
            source,
            read_options=pacsv.ReadOptions(block_size=1 << 20, use_threads=False),
            convert_options=pacsv.ConvertOptions(
                column_types=_column_types(),
                timestamp_parsers=["%Y-%m-%d %H:%M:%S"],
            ),
        )
        if tuple(reader.schema.names) != contract.source_columns:
            raise DataContractError("source header or column order does not match contract")

        for batch in reader:
            timestamps = _validate_batch(batch)
            if not len(timestamps):
                continue
            deltas = np.diff(timestamps)
            if np.any(deltas <= 0):
                raise DataContractError("timestamps must be strictly increasing")
            if previous_timestamp is not None:
                cross_batch_delta = int(timestamps[0] - previous_timestamp)
                if cross_batch_delta <= 0:
                    raise DataContractError("timestamps must be strictly increasing")
                if cross_batch_delta > contract.gap_max_delta_seconds:
                    gap_count += 1
                    close_segment()

            boundaries = [
                *(int(index) + 1 for index in np.flatnonzero(deltas > contract.gap_max_delta_seconds)),
                len(timestamps),
            ]
            start_index = 0
            for end_index in boundaries:
                if writer is None:
                    segment_path = segments_dir / f"segment-{segment_id:04d}.parquet"
                    writer = pq.ParquetWriter(segment_path, reader.schema)
                    segment_start = _EPOCH + timedelta(seconds=int(timestamps[start_index]))
                slice_length = end_index - start_index
                writer.write_batch(batch.slice(start_index, slice_length))
                segment_rows += slice_length
                total_rows += slice_length
                segment_end = _EPOCH + timedelta(seconds=int(timestamps[end_index - 1]))
                if end_index != len(timestamps):
                    gap_count += 1
                    close_segment()
                start_index = end_index
            previous_timestamp = int(timestamps[-1])

        close_segment()
        if total_rows != contract.dataset_rows:
            raise DataContractError(
                f"source row count {total_rows} does not match contract {contract.dataset_rows}"
            )
        if total_rows == 0:
            raise DataContractError("source row count must be positive")

        reader.close()
        reader = None

        segment_tuple = tuple(segments)
        contract_sha256 = cast(str, contract_manifest(contract)["contract_sha256"])
        payload = _manifest_payload(
            dataset_sha256=dataset_sha256,
            dataset_bytes=dataset_bytes,
            dataset_rows=total_rows,
            contract_sha256=contract_sha256,
            source_columns=contract.source_columns,
            total_rows=total_rows,
            gap_count=gap_count,
            segments=segment_tuple,
        )
        manifest_sha256 = hashlib.sha256(_canonical_json(payload)).hexdigest()
        manifest = PreparationManifest(
            dataset_sha256=dataset_sha256,
            dataset_bytes=dataset_bytes,
            dataset_rows=total_rows,
            contract_sha256=contract_sha256,
            source_columns=contract.source_columns,
            total_rows=total_rows,
            gap_count=gap_count,
            segments=segment_tuple,
            manifest_sha256=manifest_sha256,
        )
        (temporary / "manifest.json").write_bytes(
            _canonical_json({**payload, "manifest_sha256": manifest_sha256}) + b"\n"
        )
        temporary.rename(output_dir)
        return manifest
    except (pa.ArrowInvalid, pa.ArrowKeyError) as error:
        raise DataContractError(f"source timestamp or value is malformed: {error}") from error
    finally:
        if reader is not None:
            reader.close()
        if writer is not None:
            writer.close()
        if temporary.exists():
            shutil.rmtree(temporary)
