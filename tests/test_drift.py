from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from industrial_reliability.drift import (
    DriftReferenceV1,
    build_reference,
    load_reference,
    max_population_stability_index,
    population_stability_index,
    save_reference,
)


def test_population_stability_index_identical_distribution() -> None:
    # 10 uniform bins with 0.1 expected proportion
    bin_edges = [-np.inf, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, np.inf]
    ref_props = [0.1] * 10

    # Exactly balanced data across bins: 10 samples per bin
    actual = np.array([0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5])
    psi = population_stability_index(actual, bin_edges, ref_props)
    assert psi == pytest.approx(0.0, abs=1e-5)


def test_population_stability_index_shifted_distribution() -> None:
    bin_edges = [-np.inf, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, np.inf]
    ref_props = [0.1] * 10

    # All actual values are in the last bin (> 9.0)
    actual = np.array([10.0, 11.0, 12.0, 15.0, 20.0])
    psi = population_stability_index(actual, bin_edges, ref_props)
    # Severe shift -> PSI should be substantially greater than 0.25
    assert psi > 0.25


def test_build_save_load_reference(tmp_path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Create dummy parquet with train, calibration, and holdout splits
    schema = pa.schema(
        [
            ("split", pa.string()),
            ("tp2_mean", pa.float64()),
            ("dv_pressure_mean", pa.float64()),
        ]
    )
    train_tp2 = np.random.default_rng(42).normal(0.0, 1.0, 100).tolist()
    train_dv = np.random.default_rng(42).normal(5.0, 2.0, 100).tolist()

    # If holdout had extreme values, it MUST NOT affect drift reference
    holdout_tp2 = [999.0] * 50
    holdout_dv = [999.0] * 50

    splits = ["train"] * 100 + ["holdout"] * 50
    tp2 = train_tp2 + holdout_tp2
    dv = train_dv + holdout_dv

    tbl = pa.Table.from_arrays(
        [
            pa.array(splits),
            pa.array(tp2),
            pa.array(dv),
        ],
        schema=schema,
    )

    feat_path = tmp_path / "features.parquet"
    pq.write_table(tbl, feat_path)

    manifest = {
        "model_version": "champion-test-v1",
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "feature_names": ["tp2_mean", "dv_pressure_mean"],
    }

    ref = build_reference(feat_path, manifest)
    assert ref.model_version == "champion-test-v1"
    assert ref.num_train_samples == 100
    assert len(ref.bin_edges["tp2_mean"]) == 11  # 10 bins -> 11 edges
    assert len(ref.reference_proportions["tp2_mean"]) == 10
    assert ref.bin_edges["tp2_mean"][0] == -np.inf
    assert ref.bin_edges["tp2_mean"][-1] == np.inf
    # Ensure holdout 999.0 was not included in quantile bin computation
    assert max(ref.bin_edges["tp2_mean"][1:-1]) < 100.0

    # Save & Load
    target = tmp_path / "drift-reference.json"
    saved_path = save_reference(ref, target)
    assert saved_path.is_file()

    loaded = load_reference(target, expected_manifest=manifest)
    assert loaded.self_sha256 == ref.self_sha256
    assert loaded.model_version == ref.model_version

    # Tampering check
    data = json.loads(target.read_text(encoding="utf-8"))
    data["num_train_samples"] = 999
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="tampered or corrupted"):
        load_reference(tampered_path)


def test_max_population_stability_index(tmp_path: Path) -> None:
    bin_edges = {
        "f1": [-np.inf, 1.0, 2.0, 3.0, np.inf],
        "f2": [-np.inf, 10.0, 20.0, 30.0, np.inf],
    }
    ref_props = {
        "f1": [0.25, 0.25, 0.25, 0.25],
        "f2": [0.25, 0.25, 0.25, 0.25],
    }
    ref = DriftReferenceV1(
        model_version="v1",
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        active_feature_names=("f1", "f2"),
        num_train_samples=100,
        bin_edges=bin_edges,
        reference_proportions=ref_props,
        self_sha256="placeholder",
    )

    # f1 is shifted, f2 is normal
    current = {
        "f1": [99.0, 99.0, 99.0, 99.0],  # all in last bin
        "f2": [5.0, 15.0, 25.0, 35.0],  # perfectly uniform
    }
    max_psi = max_population_stability_index(current, ref)
    assert max_psi > 0.2


def test_drift_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    from industrial_reliability.drift import main

    schema = pa.schema(
        [
            ("split", pa.string()),
            ("tp2_mean", pa.float64()),
        ]
    )
    tbl = pa.Table.from_arrays(
        [
            pa.array(["train"] * 50),
            pa.array(np.linspace(0, 10, 50)),
        ],
        schema=schema,
    )
    feat_path = tmp_path / "feat.parquet"
    pq.write_table(tbl, feat_path)

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "model_version": "v1",
                "source_dataset_sha256": "0" * 64,
                "contract_sha256": "1" * 64,
                "feature_names": ["tp2_mean"],
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "out-ref.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "drift.py",
            "build-reference",
            "--manifest",
            str(manifest_path),
            "--features",
            str(feat_path),
            "--output",
            str(out_path),
        ],
    )
    main()
    captured = capsys.readouterr()
    assert "Successfully built drift reference" in captured.out
    assert out_path.is_file()


def test_drift_requires_feature_overlap() -> None:
    ref = DriftReferenceV1(
        model_version="v1",
        source_dataset_sha256="a" * 64,
        contract_sha256="b" * 64,
        active_feature_names=("f1", "f2"),
        num_train_samples=100,
        bin_edges={"f1": [-np.inf, 1.0, np.inf], "f2": [-np.inf, 2.0, np.inf]},
        reference_proportions={"f1": [0.5, 0.5], "f2": [0.5, 0.5]},
        self_sha256="placeholder",
    )
    current = {"other_feature": [1.0, 2.0]}
    with pytest.raises(
        ValueError, match="drift reference and current features have no feature overlap"
    ):
        max_population_stability_index(current, ref)


@pytest.fixture
def reference() -> DriftReferenceV1:
    bin_edges = {
        "f1": [-np.inf, 1.0, 2.0, 3.0, np.inf],
        "f2": [-np.inf, 10.0, 20.0, 30.0, np.inf],
    }
    ref_props = {
        "f1": [0.25, 0.25, 0.25, 0.25],
        "f2": [0.25, 0.25, 0.25, 0.25],
    }
    from industrial_reliability.drift import _compute_drift_hash

    data = {
        "schema_version": "drift-reference-v1",
        "model_version": "v1",
        "source_dataset_sha256": "a" * 64,
        "contract_sha256": "b" * 64,
        "active_feature_names": ("f1", "f2"),
        "num_train_samples": 100,
        "bin_edges": bin_edges,
        "reference_proportions": ref_props,
        "self_sha256": "",
    }
    self_sha = _compute_drift_hash(data)
    return DriftReferenceV1(
        model_version=data["model_version"],
        source_dataset_sha256=data["source_dataset_sha256"],
        contract_sha256=data["contract_sha256"],
        active_feature_names=data["active_feature_names"],
        num_train_samples=data["num_train_samples"],
        bin_edges=data["bin_edges"],
        reference_proportions=data["reference_proportions"],
        self_sha256=self_sha,
    )


def test_load_reference_rejects_feature_order_mismatch(
    tmp_path: Path,
    reference: DriftReferenceV1,
) -> None:
    path = save_reference(reference, tmp_path / "drift-reference.json")
    expected = {
        "model_version": reference.model_version,
        "source_dataset_sha256": reference.source_dataset_sha256,
        "contract_sha256": reference.contract_sha256,
        "feature_names": tuple(reversed(reference.active_feature_names)),
    }
    with pytest.raises(ValueError, match="feature order"):
        load_reference(path, expected_manifest=expected)
