from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Literal, Mapping

JSONScalar = str | int | float | bool | None
HEX64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def validate_hex64(val: str, field_name: str = "hash") -> str:
    if not isinstance(val, str) or not HEX64_PATTERN.match(val):
        raise ValueError(f"{field_name} must be a 64-character lowercase hex string, got {val!r}")
    return val


def validate_git_sha(val: str, field_name: str = "source_git_sha") -> str:
    if not isinstance(val, str) or not GIT_SHA_PATTERN.match(val):
        raise ValueError(f"{field_name} must be a 40-character lowercase hex string, got {val!r}")
    return val


def _check_no_nan(obj: Any) -> None:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError("JSON serialization cannot contain NaN or Infinity")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_no_nan(k)
            _check_no_nan(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _check_no_nan(item)


def canonical_dumps(data: Mapping[str, Any] | list[Any]) -> str:
    _check_no_nan(data)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_sha256(data: Mapping[str, Any] | list[Any]) -> str:
    serialized = canonical_dumps(data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RunProvenanceV1:
    schema_version: Literal["mlflow-run-provenance-v1"]
    mlflow_run_id: str
    experiment_name: str
    lifecycle_state: Literal["candidate", "reproduction"]
    dataset_sha256: str
    contract_sha256: str
    feature_schema_sha256: str
    source_git_sha: str
    python_version: str
    dependency_versions: Mapping[str, str]
    champion_package_sha256: str
    alert_policy_sha256: str
    parameters: Mapping[str, JSONScalar]
    metrics: Mapping[str, float]
    artifact_sha256: Mapping[str, str]
    provenance_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != "mlflow-run-provenance-v1":
            raise ValueError(f"Invalid schema_version: {self.schema_version}")
        if self.lifecycle_state not in ("candidate", "reproduction"):
            raise ValueError(f"Invalid lifecycle_state: {self.lifecycle_state}")
        validate_hex64(self.dataset_sha256, "dataset_sha256")
        validate_hex64(self.contract_sha256, "contract_sha256")
        validate_hex64(self.feature_schema_sha256, "feature_schema_sha256")
        validate_git_sha(self.source_git_sha, "source_git_sha")
        validate_hex64(self.champion_package_sha256, "champion_package_sha256")
        validate_hex64(self.alert_policy_sha256, "alert_policy_sha256")
        for k, v in self.artifact_sha256.items():
            validate_hex64(v, f"artifact_sha256[{k}]")

    def compute_hash(self) -> str:
        d = asdict(self)
        d.pop("provenance_sha256", None)
        return canonical_sha256(d)

    def with_computed_hash(self) -> RunProvenanceV1:
        return replace(self, provenance_sha256=self.compute_hash())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RunProvenanceV1:
        return cls(
            schema_version=data["schema_version"],
            mlflow_run_id=data["mlflow_run_id"],
            experiment_name=data["experiment_name"],
            lifecycle_state=data["lifecycle_state"],
            dataset_sha256=data["dataset_sha256"],
            contract_sha256=data["contract_sha256"],
            feature_schema_sha256=data["feature_schema_sha256"],
            source_git_sha=data["source_git_sha"],
            python_version=data["python_version"],
            dependency_versions=dict(data.get("dependency_versions", {})),
            champion_package_sha256=data["champion_package_sha256"],
            alert_policy_sha256=data["alert_policy_sha256"],
            parameters=dict(data.get("parameters", {})),
            metrics=dict(data.get("metrics", {})),
            artifact_sha256=dict(data.get("artifact_sha256", {})),
            provenance_sha256=data.get("provenance_sha256", ""),
        )


@dataclass(frozen=True)
class PromotionReceiptV1:
    schema_version: Literal["mlflow-promotion-receipt-v1"]
    mlflow_run_id: str
    registered_model_name: Literal["industrial-reliability-anomaly-detector"]
    registered_model_version: str
    alias: Literal["champion"]
    model_version: str
    dataset_sha256: str
    contract_sha256: str
    champion_package_sha256: str
    source_git_sha: str
    approver: str
    promoted_at: str
    receipt_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != "mlflow-promotion-receipt-v1":
            raise ValueError(f"Invalid schema_version: {self.schema_version}")
        if self.registered_model_name != "industrial-reliability-anomaly-detector":
            raise ValueError(f"Invalid registered_model_name: {self.registered_model_name}")
        if self.alias != "champion":
            raise ValueError(f"Invalid alias: {self.alias}")
        if not self.approver or not self.approver.strip():
            raise ValueError("approver cannot be empty")
        validate_hex64(self.dataset_sha256, "dataset_sha256")
        validate_hex64(self.contract_sha256, "contract_sha256")
        validate_hex64(self.champion_package_sha256, "champion_package_sha256")
        validate_git_sha(self.source_git_sha, "source_git_sha")

    def compute_hash(self) -> str:
        d = asdict(self)
        d.pop("receipt_sha256", None)
        return canonical_sha256(d)

    def with_computed_hash(self) -> PromotionReceiptV1:
        return replace(self, receipt_sha256=self.compute_hash())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PromotionReceiptV1:
        return cls(
            schema_version=data["schema_version"],
            mlflow_run_id=data["mlflow_run_id"],
            registered_model_name=data["registered_model_name"],
            registered_model_version=str(data["registered_model_version"]),
            alias=data["alias"],
            model_version=data["model_version"],
            dataset_sha256=data["dataset_sha256"],
            contract_sha256=data["contract_sha256"],
            champion_package_sha256=data["champion_package_sha256"],
            source_git_sha=data["source_git_sha"],
            approver=data["approver"],
            promoted_at=data["promoted_at"],
            receipt_sha256=data.get("receipt_sha256", ""),
        )


def verify_run_provenance(prov: RunProvenanceV1) -> None:
    expected = prov.compute_hash()
    if prov.provenance_sha256 != expected:
        raise ValueError(
            f"Run provenance hash mismatch: expected {expected}, got {prov.provenance_sha256}"
        )


def write_run_provenance(path: Path, prov: RunProvenanceV1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prov_with_hash = prov.with_computed_hash()
    content = canonical_dumps(prov_with_hash.to_dict())
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def load_run_provenance(path: Path) -> RunProvenanceV1:
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    prov = RunProvenanceV1.from_dict(data)
    verify_run_provenance(prov)
    return prov


def verify_promotion_receipt(
    receipt: PromotionReceiptV1, package_manifest: Any = None
) -> None:
    expected = receipt.compute_hash()
    if receipt.receipt_sha256 != expected:
        raise ValueError(
            f"Promotion receipt hash mismatch: expected {expected}, got {receipt.receipt_sha256}"
        )
    if receipt.alias != "champion":
        raise ValueError(f"Promotion receipt must specify champion alias, got {receipt.alias}")
    if package_manifest is not None:
        manifest_sha = getattr(package_manifest, "manifest_sha256", None) or getattr(
            package_manifest, "package_sha256", None
        )
        if manifest_sha is not None and manifest_sha != receipt.champion_package_sha256:
            raise ValueError(
                f"Package manifest SHA mismatch: manifest has {manifest_sha}, "
                f"receipt has {receipt.champion_package_sha256}"
            )


def write_promotion_receipt(path: Path, receipt: PromotionReceiptV1) -> None:
    if path.exists():
        raise FileExistsError(f"Promotion receipt destination already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt_with_hash = receipt.with_computed_hash()
    content = canonical_dumps(receipt_with_hash.to_dict())
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def load_promotion_receipt(path: Path) -> PromotionReceiptV1:
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    receipt = PromotionReceiptV1.from_dict(data)
    verify_promotion_receipt(receipt)
    return receipt
