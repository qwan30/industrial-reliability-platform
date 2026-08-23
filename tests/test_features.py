"""Behavior tests for causal Phase 1 feature construction."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import fields, replace
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
from tests.helpers import (
    make_segment,
    make_segment_around_split_boundary,
    sample_contract,
    sample_contract_for_frame,
    write_sample_csv,
)

import industrial_reliability.features as features_module
from industrial_reliability.contracts import PHASE1, Phase1Contract, Split, contract_manifest
from industrial_reliability.data import DataContractError, prepare_dataset, sha256_file
from industrial_reliability.features import (
    FeatureManifest,
    build_features,
    extract_segment_features,
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _prepared_feature_inputs(tmp_path: Path) -> tuple[Path, Path, Phase1Contract]:
    start = pd.Timestamp("2022-01-01 06:00:00").to_pydatetime()
    source = tmp_path / "source.csv"
    write_sample_csv(
        source,
        [start + timedelta(seconds=offset) for offset in range(80)],
    )
    contract = sample_contract(source)
    prepared = tmp_path / "prepared"
    prepare_dataset(source, prepared, contract)
    return prepared, tmp_path / "features.parquet", contract


def test_future_change_does_not_change_prior_feature() -> None:
    original = make_segment(seconds=2_100)
    changed = original.copy()
    changed.loc[changed.index[-1], "TP2"] = 9_999.0
    contract = sample_contract_for_frame(original)

    before = extract_segment_features(original, contract)
    after = extract_segment_features(changed, contract)

    pd.testing.assert_series_equal(before.iloc[0], after.iloc[0])


def test_production_windows_are_exactly_1800_rows_and_sensor_major() -> None:
    frame = make_segment(seconds=2_400)

    result = extract_segment_features(frame, PHASE1)

    assert result["window_end"].tolist() == [
        pd.Timestamp("2022-01-01 06:29:59"),
        pd.Timestamp("2022-01-01 06:34:59"),
        pd.Timestamp("2022-01-01 06:39:59"),
    ]
    assert (result["window_end"] - result["window_start"]).dt.total_seconds().eq(1_799).all()
    assert len(result.columns[3:]) == 63
    assert tuple(result.columns[3:]) == PHASE1.feature_columns
    first = result.iloc[0]
    assert first["TP2__last"] == 1_800.0
    assert first["TP2__mean"] == 900.5
    assert first["TP2__std"] == pd.Series(range(1, 1_801), dtype=float).std(ddof=0)
    assert first["TP2__min"] == 1.0
    assert first["TP2__max"] == 1_800.0
    assert first["TP2__delta"] == 1_799.0
    assert first["COMP__last"] == 1
    assert first["COMP__active_ratio"] == 0.5
    assert first["COMP__transition_count"] == 1_799


def test_excluded_columns_cannot_affect_features() -> None:
    original = make_segment(seconds=1_800)
    changed = original.copy()
    excluded = set(PHASE1.source_columns) - {"timestamp", *PHASE1.predictor_columns}
    for column in excluded:
        changed[column] = 9_999

    before = extract_segment_features(original, PHASE1)
    after = extract_segment_features(changed, PHASE1)

    pd.testing.assert_frame_equal(before, after)
    assert not any(
        feature.startswith(f"{column}__")
        for column in excluded
        for feature in before.columns
    )


def test_windows_never_cross_gap_or_split_boundary() -> None:
    frame = make_segment_around_split_boundary()
    contract = sample_contract_for_frame(frame)
    frame.loc[100:, "timestamp"] += timedelta(seconds=1)

    result = extract_segment_features(frame, contract)

    assert result["split"].tolist() == ["train"]
    assert (result["window_end"] - result["window_start"]).dt.total_seconds().eq(59).all()
    timestamps = set(pd.to_datetime(frame["timestamp"]))
    for row in result.itertuples():
        split = getattr(contract, row.split)
        assert row.window_start >= split.start
        assert row.window_end < split.end
        expected = pd.date_range(row.window_start, row.window_end, freq="s")
        assert set(expected).issubset(timestamps)


def test_segment_anchor_resets_after_prepared_gap(tmp_path: Path) -> None:
    start = pd.Timestamp("2022-01-01 06:00:00").to_pydatetime()
    source = tmp_path / "source.csv"
    offsets = [*range(100), *range(101, 191)]
    write_sample_csv(source, [start + timedelta(seconds=offset) for offset in offsets])
    contract = sample_contract(source)
    prepared = tmp_path / "prepared"
    prepare_dataset(source, prepared, contract)
    output = tmp_path / "features.parquet"

    manifest = build_features(prepared, output, contract)
    table = pq.read_table(output).to_pandas()

    assert table["window_end"].tolist() == [
        start + timedelta(seconds=offset)
        for offset in (59, 69, 79, 89, 99, 160, 170, 180, 190)
    ]
    assert manifest.total_windows == 9
    assert manifest.windows_by_split == {"train": 9, "calibration": 0, "holdout": 0}


def test_feature_manifest_has_exact_fields_counts_and_hashes(tmp_path: Path) -> None:
    start = pd.Timestamp("2022-01-01 06:39:00").to_pydatetime()
    source = tmp_path / "source.csv"
    write_sample_csv(
        source,
        [start + timedelta(seconds=offset) for offset in range(180)],
    )
    base_contract = sample_contract(source)
    contract = replace(
        base_contract,
        train=Split("train", start, start + timedelta(seconds=60)),
        calibration=Split(
            "calibration",
            start + timedelta(seconds=60),
            start + timedelta(seconds=120),
        ),
        holdout=Split(
            "holdout",
            start + timedelta(seconds=120),
            start + timedelta(seconds=180),
        ),
    )
    prepared = tmp_path / "prepared"
    prepare_dataset(source, prepared, contract)
    output = tmp_path / "features.parquet"

    manifest = build_features(prepared, output, contract)
    feature_table = pq.read_table(output).to_pandas()

    assert tuple(field.name for field in fields(FeatureManifest)) == (
        "contract_sha256",
        "data_manifest_sha256",
        "feature_columns",
        "total_windows",
        "windows_by_split",
        "rejected_windows_by_reason",
        "output_path",
        "output_sha256",
        "manifest_sha256",
    )
    assert manifest.contract_sha256 == contract_manifest(contract)["contract_sha256"]
    data_manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.data_manifest_sha256 == data_manifest["manifest_sha256"]
    assert manifest.feature_columns == contract.feature_columns
    assert manifest.total_windows == 3
    assert feature_table["split"].tolist() == ["train", "calibration", "holdout"]
    assert manifest.windows_by_split == {"train": 1, "calibration": 1, "holdout": 1}
    assert manifest.rejected_windows_by_reason == {
        "split_boundary": 10,
        "timestamp_gap": 0,
    }
    assert manifest.output_path == "features.parquet"
    assert manifest.output_sha256 == sha256_file(output)

    sidecar = json.loads(output.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    assert set(sidecar) == {field.name for field in fields(FeatureManifest)}
    manifest_hash = sidecar.pop("manifest_sha256")
    assert manifest_hash == hashlib.sha256(_canonical_json(sidecar)).hexdigest()
    assert manifest.manifest_sha256 == manifest_hash


def test_build_features_rejects_tampered_data_manifest(tmp_path: Path) -> None:
    prepared, output, contract = _prepared_feature_inputs(tmp_path)
    manifest_path = prepared / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["total_rows"] += 1
    manifest_path.write_bytes(_canonical_json(manifest) + b"\n")

    with pytest.raises(DataContractError, match="data manifest SHA-256"):
        build_features(prepared, output, contract)

    assert not output.exists()
    assert not output.with_suffix(".manifest.json").exists()


def test_build_features_rejects_tampered_segment(tmp_path: Path) -> None:
    prepared, output, contract = _prepared_feature_inputs(tmp_path)
    data_manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    segment = prepared / data_manifest["segments"][0]["path"]
    with segment.open("ab") as handle:
        handle.write(b"tampered")

    with pytest.raises(DataContractError, match="segment SHA-256 mismatch"):
        build_features(prepared, output, contract)

    assert not output.exists()
    assert not output.with_suffix(".manifest.json").exists()


@pytest.mark.parametrize("existing", ["output", "manifest"])
def test_build_features_preserves_preexisting_destination_bytes(
    tmp_path: Path,
    existing: str,
) -> None:
    prepared, output, contract = _prepared_feature_inputs(tmp_path)
    manifest_path = output.with_suffix(".manifest.json")
    destination = output if existing == "output" else manifest_path
    destination.write_bytes(b"owner-controlled bytes")

    with pytest.raises(FileExistsError, match="already exists"):
        build_features(prepared, output, contract)

    assert destination.read_bytes() == b"owner-controlled bytes"
    assert not (manifest_path if existing == "output" else output).exists()


def test_build_features_does_not_overwrite_destination_created_after_precheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, output, contract = _prepared_feature_inputs(tmp_path)
    real_load_manifest = features_module._load_data_manifest

    def load_manifest_then_create_destination(*args, **kwargs):
        manifest = real_load_manifest(*args, **kwargs)
        output.write_bytes(b"racing owner bytes")
        return manifest

    monkeypatch.setattr(features_module, "_load_data_manifest", load_manifest_then_create_destination)

    with pytest.raises(FileExistsError):
        build_features(prepared, output, contract)

    assert output.read_bytes() == b"racing owner bytes"
    assert not output.with_suffix(".manifest.json").exists()


def test_build_features_removes_claimed_output_when_manifest_claim_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, output, contract = _prepared_feature_inputs(tmp_path)
    manifest_path = output.with_suffix(".manifest.json")
    real_link = os.link

    def fail_manifest_claim(source, destination, *args, **kwargs):
        if Path(destination) == manifest_path:
            raise OSError("simulated manifest claim failure")
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", fail_manifest_claim)

    with pytest.raises(OSError, match="simulated manifest claim failure"):
        build_features(prepared, output, contract)

    assert not output.exists()
    assert not manifest_path.exists()
    assert not list(tmp_path.glob(".features*.tmp-*"))


def test_build_features_preserves_output_replaced_before_manifest_claim_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, output, contract = _prepared_feature_inputs(tmp_path)
    manifest_path = output.with_suffix(".manifest.json")
    replacement = b"replacement owner bytes"
    real_link = os.link

    def replace_output_then_fail_manifest(source, destination, *args, **kwargs):
        if Path(destination) == manifest_path:
            output.unlink()
            output.write_bytes(replacement)
            raise OSError("simulated failure after output replacement")
        return real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", replace_output_then_fail_manifest)

    with pytest.raises(OSError, match="simulated failure after output replacement"):
        build_features(prepared, output, contract)

    assert output.read_bytes() == replacement
    assert not manifest_path.exists()
    assert not list(tmp_path.glob(".features*.tmp-*"))
