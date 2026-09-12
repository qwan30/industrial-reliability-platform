"""Export Lab Pydantic models to JSON Schema and fixtures for frontend TS synchronization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from industrial_reliability.lab.catalog import get_catalog, get_reference_lab_definition
from industrial_reliability.lab.contracts import (
    ActiveFault,
    Asset,
    CommandReceipt,
    CommandRequest,
    ControlState,
    EngineCheckpoint,
    LabAlert,
    LabDefinition,
    LabEvent,
    LabValidationError,
    LabValidationResult,
    Observation,
    PhysicalState,
    Pipe,
    PortRef,
    RunSnapshot,
    RunSpec,
    SceneBinding,
    Sensor,
    SimulationRun,
)
from industrial_reliability.report_hashes import canonical_json_bytes

SCHEMA_MODELS = {
    "LabDefinition": LabDefinition,
    "Asset": Asset,
    "Pipe": Pipe,
    "Sensor": Sensor,
    "PortRef": PortRef,
    "SceneBinding": SceneBinding,
    "RunSpec": RunSpec,
    "SimulationRun": SimulationRun,
    "PhysicalState": PhysicalState,
    "Observation": Observation,
    "CommandRequest": CommandRequest,
    "CommandReceipt": CommandReceipt,
    "LabEvent": LabEvent,
    "LabAlert": LabAlert,
    "ActiveFault": ActiveFault,
    "ControlState": ControlState,
    "EngineCheckpoint": EngineCheckpoint,
    "LabValidationError": LabValidationError,
    "LabValidationResult": LabValidationResult,
    "RunSnapshot": RunSnapshot,
}


def build_schema_bundle() -> dict[str, Any]:
    """Generate bundled JSON Schema containing all virtual lab contracts."""
    definitions: dict[str, Any] = {}
    for name, model_cls in SCHEMA_MODELS.items():
        adapter = TypeAdapter(model_cls)
        definitions[name] = adapter.json_schema()

    ref_lab = get_reference_lab_definition()
    catalog = get_catalog()

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Industrial Reliability Virtual Lab Schema Bundle",
        "version": "lab-contracts-v1",
        "definitions": definitions,
        "fixtures": {
            "reference_lab": ref_lab.model_dump(mode="json"),
            "catalog": catalog,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export virtual lab contracts schema.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether exported schema matches file on disk without writing.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "apps"
        / "operator-console"
        / "src"
        / "lab"
        / "contracts.schema.json",
        help="Output schema JSON file path.",
    )
    args = parser.parse_args()

    bundle = build_schema_bundle()
    formatted = json.dumps(bundle, indent=2, sort_keys=True) + "\n"

    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.check:
        if not output_path.is_file():
            print(
                f"Error: {output_path} does not exist. Run export_lab_contracts.py without --check.",
                file=sys.stderr,
            )
            return 1
        current = output_path.read_text(encoding="utf-8")
        if canonical_json_bytes(json.loads(current)) != canonical_json_bytes(bundle):
            print(
                f"Error: {output_path} is out of date with current Pydantic models. Run python scripts/export_lab_contracts.py.",
                file=sys.stderr,
            )
            return 1
        print("Contracts schema is up to date.")
        return 0

    output_path.write_text(formatted, encoding="utf-8")
    print(f"Wrote contracts schema bundle to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
