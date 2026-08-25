from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _canonical_json(data: Any) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o),
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def write_decision(
    *,
    spec: Path,
    phase7_gate: Path,
    git_sha: str,
    output: Path,
) -> Path:
    if not spec.is_file():
        raise ValueError(f"Roadmap spec not found at {spec}")
    if not phase7_gate.is_file():
        raise ValueError(f"Phase 7 gate report not found at {phase7_gate}")

    gate = json.loads(phase7_gate.read_text(encoding="utf-8"))
    # Validate passing phase 7 gate
    if gate.get("verdict") != "PASS":
        raise ValueError(f"Phase 7 gate did not pass: verdict={gate.get('verdict')}")

    if not re.fullmatch(r"[0-9a-f]{40}", git_sha):
        raise ValueError("Git SHA must be 40 lowercase hexadecimal characters")

    payload: dict[str, Any] = {
        "schema_version": "airflow-decision-v1",
        "decision": "NOT_ADOPTED",
        "approved_recurring_workflows": 0,
        "scheduled_workflows": 0,
        "promotion_mode": "manual",
        "airflow_installed": False,
        "roadmap_spec_sha256": _sha256_file(spec),
        "phase7_gate_sha256": _sha256_file(phase7_gate),
        "git_sha": git_sha,
        "reconsideration_trigger": "an approved recurring or scheduled workflow with measured orchestration requirements",
    }

    raw_json = _canonical_json(payload)
    decision_sha256 = hashlib.sha256(raw_json).hexdigest()
    full_payload = {**payload, "decision_sha256": decision_sha256}

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_file = output.with_suffix(f".tmp.{output.suffix}")
    temp_file.write_text(json.dumps(full_payload, indent=2), encoding="utf-8")
    temp_file.replace(output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write Phase 7A Airflow NOT_ADOPTED decision artifact"
    )
    parser.add_argument("--spec", type=Path, required=True, help="Roadmap spec file")
    parser.add_argument("--phase7-gate", type=Path, required=True, help="Phase 7 gate JSON file")
    parser.add_argument("--git-sha", type=str, required=True, help="Current 40-char git commit SHA")
    parser.add_argument("--output", type=Path, required=True, help="Output decision JSON path")

    args = parser.parse_args(argv)
    try:
        res = write_decision(
            spec=args.spec,
            phase7_gate=args.phase7_gate,
            git_sha=args.git_sha,
            output=args.output,
        )
        print(f"Phase 7A Airflow decision written to {res}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
