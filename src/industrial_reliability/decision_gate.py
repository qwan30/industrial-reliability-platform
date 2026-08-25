from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

DecisionStatus = Literal["ADOPTED", "NOT_ADOPTED", "N/A"]


def _canonical_json(data: Any) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o),
    ).encode("utf-8")


def canonical_sha256(data: dict[str, Any]) -> str:
    copy_data = dict(data)
    copy_data.pop("decision_sha256", None)
    return hashlib.sha256(_canonical_json(copy_data)).hexdigest()


@dataclass(frozen=True)
class ReplayBenchmarkResultV1:
    schema_version: str
    implementation: str
    git_sha: str
    champion_sha256: str
    contract_sha256: str
    source_dataset_sha256: str
    workload_sha256: str
    repetitions: int
    source_events: int
    valid_windows: int
    feature_digest: str
    score_digest: str
    alert_digest: str
    duplicate_rows: int
    quarantine_rows: int
    p50_latency_ms: float
    p95_latency_ms: float
    throughput_events_per_second: float
    max_consumer_lag: float
    lag_drain_seconds: float
    cpu_seconds_per_million_events: float
    peak_rss_bytes: int
    restart_recovery_passed: bool

    def __post_init__(self) -> None:
        for name, val in [
            ("p50_latency_ms", self.p50_latency_ms),
            ("p95_latency_ms", self.p95_latency_ms),
            ("throughput_events_per_second", self.throughput_events_per_second),
            ("max_consumer_lag", self.max_consumer_lag),
            ("lag_drain_seconds", self.lag_drain_seconds),
            ("cpu_seconds_per_million_events", self.cpu_seconds_per_million_events),
        ]:
            if not math.isfinite(val) or val < 0:
                raise ValueError(f"Metric {name} must be a non-negative finite float, got {val}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OptionalTechnologyDecisionV1:
    schema_version: str
    technology: str
    status: DecisionStatus
    git_sha: str
    champion_sha256: str | None
    contract_sha256: str | None
    source_dataset_sha256: str | None
    reason_codes: tuple[str, ...]
    baseline: ReplayBenchmarkResultV1 | None
    candidate: ReplayBenchmarkResultV1 | None
    parity_passed: bool | None
    benefit_passed: bool | None
    limitations: tuple[str, ...]
    decision_sha256: str = ""

    def __post_init__(self) -> None:
        if self.status == "ADOPTED":
            if self.candidate is None:
                raise ValueError("ADOPTED decision requires candidate evidence")
            if self.parity_passed is not True or self.benefit_passed is not True:
                raise ValueError("ADOPTED decision requires both parity and benefit to be True")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.baseline:
            d["baseline"] = self.baseline.to_dict()
        if self.candidate:
            d["candidate"] = self.candidate.to_dict()
        return d


def write_decision(
    decision: OptionalTechnologyDecisionV1,
    output: Path,
) -> Path:
    d = decision.to_dict()
    computed_sha = canonical_sha256(d)
    d["decision_sha256"] = computed_sha

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_file = output.with_suffix(f".tmp.{output.suffix}")
    temp_file.write_text(json.dumps(d, indent=2), encoding="utf-8")
    temp_file.replace(output)
    return output
