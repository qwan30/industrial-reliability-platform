"""Evidence collection and certification gate for Phase 6 Operator Console."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REQUIRED_PASSES = (
    "console_feed_stream_passed",
    "reconnectable_sse_passed",
    "react_components_certified",
    "e2e_real_click_flow_passed",
    "branch_coverage_met",
)


@dataclass(frozen=True, slots=True)
class Phase6Evidence:
    console_feed_stream_passed: bool
    reconnectable_sse_passed: bool
    react_components_certified: bool
    e2e_real_click_flow_passed: bool
    branch_coverage_met: bool
    code_git_sha: str
    source_dataset_sha256: str
    contract_sha256: str
    model_version: str
    python_coverage_pct: float
    typescript_coverage_pct: float
    console_bundle_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_gate(output: Path, evidence: Phase6Evidence) -> None:
    payload = evidence.to_dict()
    for name in REQUIRED_PASSES:
        if payload.get(name) is not True:
            raise ValueError(f"Phase 6 gate verification failed: {name} is not True")

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
