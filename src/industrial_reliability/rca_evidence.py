from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from industrial_reliability.persistence import AlertDetailRecord

RCA_TOOL_NAMES = (
    "get_alert",
    "get_score_evidence",
    "get_model_provenance",
    "get_system_health",
)

JsonScalar = str | int | float | bool | list[str]


class AlertNotFound(Exception):
    pass


class EvidenceItemV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: str = Field(min_length=1)
    tool_name: Literal[
        "get_alert",
        "get_score_evidence",
        "get_model_provenance",
        "get_system_health",
    ]
    observed_at: datetime
    facts: dict[str, JsonScalar]


class EvidenceBundleV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["rca-evidence-bundle-v1"] = "rca-evidence-bundle-v1"
    alert_id: str = Field(min_length=1)
    replay_session_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: tuple[EvidenceItemV1, ...]
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _canonical_json(data: Any) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o),
    ).encode("utf-8")


def _evidence_id(tool_name: str, facts: Mapping[str, JsonScalar]) -> str:
    digest = hashlib.sha256(
        _canonical_json({"facts": dict(sorted(facts.items())), "tool_name": tool_name})
    ).hexdigest()
    return f"evidence-{digest[:24]}"


def _compute_bundle_hash(data: dict[str, Any]) -> str:
    copy_data = dict(data)
    copy_data["bundle_sha256"] = ""
    return hashlib.sha256(_canonical_json(copy_data)).hexdigest()


def _sanitize_scalar(val: Any) -> JsonScalar:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if not math.isfinite(val):
            raise ValueError(f"Non-finite float not allowed: {val}")
        return float(val) if isinstance(val, float) else val
    if isinstance(val, list):
        return [str(x) for x in val]
    return str(val)


def get_alert_evidence(detail: AlertDetailRecord) -> EvidenceItemV1:
    alert = detail.alert
    observed_at = (
        alert.last_detection.replace(tzinfo=UTC)
        if alert.last_detection.tzinfo is None
        else alert.last_detection
    )
    first_dt = (
        alert.first_detection.replace(tzinfo=UTC)
        if alert.first_detection.tzinfo is None
        else alert.first_detection
    )
    last_dt = (
        alert.last_detection.replace(tzinfo=UTC)
        if alert.last_detection.tzinfo is None
        else alert.last_detection
    )
    active_duration = (last_dt - first_dt).total_seconds()
    facts: dict[str, JsonScalar] = {
        "action": str(detail.events[0]["action"]) if detail.events else "OPENED",
        "active_duration_seconds": float(active_duration),
        "alert_id": str(alert.alert_id),
        "decision_count": len(detail.decisions),
        "first_detection": alert.first_detection.isoformat(),
        "last_detection": alert.last_detection.isoformat(),
        "machine_id": str(alert.machine_id),
        "state": str(alert.state),
    }
    if detail.decisions:
        first_dec = detail.decisions[0]
        if "score" in first_dec:
            facts["score"] = _sanitize_scalar(first_dec["score"])
        if "threshold" in first_dec:
            facts["threshold"] = _sanitize_scalar(first_dec["threshold"])
    return EvidenceItemV1(
        evidence_id=_evidence_id("get_alert", facts),
        tool_name="get_alert",
        observed_at=observed_at,
        facts=facts,
    )


def get_score_evidence(detail: AlertDetailRecord) -> EvidenceItemV1:
    alert = detail.alert
    observed_at = (
        alert.last_detection.replace(tzinfo=UTC)
        if alert.last_detection.tzinfo is None
        else alert.last_detection
    )
    facts: dict[str, JsonScalar] = {}
    if detail.evidence:
        first_ev = detail.evidence[0]
        if "feature_deviations" in first_ev and isinstance(first_ev["feature_deviations"], list):
            for dev in first_ev["feature_deviations"]:
                feat_name = str(dev.get("feature_name", "unknown"))
                obs_val = _sanitize_scalar(dev.get("observed_value", 0.0))
                abs_dev = _sanitize_scalar(dev.get("absolute_deviation", 0.0))
                facts[f"feature_{feat_name}_observed"] = obs_val
                facts[f"feature_{feat_name}_deviation"] = abs_dev
        if "data_quality" in first_ev and isinstance(first_ev["data_quality"], dict):
            for k, v in first_ev["data_quality"].items():
                facts[f"dq_{k}"] = _sanitize_scalar(v)
    return EvidenceItemV1(
        evidence_id=_evidence_id("get_score_evidence", facts),
        tool_name="get_score_evidence",
        observed_at=observed_at,
        facts=facts,
    )


def get_model_provenance_evidence(
    detail: AlertDetailRecord, champion_dir: Path | None = None
) -> EvidenceItemV1:
    alert = detail.alert
    observed_at = (
        alert.last_detection.replace(tzinfo=UTC)
        if alert.last_detection.tzinfo is None
        else alert.last_detection
    )
    model_ver = "champion-statistical-v1"
    contract_sha = "0" * 64
    dataset_sha = "0" * 64
    if detail.decisions:
        dec = detail.decisions[0]
        model_ver = str(dec.get("model_version", model_ver))
        contract_sha = str(dec.get("contract_sha256", contract_sha))
        dataset_sha = str(dec.get("source_dataset_sha256", dataset_sha))

    facts: dict[str, JsonScalar] = {
        "contract_sha256": contract_sha,
        "model_version": model_ver,
        "source_dataset_sha256": dataset_sha,
    }

    # If champion artifacts exist, read manifest metadata without secrets
    champ_path = champion_dir or Path("artifacts/champion")
    manifest_file = champ_path / "manifest.json"
    if manifest_file.is_file():
        try:
            m_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            facts["champion_manifest_model_id"] = str(m_data.get("model_id", ""))
            facts["champion_threshold"] = float(m_data.get("threshold", 0.0))
        except Exception:
            pass

    return EvidenceItemV1(
        evidence_id=_evidence_id("get_model_provenance", facts),
        tool_name="get_model_provenance",
        observed_at=observed_at,
        facts=facts,
    )


def get_system_health_evidence(detail: AlertDetailRecord) -> EvidenceItemV1:
    alert = detail.alert
    observed_at = (
        alert.last_detection.replace(tzinfo=UTC)
        if alert.last_detection.tzinfo is None
        else alert.last_detection
    )
    facts: dict[str, JsonScalar] = {}
    if detail.evidence:
        first_ev = detail.evidence[0]
        if "system_health" in first_ev and isinstance(first_ev["system_health"], dict):
            for k, v in first_ev["system_health"].items():
                facts[f"health_{k}"] = _sanitize_scalar(v)
    if not facts:
        facts["health_status"] = "normal"
    return EvidenceItemV1(
        evidence_id=_evidence_id("get_system_health", facts),
        tool_name="get_system_health",
        observed_at=observed_at,
        facts=facts,
    )


def gather_evidence(
    alert_id: str, store: Any, champion_dir: Path | None = None
) -> EvidenceBundleV1:
    detail: AlertDetailRecord | None = store.get_alert_detail(alert_id)
    if detail is None:
        raise AlertNotFound(f"Alert '{alert_id}' not found in runtime store")

    item_1 = get_alert_evidence(detail)
    item_2 = get_score_evidence(detail)
    item_3 = get_model_provenance_evidence(detail, champion_dir=champion_dir)
    item_4 = get_system_health_evidence(detail)
    items = (item_1, item_2, item_3, item_4)

    replay_session_id = "00000000-0000-0000-0000-000000000000"
    model_version = "champion-statistical-v1"
    contract_sha256 = "0" * 64
    source_dataset_sha256 = "0" * 64
    if detail.decisions:
        first_dec = detail.decisions[0]
        replay_session_id = str(first_dec.get("replay_session_id", replay_session_id))
        model_version = str(first_dec.get("model_version", model_version))
        contract_sha256 = str(first_dec.get("contract_sha256", contract_sha256))
        source_dataset_sha256 = str(first_dec.get("source_dataset_sha256", source_dataset_sha256))

    raw_bundle_dict: dict[str, Any] = {
        "alert_id": alert_id,
        "bundle_sha256": "",
        "contract_sha256": contract_sha256,
        "items": [item.model_dump() for item in items],
        "model_version": model_version,
        "replay_session_id": replay_session_id,
        "schema_version": "rca-evidence-bundle-v1",
        "source_dataset_sha256": source_dataset_sha256,
    }
    b_hash = _compute_bundle_hash(raw_bundle_dict)

    return EvidenceBundleV1(
        schema_version="rca-evidence-bundle-v1",
        alert_id=alert_id,
        replay_session_id=replay_session_id,
        model_version=model_version,
        contract_sha256=contract_sha256,
        source_dataset_sha256=source_dataset_sha256,
        items=items,
        bundle_sha256=b_hash,
    )
