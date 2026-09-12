from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, replace
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
class ReplayBenchmarkSampleV1:
    repetition: int
    source_events: int
    valid_windows: int
    p50_latency_ms: float
    p95_latency_ms: float
    throughput_events_per_second: float
    max_consumer_lag: float
    lag_drain_seconds: float
    duplicate_rows: int
    quarantine_rows: int
    cpu_seconds: float
    peak_rss_bytes: int
    recovery_passed: bool
    timing_samples: tuple[dict[str, float], ...] = ()
    prometheus_samples: tuple[dict[str, float], ...] = ()
    container_samples: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        for name, val in [
            ("p50_latency_ms", self.p50_latency_ms),
            ("p95_latency_ms", self.p95_latency_ms),
            ("throughput_events_per_second", self.throughput_events_per_second),
            ("max_consumer_lag", self.max_consumer_lag),
            ("lag_drain_seconds", self.lag_drain_seconds),
            ("cpu_seconds", self.cpu_seconds),
        ]:
            if not math.isfinite(val) or val < 0:
                raise ValueError(
                    f"Sample metric {name} must be a non-negative finite float, got {val}"
                )

        if type(self.repetition) is not int or self.repetition <= 0:
            raise ValueError(
                f"Sample metric repetition must be a positive integer, got {self.repetition}"
            )
        for name, val in (
            ("source_events", self.source_events),
            ("valid_windows", self.valid_windows),
            ("duplicate_rows", self.duplicate_rows),
            ("quarantine_rows", self.quarantine_rows),
            ("peak_rss_bytes", self.peak_rss_bytes),
        ):
            if type(val) is not int or val < 0:
                raise ValueError(f"Sample metric {name} must be a non-negative integer, got {val}")
        if type(self.recovery_passed) is not bool:
            raise ValueError("Sample metric recovery_passed must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
class ReplayBenchmarkResultV2:
    schema_version: Literal["replay-benchmark-v2"]
    evidence_level: Literal["RUNTIME"]
    implementation: str
    git_sha: str
    champion_sha256: str
    contract_sha256: str
    source_dataset_sha256: str
    workload_sha256: str
    repetitions: int
    raw_samples: tuple[ReplayBenchmarkSampleV1, ...]
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
    regression_budget: None = None
    limitations: tuple[str, ...] = ("baseline only; no budget established",)
    self_sha256: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != "replay-benchmark-v2" or self.evidence_level != "RUNTIME":
            raise ValueError("ReplayBenchmarkResultV2 must be runtime evidence")
        if (
            not isinstance(self.git_sha, str)
            or not re.fullmatch(r"[0-9a-f]{40}", self.git_sha)
            or self.git_sha == "0" * 40
        ):
            raise ValueError("git_sha must be a non-zero lowercase 40-character SHA")
        for hash_name, hash_value in (
            ("champion_sha256", self.champion_sha256),
            ("contract_sha256", self.contract_sha256),
            ("source_dataset_sha256", self.source_dataset_sha256),
            ("workload_sha256", self.workload_sha256),
            ("feature_digest", self.feature_digest),
            ("score_digest", self.score_digest),
            ("alert_digest", self.alert_digest),
        ):
            if not isinstance(hash_value, str) or not re.fullmatch(r"[0-9a-f]{64}", hash_value):
                raise ValueError(f"{hash_name} must be a lowercase 64-character SHA-256")
        if self.repetitions <= 0 or len(self.raw_samples) != self.repetitions:
            raise ValueError("repetitions must equal the number of raw samples and be positive")
        if len({sample.repetition for sample in self.raw_samples}) != len(self.raw_samples):
            raise ValueError("raw sample repetition identifiers must be unique")
        for metric_name, metric_value in (
            ("p50_latency_ms", self.p50_latency_ms),
            ("p95_latency_ms", self.p95_latency_ms),
            ("throughput_events_per_second", self.throughput_events_per_second),
            ("max_consumer_lag", self.max_consumer_lag),
            ("lag_drain_seconds", self.lag_drain_seconds),
            ("cpu_seconds_per_million_events", self.cpu_seconds_per_million_events),
        ):
            if not math.isfinite(metric_value) or metric_value < 0:
                raise ValueError(f"Metric {metric_name} must be a non-negative finite float")
        for count_name, count_value in (
            ("source_events", self.source_events),
            ("valid_windows", self.valid_windows),
            ("duplicate_rows", self.duplicate_rows),
            ("quarantine_rows", self.quarantine_rows),
            ("peak_rss_bytes", self.peak_rss_bytes),
        ):
            if not isinstance(count_value, int) or count_value < 0:
                raise ValueError(f"Metric {count_name} must be a non-negative integer")
        if self.self_sha256 and not re.fullmatch(r"[0-9a-f]{64}", self.self_sha256):
            raise ValueError("self_sha256 must be a lowercase 64-character SHA-256")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def with_computed_hash(self) -> ReplayBenchmarkResultV2:
        payload = self.to_dict()
        payload["self_sha256"] = ""
        computed = hashlib.sha256(_canonical_json(payload)).hexdigest()
        return replace(self, self_sha256=computed)


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
