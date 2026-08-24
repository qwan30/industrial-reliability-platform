"""Evidence collection and certification gate for Phase 5 Alert Lifecycle & Persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REQUIRED_PASSES = (
    "policy_locked_before_holdout",
    "duplicate_idempotence_passed",
    "restart_recovery_passed",
    "traceability_passed",
)


@dataclass(frozen=True, slots=True)
class Phase5Evidence:
    policy_locked_before_holdout: bool
    duplicate_idempotence_passed: bool
    restart_recovery_passed: bool
    traceability_passed: bool
    code_git_sha: str
    source_dataset_sha256: str
    contract_sha256: str
    model_version: str
    policy_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_gate(output: Path, evidence: Phase5Evidence) -> None:
    payload = evidence.to_dict()
    for name in REQUIRED_PASSES:
        if payload.get(name) is not True:
            raise ValueError(f"Phase 5 gate verification failed: {name} is not True")

    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    gate_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    payload["gate_sha256"] = gate_sha256

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_suffix(".tmp")
    temp_output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    temp_output.replace(output)
