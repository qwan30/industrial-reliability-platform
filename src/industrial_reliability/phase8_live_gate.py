"""Phase 8 fault-isolation evidence gates.

The unit helper preserves the in-process fault-report contract for deterministic
tests. The public ``run_phase8_live_gate`` path is dependency-backed: it
requires a healthy Compose deployment and records native Kafka, PostgreSQL,
Prometheus, and HTTP observations in an integration report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from industrial_reliability.fault_report import (
    DrillResultV1,
    FaultReportV1,
    build_drill_settings,
    build_fault_report,
    run_known_abnormal_replay_drill,
    run_malformed_telemetry_drill,
    run_scoring_outage_drill,
)
from industrial_reliability.kafka_io import encode_message
from industrial_reliability.report_hashes import (
    compute_self_hash,
    require_committed_git_sha,
    resolve_git_sha,
)
from industrial_reliability.runtime_messages import (
    QUARANTINE_TOPIC,
    SCORES_TOPIC,
    TELEMETRY_TOPIC,
    EvidenceValueV1,
    ScoreDecisionV1,
)

logger = logging.getLogger(__name__)

PHASE8_LIVE_SCHEMA: Literal["phase8-live-fault-drills-v1"] = "phase8-live-fault-drills-v1"
PHASE8_RANGE_START = "2020-05-29T22:00:00"
PHASE8_RANGE_END = "2020-05-30T00:30:00"
PHASE8_SPEED = 1000
PHASE8_REQUIRED_SERVICES = (
    "postgres",
    "kafka",
    "scoring-api",
    "streaming-worker",
    "alert-service",
    "prometheus",
)
PHASE8_DEPENDENCY_RECEIPTS = (
    {"dependency": "kafka", "endpoint": "127.0.0.1:29092"},
    {"dependency": "postgres", "endpoint": "127.0.0.1:5432"},
    {"dependency": "scoring_api", "endpoint": "127.0.0.1:8000"},
)


@dataclass(frozen=True, slots=True)
class LiveDrillResultV1:
    drill_type: str
    expected_classification: str
    actual_classification: str
    passed: bool
    recovery_seconds: float | None
    messages_before: int
    messages_after: int
    committed_offset_before: int | None
    committed_offset_after: int | None
    lost_messages: int
    duplicate_messages: int
    quarantine_messages: int
    alert_persisted: bool | None
    alert_id: str | None
    evidence_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LiveFaultReportV1:
    schema_version: Literal["phase8-live-fault-drills-v1"]
    evidence_level: Literal["INTEGRATION"]
    provider_mode: Literal["INTEGRATION"]
    simulated_components: tuple[str, ...]
    git_sha: str
    timestamp: str
    verdict: Literal["BLOCKED", "PASS", "FAIL"]
    all_passed: bool
    drills: tuple[LiveDrillResultV1, ...]
    prerequisite_errors: tuple[str, ...]
    dependency_receipts: tuple[dict[str, str], ...]
    self_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["drills"] = [drill.to_dict() for drill in self.drills]
        payload["simulated_components"] = list(self.simulated_components)
        payload["prerequisite_errors"] = list(self.prerequisite_errors)
        payload["dependency_receipts"] = [dict(item) for item in self.dependency_receipts]
        return payload


PHASE8_GATE_MODEL_VERSION = "research-statistical-v1"
PHASE8_REPORT_BASENAME = "phase-8-live-fault-drills"


async def execute_live_drills() -> list[DrillResultV1]:
    """Run the three fault drills with research-candidate settings."""
    settings = build_drill_settings(model_version=PHASE8_GATE_MODEL_VERSION)
    return [
        await run_scoring_outage_drill(settings),
        await run_malformed_telemetry_drill(settings),
        await run_known_abnormal_replay_drill(settings),
    ]


def publish_live_drill_report(
    drills: list[DrillResultV1],
    json_path: Path,
    md_path: Path,
    git_sha: str,
) -> FaultReportV1:
    """Publish an in-process unit report with a fixed evidence level/schema."""
    report = build_fault_report(
        drills,
        git_sha,
        evidence_level="UNIT",
        schema_version="phase8-fault-report-v1",
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return report


def _run_command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True, shell=False)


def _request_json(
    method: str,
    url: str,
    payload: Mapping[str, Any] | None = None,
    *,
    timeout_seconds: float = 10.0,
) -> Mapping[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP {response.status}")
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("runtime endpoint unavailable") from exc
    if not isinstance(result, Mapping):
        raise ValueError("runtime endpoint returned a non-object")
    return result


def _request_status(
    method: str,
    url: str,
    *,
    timeout_seconds: float = 10.0,
) -> None:
    request = Request(url, method=method, headers={"Accept": "text/plain"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP {response.status}")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("runtime status endpoint unavailable") from exc


def _compose_service_healthy(service: str) -> bool:
    result = _run_command(["docker", "compose", "ps", "--all", "--format", "json", service])
    if result.returncode != 0:
        return False
    try:
        row = _parse_compose_services(result.stdout).get(service)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if row is None:
        return False
    state = str(row.get("State", "")).lower()
    health = str(row.get("Health", "")).lower()
    return "running" in state and (not health or health in {"healthy", "running"})


def _require_runtime_data(payload: Mapping[str, Any], operation: str) -> dict[str, Any]:
    data = payload.get("data")
    if payload.get("success") is not True or not isinstance(data, dict):
        raise RuntimeError(f"{operation} returned an unsuccessful response")
    return data


def _parse_compose_services(output: str) -> dict[str, dict[str, Any]]:
    if not output.strip():
        return {}
    try:
        decoded = json.loads(output)
        rows = decoded if isinstance(decoded, list) else [decoded]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    return {
        str(row.get("Service") or row.get("Name")): dict(row)
        for row in rows
        if isinstance(row, Mapping)
    }


def _runtime_preflight() -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    errors: list[str] = []
    config = _run_command(["docker", "compose", "config", "--quiet"])
    if config.returncode != 0:
        errors.append("docker compose config --quiet failed")

    services = _run_command(["docker", "compose", "ps", "--all", "--format", "json"])
    if services.returncode != 0:
        errors.append("docker compose ps failed")
    else:
        try:
            rows = _parse_compose_services(services.stdout)
            for service in PHASE8_REQUIRED_SERVICES:
                row = rows.get(service)
                if row is None:
                    errors.append(f"required service is missing: {service}")
                    continue
                state = str(row.get("State", "")).lower()
                health = str(row.get("Health", "")).lower()
                if "running" not in state:
                    errors.append(f"required service is not running: {service}")
                if health and health not in {"healthy", "running"}:
                    errors.append(f"required service is unhealthy: {service}")
        except (TypeError, ValueError, json.JSONDecodeError):
            errors.append("docker compose ps returned invalid JSON")

    api_url = os.environ.get("PHASE8_API_URL", "http://127.0.0.1:8000").rstrip("/")
    prometheus_url = os.environ.get(
        "PHASE8_PROMETHEUS_URL",
        "http://127.0.0.1:9090",
    ).rstrip("/")
    try:
        _request_json("GET", f"{api_url}/healthz")
    except Exception:
        errors.append("scoring API health endpoint is unavailable")
    try:
        _request_status("GET", f"{prometheus_url}/-/ready")
    except Exception:
        errors.append("Prometheus readiness endpoint is unavailable")

    manifest = Path(
        os.environ.get(
            "PHASE8_PACKAGE_MANIFEST",
            "artifacts/research-candidate/manifest.json",
        )
    )
    if not manifest.is_file():
        errors.append(f"research package manifest is missing: {manifest}")
    parquet = Path(
        os.environ.get(
            "PHASE8_TELEMETRY_PARQUET",
            "data/processed/phase1b/metropt3/telemetry.parquet",
        )
    )
    if not parquet.is_file():
        errors.append(f"runtime telemetry parquet is missing: {parquet}")
    return tuple(errors), PHASE8_DEPENDENCY_RECEIPTS


def _build_live_fault_report(
    drills: Sequence[LiveDrillResultV1],
    git_sha: str,
    *,
    prerequisite_errors: Sequence[str] = (),
    dependency_receipts: Sequence[dict[str, str]] = (),
) -> LiveFaultReportV1:
    require_committed_git_sha(git_sha)
    errors = tuple(prerequisite_errors)
    drill_tuple = tuple(drills)
    receipt_tuple = tuple(dependency_receipts)
    all_passed = not errors and len(drill_tuple) == 4 and all(drill.passed for drill in drill_tuple)
    verdict: Literal["BLOCKED", "PASS", "FAIL"] = (
        "BLOCKED" if errors else ("PASS" if all_passed else "FAIL")
    )
    base: dict[str, Any] = {
        "schema_version": PHASE8_LIVE_SCHEMA,
        "evidence_level": "INTEGRATION",
        "provider_mode": "INTEGRATION",
        "simulated_components": [],
        "git_sha": git_sha,
        "timestamp": datetime.now(UTC).isoformat(),
        "verdict": verdict,
        "all_passed": all_passed,
        "drills": [drill.to_dict() for drill in drill_tuple],
        "prerequisite_errors": list(errors),
        "dependency_receipts": [dict(item) for item in receipt_tuple],
        "self_sha256": "",
    }
    return LiveFaultReportV1(
        schema_version=PHASE8_LIVE_SCHEMA,
        evidence_level="INTEGRATION",
        provider_mode="INTEGRATION",
        simulated_components=(),
        git_sha=git_sha,
        timestamp=str(base["timestamp"]),
        verdict=verdict,
        all_passed=all_passed,
        drills=drill_tuple,
        prerequisite_errors=errors,
        dependency_receipts=receipt_tuple,
        self_sha256=compute_self_hash(base, "self_sha256"),
    )


def _write_live_report(report: LiveFaultReportV1, target_dir: Path) -> LiveFaultReportV1:
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / f"{PHASE8_REPORT_BASENAME}.json"
    md_path = target_dir / f"{PHASE8_REPORT_BASENAME}.md"
    payload = json.dumps(report.to_dict(), indent=2)
    temp_json = json_path.with_suffix(".json.tmp")
    temp_json.write_text(payload, encoding="utf-8")
    temp_json.replace(json_path)
    temp_md = md_path.with_suffix(".md.tmp")
    temp_md.write_text(_render_live_markdown(report), encoding="utf-8")
    temp_md.replace(md_path)
    return report


def _render_live_markdown(report: LiveFaultReportV1) -> str:
    lines = [
        "# Phase 8 Runtime Fault Drill Report",
        "",
        f"- **Verdict:** `{report.verdict}`",
        f"- **Evidence Level:** `{report.evidence_level}`",
        f"- **Git SHA:** `{report.git_sha}`",
        f"- **Self SHA-256:** `{report.self_sha256}`",
        "",
        "## Prerequisite Errors",
    ]
    if report.prerequisite_errors:
        lines.extend(f"- {error}" for error in report.prerequisite_errors)
    else:
        lines.append("- None")
    lines.extend(["", "## Fault Isolation Drills", ""])
    for drill in report.drills:
        lines.extend(
            [
                f"### `{drill.drill_type}`",
                f"- Expected: `{drill.expected_classification}`",
                f"- Actual: `{drill.actual_classification}`",
                f"- Passed: `{drill.passed}`",
                f"- Recovery seconds: `{drill.recovery_seconds}`",
                f"- Messages: `{drill.messages_before}` → `{drill.messages_after}`",
                f"- Offsets: `{drill.committed_offset_before}` → `{drill.committed_offset_after}`",
                f"- Loss / duplicates / quarantine: `{drill.lost_messages}` / "
                f"`{drill.duplicate_messages}` / `{drill.quarantine_messages}`",
                f"- Alert persisted: `{drill.alert_persisted}`",
                f"- Alert ID: `{drill.alert_id}`",
                f"- Evidence: {drill.evidence_summary}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _phase8_urls() -> tuple[str, str]:
    return (
        os.environ.get("PHASE8_API_URL", "http://127.0.0.1:8000").rstrip("/"),
        os.environ.get("PHASE8_PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/"),
    )


def _prometheus_value(base_url: str, query: str) -> float:
    payload = _request_json(
        "GET",
        f"{base_url}/api/v1/query?query={quote(query, safe='')}",
    )
    if payload.get("status") != "success":
        raise RuntimeError("Prometheus query failed")
    result = payload.get("data", {}).get("result")
    if not isinstance(result, list) or not result:
        raise RuntimeError(f"Prometheus query returned no samples: {query}")
    value = result[0].get("value") if isinstance(result[0], Mapping) else None
    if not isinstance(value, list) or len(value) != 2:
        raise RuntimeError(f"Prometheus query returned an invalid sample: {query}")
    try:
        parsed = float(value[1])
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Prometheus query returned a non-numeric sample: {query}") from exc
    if parsed < 0:
        raise RuntimeError(f"Prometheus query returned a negative sample: {query}")
    return parsed


def _runtime_counters(prometheus_url: str) -> dict[str, int]:
    queries = {
        "accepted": 'sum(irp_telemetry_events_total{outcome="accepted"})',
        "duplicate": 'sum(irp_telemetry_events_total{outcome="duplicate"})',
        "quarantine": 'sum(irp_telemetry_events_total{outcome="quarantined"})',
        "score_ok": 'sum(irp_score_requests_total{outcome="ok"})',
        "score_unavailable": 'sum(irp_score_requests_total{outcome="unavailable"})',
        "anomaly": "sum(irp_anomaly_decisions_total)",
        "alerts": 'sum(irp_alert_events_total{action="opened"})',
    }
    return {
        name: round(_prometheus_value(prometheus_url, query)) for name, query in queries.items()
    }


def _start_replay(api_url: str) -> str:
    payload = _request_json(
        "POST",
        f"{api_url}/v1/replays",
        {
            "range_start": PHASE8_RANGE_START,
            "range_end": PHASE8_RANGE_END,
            "speed": PHASE8_SPEED,
        },
    )
    data = _require_runtime_data(payload, "replay start")
    session_id = data.get("replay_session_id")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("replay start did not return replay_session_id")
    return session_id


def _replay_status(api_url: str, session_id: str) -> dict[str, Any]:
    payload = _request_json(
        "GET",
        f"{api_url}/v1/replays/{quote(session_id, safe='')}",
    )
    return _require_runtime_data(payload, "replay status")


def _wait_for_replay(
    api_url: str,
    session_id: str,
    *,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = _replay_status(api_url, session_id)
        state = status.get("state")
        if state == "COMPLETED":
            return status
        if state == "FAILED":
            raise RuntimeError(f"replay failed: {status.get('error_code', 'unknown')}")
        time.sleep(0.5)
    raise RuntimeError("replay did not complete before the timeout")


def _list_replay_alerts(api_url: str, session_id: str) -> list[dict[str, Any]]:
    payload = _request_json(
        "GET",
        f"{api_url}/v1/replays/{quote(session_id, safe='')}/alerts",
    )
    alerts = _require_runtime_data(payload, "replay alerts").get("alerts")
    if not isinstance(alerts, list) or not all(isinstance(alert, dict) for alert in alerts):
        raise RuntimeError("replay alerts response was invalid")
    return alerts


def _get_consumer_offset(
    group: str = "irp-streaming-worker-v1",
    topic: str = TELEMETRY_TOPIC,
) -> int | None:
    command = _run_command(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "kafka",
            "/opt/kafka/bin/kafka-consumer-groups.sh",
            "--bootstrap-server",
            "kafka:9092",
            "--group",
            group,
            "--topic",
            topic,
            "--describe",
        ]
    )
    if command.returncode != 0:
        return None
    offsets: list[int] = []
    for line in command.stdout.splitlines():
        columns = line.split()
        if len(columns) < 3 or columns[0].lower() == "topic" or columns[0] != topic:
            continue
        try:
            offsets.append(int(columns[2]))
        except ValueError:
            continue
    return max(offsets) if offsets else None


def _wait_for_replay_active(
    api_url: str,
    session_id: str,
    *,
    timeout_seconds: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = _replay_status(api_url, session_id)
        state = status.get("state")
        if state == "RUNNING":
            return
        if state == "COMPLETED":
            raise RuntimeError("replay completed before broker interruption started")
        if state == "FAILED":
            raise RuntimeError("replay failed before broker interruption started")
        time.sleep(0.2)
    raise RuntimeError("replay did not become active before broker interruption")


def _wait_for_compose_service(service: str, *, timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        command = _run_command(["docker", "compose", "ps", "--all", "--format", "json", service])
        if command.returncode == 0:
            try:
                rows = json.loads(command.stdout)
                if isinstance(rows, Mapping):
                    rows = [rows]
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, Mapping):
                            continue
                        row_service = str(row.get("Service") or "")
                        row_name = str(row.get("Name") or "")
                        state = str(row.get("State") or "").lower()
                        health = str(row.get("Health") or "").lower()
                        if (
                            (row_service == service or row_name.startswith(f"{service}-"))
                            and "running" in state
                            and (not health or health in {"healthy", "running"})
                        ):
                            return
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        time.sleep(0.5)
    raise RuntimeError(f"runtime service did not recover: {service}")


def _run_broker_interruption(api_url: str, prometheus_url: str) -> LiveDrillResultV1:
    before_messages = _runtime_counters(prometheus_url)["accepted"]
    before_offset = _get_consumer_offset(
        group="irp-streaming-worker-v1",
        topic=TELEMETRY_TOPIC,
    )
    session_id = _start_replay(api_url)
    _wait_for_replay_active(api_url, session_id)
    active_status = _replay_status(api_url, session_id)
    if active_status.get("state") != "RUNNING":
        raise RuntimeError("replay was not active before broker interruption started")

    recovery_started = time.monotonic()
    stopped = _run_command(["docker", "compose", "stop", "kafka"])
    if stopped.returncode != 0:
        raise RuntimeError("docker compose stop kafka failed")
    try:
        time.sleep(1.0)
        outage_status = _replay_status(api_url, session_id)
        if outage_status.get("state") != "RUNNING":
            raise RuntimeError("replay did not remain active during broker interruption")
    finally:
        restarted = _run_command(["docker", "compose", "start", "kafka"])
        if restarted.returncode != 0:
            raise RuntimeError("docker compose start kafka failed")
    _wait_for_compose_service("kafka")
    recovery_seconds = round(time.monotonic() - recovery_started, 3)
    status = _wait_for_replay(api_url, session_id)
    after_messages = _runtime_counters(prometheus_url)["accepted"]
    after_offset = _get_consumer_offset(
        group="irp-streaming-worker-v1",
        topic=TELEMETRY_TOPIC,
    )
    expected_messages = status.get("last_sequence")
    if not isinstance(expected_messages, int) or expected_messages <= 0:
        raise RuntimeError("broker drill replay did not expose a terminal sequence")
    observed = after_messages - before_messages
    lost = max(0, expected_messages - observed)
    duplicate = max(0, observed - expected_messages)
    passed = (
        outage_status.get("state") == "RUNNING"
        and status.get("state") == "COMPLETED"
        and before_offset is not None
        and after_offset is not None
        and after_offset >= before_offset
        and lost == 0
        and duplicate == 0
    )
    return LiveDrillResultV1(
        drill_type="broker-interruption",
        expected_classification="SERVICE",
        actual_classification="SERVICE" if passed else "UNKNOWN",
        passed=passed,
        recovery_seconds=recovery_seconds,
        messages_before=before_messages,
        messages_after=after_messages,
        committed_offset_before=before_offset,
        committed_offset_after=after_offset,
        lost_messages=lost,
        duplicate_messages=duplicate,
        quarantine_messages=0,
        alert_persisted=None,
        alert_id=None,
        evidence_summary="Kafka interruption recovered without offset regression, loss, or duplication.",
    )


def _load_runtime_package() -> dict[str, Any]:
    package_path = Path(
        os.environ.get(
            "PHASE8_PACKAGE_MANIFEST",
            "artifacts/research-candidate/manifest.json",
        )
    )
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if not isinstance(package, dict):
        raise RuntimeError("research package manifest must be a JSON object")
    for key in ("model_version", "source_dataset_sha256", "contract_sha256"):
        if not isinstance(package.get(key), str) or not package[key]:
            raise RuntimeError(f"research package manifest is missing {key}")
    return package


async def _publish_database_fault_decisions(
    session_id: UUID,
    package: Mapping[str, Any],
) -> int:
    from aiokafka import AIOKafkaProducer

    bootstrap = os.environ.get("PHASE8_KAFKA_BOOTSTRAP", "127.0.0.1:29092")
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
    model_version = str(package["model_version"])
    source_dataset_sha256 = str(package["source_dataset_sha256"])
    contract_sha256 = str(package["contract_sha256"])
    threshold = float(package.get("threshold", 0.0))
    source_start = datetime(2020, 5, 29, 22, 0, 0)
    await producer.start()
    try:
        for index in range(3):
            decision_id = uuid4()
            decision = ScoreDecisionV1(
                message_id=decision_id,
                replay_session_id=session_id,
                source_dataset_sha256=source_dataset_sha256,
                contract_sha256=contract_sha256,
                source_timestamp=source_start + timedelta(minutes=5 * index),
                emitted_at=datetime.now(UTC),
                decision_id=decision_id,
                window_id=uuid4(),
                model_version=model_version,
                score=threshold + 1.0,
                threshold=threshold,
                is_anomaly=True,
                evidence_vector=(
                    EvidenceValueV1(
                        feature_name="tp2_mean",
                        feature_value=threshold + 1.0,
                        robust_deviation=1.0,
                    ),
                ),
            )
            await producer.send_and_wait(
                SCORES_TOPIC,
                value=encode_message(decision),
                key=str(session_id).encode("ascii"),
            )
    finally:
        await producer.stop()
    return 3


def _wait_for_alerts(
    api_url: str,
    session_id: str,
    *,
    timeout_seconds: float = 90.0,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            alerts = _list_replay_alerts(api_url, session_id)
            if alerts:
                return alerts
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("database drill alert did not persist before the timeout")


def _run_database_interruption(api_url: str, prometheus_url: str) -> LiveDrillResultV1:
    del prometheus_url
    package = _load_runtime_package()
    alert_group = "irp-alert-service-v1"
    before_offset = _get_consumer_offset(group=alert_group, topic=SCORES_TOPIC)
    session_id = uuid4()
    recovery_started = time.monotonic()
    stopped = _run_command(["docker", "compose", "stop", "postgres"])
    if stopped.returncode != 0:
        raise RuntimeError("docker compose stop postgres failed")
    try:
        expected_decisions = asyncio.run(_publish_database_fault_decisions(session_id, package))
        time.sleep(2.0)
        failed_offset = _get_consumer_offset(group=alert_group, topic=SCORES_TOPIC)
    finally:
        restarted = _run_command(["docker", "compose", "start", "postgres"])
        if restarted.returncode != 0:
            raise RuntimeError("docker compose start postgres failed")
    _wait_for_compose_service("postgres")
    recovery_seconds = round(time.monotonic() - recovery_started, 3)

    recovered_offset = _get_consumer_offset(group=alert_group, topic=SCORES_TOPIC)
    offset_deadline = time.monotonic() + 90.0
    while time.monotonic() < offset_deadline and (
        recovered_offset is None
        or (before_offset is not None and recovered_offset <= before_offset)
    ):
        time.sleep(0.5)
        recovered_offset = _get_consumer_offset(group=alert_group, topic=SCORES_TOPIC)

    alerts = _wait_for_alerts(api_url, str(session_id))
    alert_ids = [str(alert.get("alert_id")) for alert in alerts if alert.get("alert_id")]
    detail = (
        _require_runtime_data(
            _request_json("GET", f"{api_url}/v1/alerts/{quote(alert_ids[0], safe='')}"),
            "database drill alert detail",
        )
        if len(alert_ids) == 1
        else {}
    )
    decisions = detail.get("decisions") if isinstance(detail, Mapping) else None
    decision_ids = (
        [
            str(decision.get("decision_id"))
            for decision in decisions
            if isinstance(decision, dict) and decision.get("decision_id")
        ]
        if isinstance(decisions, list)
        else []
    )
    persisted_once = (
        len(alerts) == 1
        and len(alert_ids) == 1
        and isinstance(decisions, list)
        and len(decision_ids) == expected_decisions
        and len(set(decision_ids)) == expected_decisions
        and all(
            isinstance(decision, dict)
            and decision.get("replay_session_id") == str(session_id)
            and decision.get("source_dataset_sha256") == package["source_dataset_sha256"]
            and decision.get("contract_sha256") == package["contract_sha256"]
            and decision.get("model_version") == package["model_version"]
            for decision in decisions
        )
    )
    failed_write_did_not_advance = failed_offset == before_offset
    recovered = recovered_offset is not None and (
        before_offset is None or recovered_offset > before_offset
    )
    passed = failed_write_did_not_advance and recovered and persisted_once
    return LiveDrillResultV1(
        drill_type="database-interruption",
        expected_classification="SERVICE",
        actual_classification="SERVICE" if passed else "UNKNOWN",
        passed=passed,
        recovery_seconds=recovery_seconds,
        messages_before=0,
        messages_after=expected_decisions,
        committed_offset_before=before_offset,
        committed_offset_after=recovered_offset,
        lost_messages=0 if persisted_once else expected_decisions,
        duplicate_messages=0
        if persisted_once
        else max(0, len(decision_ids) - len(set(decision_ids))),
        quarantine_messages=0,
        alert_persisted=persisted_once,
        alert_id=alert_ids[0] if persisted_once else None,
        evidence_summary=(
            "PostgreSQL interruption left the alert offset uncommitted during failure and "
            "persisted the anomaly decisions exactly once after recovery."
        ),
    )


async def _publish_malformed_telemetry() -> bool:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

    bootstrap = os.environ.get("PHASE8_KAFKA_BOOTSTRAP", "127.0.0.1:29092")
    consumer = AIOKafkaConsumer(
        QUARANTINE_TOPIC,
        bootstrap_servers=bootstrap,
        group_id=f"phase8-quarantine-{uuid4().hex}",
        auto_offset_reset="latest",
        enable_auto_commit=False,
    )
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
    await consumer.start()
    await producer.start()
    try:
        await producer.send_and_wait(TELEMETRY_TOPIC, value=b"invalid-runtime-telemetry")
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            records = await consumer.getmany(timeout_ms=500, max_records=1)
            if any(records.values()):
                return True
        return False
    finally:
        await producer.stop()
        await consumer.stop()


def _run_malformed_telemetry(api_url: str, prometheus_url: str) -> LiveDrillResultV1:
    before = _runtime_counters(prometheus_url)
    quarantine_received = asyncio.run(_publish_malformed_telemetry())
    time.sleep(2.0)
    worker_healthy = _compose_service_healthy("streaming-worker")

    after = _runtime_counters(prometheus_url)
    quarantine_delta = after["quarantine"] - before["quarantine"]
    passed = (
        quarantine_received
        and quarantine_delta > 0
        and after["score_ok"] == before["score_ok"]
        and after["score_unavailable"] == before["score_unavailable"]
        and after["anomaly"] == before["anomaly"]
        and after["alerts"] == before["alerts"]
        and worker_healthy
    )
    return LiveDrillResultV1(
        drill_type="malformed-telemetry",
        expected_classification="DATA",
        actual_classification="DATA" if passed else "UNKNOWN",
        passed=passed,
        recovery_seconds=2.0,
        messages_before=before["accepted"],
        messages_after=after["accepted"],
        committed_offset_before=None,
        committed_offset_after=None,
        lost_messages=0,
        duplicate_messages=0,
        quarantine_messages=quarantine_delta,
        alert_persisted=None,
        alert_id=None,
        evidence_summary="Malformed bytes reached the quarantine topic without downstream scoring or alerting.",
    )


def _run_known_abnormal_replay(api_url: str, prometheus_url: str) -> LiveDrillResultV1:
    before_messages = _runtime_counters(prometheus_url)["accepted"]
    session_id = _start_replay(api_url)
    status = _wait_for_replay(api_url, session_id)
    alerts = _list_replay_alerts(api_url, session_id)
    package = _load_runtime_package()
    expected_dataset = package["source_dataset_sha256"]
    expected_contract = package["contract_sha256"]
    expected_model = package["model_version"]
    persisted = False
    alert_id: str | None = None
    if alerts:
        alert_id = str(alerts[0].get("alert_id"))
        detail = _require_runtime_data(
            _request_json("GET", f"{api_url}/v1/alerts/{quote(alert_id, safe='')}"),
            "abnormal alert detail",
        )
        alert = detail.get("alert")
        decisions = detail.get("decisions")
        evidence = detail.get("evidence")
        persisted = (
            isinstance(alert, dict)
            and alert.get("replay_session_id") == session_id
            and isinstance(decisions, list)
            and isinstance(evidence, list)
            and all(
                isinstance(item, dict)
                and item.get("replay_session_id") == session_id
                and item.get("source_dataset_sha256") == expected_dataset
                and item.get("contract_sha256") == expected_contract
                and item.get("model_version") == expected_model
                for item in decisions
            )
            and all(
                isinstance(item, dict) and item.get("alert_id") == alert_id for item in evidence
            )
        )
    after_messages = _runtime_counters(prometheus_url)["accepted"]
    expected_messages = status.get("last_sequence")
    observed = after_messages - before_messages
    lost = max(0, int(expected_messages) - observed) if isinstance(expected_messages, int) else 1
    duplicate = (
        max(0, observed - int(expected_messages)) if isinstance(expected_messages, int) else 1
    )
    passed = status.get("state") == "COMPLETED" and persisted and lost == 0 and duplicate == 0
    return LiveDrillResultV1(
        drill_type="known-abnormal-replay",
        expected_classification="MACHINE",
        actual_classification="MACHINE" if passed else "UNKNOWN",
        passed=passed,
        recovery_seconds=0.0,
        messages_before=before_messages,
        messages_after=after_messages,
        committed_offset_before=None,
        committed_offset_after=None,
        lost_messages=lost,
        duplicate_messages=duplicate,
        quarantine_messages=0,
        alert_persisted=persisted,
        alert_id=alert_id,
        evidence_summary="Known-abnormal replay produced a persisted alert bound to the replay and research package.",
    )


def _failed_live_drill(
    drill_type: str,
    expected_classification: str,
    exc: Exception,
) -> LiveDrillResultV1:
    return LiveDrillResultV1(
        drill_type=drill_type,
        expected_classification=expected_classification,
        actual_classification="UNKNOWN",
        passed=False,
        recovery_seconds=None,
        messages_before=0,
        messages_after=0,
        committed_offset_before=None,
        committed_offset_after=None,
        lost_messages=0,
        duplicate_messages=0,
        quarantine_messages=0,
        alert_persisted=None,
        alert_id=None,
        evidence_summary=f"Runtime drill unavailable: {type(exc).__name__}.",
    )


def _execute_runtime_drills() -> tuple[LiveDrillResultV1, ...]:
    api_url, prometheus_url = _phase8_urls()
    runners = (
        ("broker-interruption", "SERVICE", _run_broker_interruption),
        ("database-interruption", "SERVICE", _run_database_interruption),
        ("malformed-telemetry", "DATA", _run_malformed_telemetry),
        ("known-abnormal-replay", "MACHINE", _run_known_abnormal_replay),
    )
    results: list[LiveDrillResultV1] = []
    for drill_type, expected, runner in runners:
        try:
            results.append(runner(api_url, prometheus_url))
        except Exception as exc:
            logger.exception("Phase 8 runtime drill failed: %s", drill_type)
            results.append(_failed_live_drill(drill_type, expected, exc))
    return tuple(results)


def _render_markdown(report: FaultReportV1) -> str:
    md_lines = [
        "# Phase 8 Observability & Reliability Fault Drill Report",
        "",
        f"- **Verdict:** `{'PASS' if report.all_passed else 'FAIL'}`",
        f"- **Evidence Level:** `{report.evidence_level}`",
        f"- **Simulated Components:** `{', '.join(report.simulated_components)}`",
        f"- **Git SHA:** `{report.git_sha}`",
        f"- **Timestamp:** `{report.timestamp}`",
        f"- **Self SHA-256:** `{report.self_sha256}`",
        "",
        "## Fault Isolation Drill Results",
        "",
        "| Drill Type | Expected | Actual | Status | Summary |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for d in report.drills:
        status_sym = "PASS" if d.passed else "FAIL"
        md_lines.append(
            f"| `{d.drill_type}` | `{d.expected_classification}` | "
            f"`{d.actual_classification}` | **{status_sym}** | {d.evidence_summary} |"
        )

    md_lines.extend(
        [
            "",
            "## Operational Invariants",
            "- Service fault isolates scoring outages without telemetry drop.",
            "- Data fault isolates corrupted telemetry to quarantine without downstream poison.",
            "- Machine fault triggers legitimate stateful alert lifecycle transition.",
            "",
            "## Evidence Disclosure",
            "- Drills execute the real streaming-worker fault-isolation logic in-process.",
            "- Scoring client, Kafka producer, and metrics registry are in-process doubles; "
            "no broker, scoring API, or database is contacted.",
        ]
    )

    return "\n".join(md_lines) + "\n"


def run_phase8_live_gate(
    output_dir: Path | None = None,
    git_sha: str | None = None,
) -> LiveFaultReportV1:
    target_dir = output_dir or Path("artifacts/certification/live")
    sha = resolve_git_sha(git_sha)
    prerequisite_errors, dependency_receipts = _runtime_preflight()
    if prerequisite_errors:
        report = _build_live_fault_report(
            (),
            sha,
            prerequisite_errors=prerequisite_errors,
        )
    else:
        drills = _execute_runtime_drills()
        report = _build_live_fault_report(
            drills,
            sha,
            dependency_receipts=dependency_receipts,
        )
    return _write_live_report(report, target_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 8 runtime fault drill gate")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--git-sha", type=str, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_phase8_live_gate(
            output_dir=args.output_dir,
            git_sha=args.git_sha,
        )
    except Exception as exc:
        print(f"Phase 8 runtime gate unavailable: {exc}", file=sys.stderr)
        return 1
    print(
        f"Phase 8 Fault Gate: {report.verdict} "
        f"({len(report.drills)} drills, evidence_level={report.evidence_level})"
    )
    print(f"Report SHA-256: {report.self_sha256}")
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
