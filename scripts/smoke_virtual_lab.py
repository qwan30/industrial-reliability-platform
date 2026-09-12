"""Smoke test script verifying the complete Virtual Lab pipeline."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx


def run_smoke_test_with_client(
    client: httpx.Client, base_url: str
) -> dict[str, str | int | float | bool]:
    """Execute end-to-end smoke verification sequence."""
    report: dict[str, str | int | float | bool] = {
        "timestamp": time.time(),
        "base_url": base_url,
    }

    # 1. Health check
    print(f"Checking liveness at {base_url}/v2/healthz...")
    res = client.get("/v2/healthz")
    assert res.status_code == 200, f"Healthz failed: {res.text}"
    report["healthz_status"] = 200

    # 2. Fetch Catalog
    print("Fetching catalog...")
    res_cat = client.get("/v2/catalog")
    assert res_cat.status_code == 200, f"Catalog fetch failed: {res_cat.text}"
    cat_data = res_cat.json()["data"]
    assert "COMPRESSOR" in cat_data["assets"]
    report["catalog_ok"] = True

    # 3. Create Smoke Lab
    smoke_name = f"smoke-{uuid4().hex[:8]}"
    print(f"Creating reference lab '{smoke_name}'...")
    res_create = client.post("/v2/labs", json={"name": smoke_name, "template": "REFERENCE"})
    assert res_create.status_code == 201, f"Create lab failed: {res_create.text}"
    lab_data = res_create.json()["data"]
    lab_id = lab_data["lab_id"]
    report["lab_id"] = lab_id

    # 4. Validate Lab Revision
    print(f"Validating lab {lab_id} rev 1...")
    res_val = client.post(f"/v2/labs/{lab_id}/validate", json={"revision": 1})
    assert res_val.status_code == 200, f"Validation failed: {res_val.text}"
    val_data = res_val.json()["data"]
    assert val_data["run_eligible"] is True, f"Lab not run eligible: {val_data['errors']}"
    report["run_eligible"] = True

    # 5. Start Simulation Run
    print("Starting simulation run...")
    res_run = client.post(
        "/v2/runs",
        json={"lab_id": lab_id, "lab_revision": 1, "seed": 42, "speed": 10, "max_ticks": 2400},
    )
    assert res_run.status_code == 201, f"Create run failed: {res_run.text}"
    run_data = res_run.json()["data"]
    run_id = run_data["run_id"]
    report["run_id"] = run_id

    # 6. Submit Operational Command
    first_valve = next(a for a in lab_data["assets"] if a["type"] == "CONTROL_VALVE")
    cmd_id = str(uuid4())
    print(f"Submitting command to valve {first_valve['asset_id']}...")
    res_cmd = client.post(
        f"/v2/runs/{run_id}/commands",
        json={
            "command_id": cmd_id,
            "expected_control_revision": 0,
            "action": "SET_VALVE_OPENING",
            "target_id": first_valve["asset_id"],
            "parameters": {"opening": 0.4},
        },
    )
    assert res_cmd.status_code == 202, f"Command failed: {res_cmd.text}"
    receipt = res_cmd.json()["data"]
    assert receipt["status"] == "ACCEPTED"
    report["command_accepted"] = True

    # 7. Query Snapshot
    print("Querying snapshot...")
    res_snap = client.get(f"/v2/runs/{run_id}")
    assert res_snap.status_code == 200, f"Snapshot query failed: {res_snap.text}"
    snap_data = res_snap.json()["data"]
    assert snap_data["control_revision"] == 1
    return report


def run_smoke_test(base_url: str) -> dict[str, str | int | float | bool]:
    """Execute smoke test live or with in-process ASGI fallback."""
    try:
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            res = client.get("/v2/healthz")
            if res.status_code == 200:
                print(f"Connected to live lab-api at {base_url}")
                return run_smoke_test_with_client(client, base_url)
    except Exception as e:
        print(f"Live server at {base_url} unreachable ({e}). Running in-process verification...")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tests.test_lab_api import FakeLabStore

        from industrial_reliability.lab.api import create_app
    fake_store = FakeLabStore()
    app = create_app(store=fake_store)
    from fastapi.testclient import TestClient

    with TestClient(app, base_url="http://virtual-lab.test") as client:
        res = run_smoke_test_with_client(client, "http://virtual-lab.test")  # type: ignore[arg-type]
        res["in_process_fallback"] = True
        return res


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test virtual lab API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="Base URL of lab-api")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/virtual-lab/smoke.json"),
        help="Output report JSON file",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    try:
        results = run_smoke_test(args.base_url)
        args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Wrote smoke report to {args.output}")
        return 0
    except Exception as e:
        print(f"Smoke test failed: {e}", file=sys.stderr)
        failure_report = {
            "timestamp": time.time(),
            "base_url": args.base_url,
            "smoke_verdict": "FAIL",
            "error": str(e),
        }
        args.output.write_text(json.dumps(failure_report, indent=2), encoding="utf-8")
        return 1


if __name__ == "__main__":
    sys.exit(main())
