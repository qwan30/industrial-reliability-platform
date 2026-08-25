from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    make_asgi_app,
    start_http_server,
)

TELEMETRY_OUTCOMES = frozenset({"accepted", "duplicate", "quarantined"})
SEGMENT_BREAK_REASONS = frozenset({"gap", "ordering"})
SCORE_OUTCOMES = frozenset({"ok", "invalid_contract", "invalid_model", "unavailable"})
ALERT_ACTIONS = frozenset({"opened", "updated", "resolved", "reopened"})
KNOWN_DEPENDENCIES = frozenset({"postgres", "kafka", "scoring_api"})


def _require(value: str, allowed: frozenset[str], kind: str) -> str:
    if value not in allowed:
        raise ValueError(f"unsupported {kind}: {value}")
    return value


@dataclass(frozen=True)
class RuntimeMetrics:
    registry: CollectorRegistry
    dependency_ready: Gauge
    replay_session_failures: Counter
    kafka_consumer_lag: Gauge
    telemetry_events: Counter
    segment_breaks: Counter
    valid_windows: Counter
    window_coverage_ratio: Gauge
    score_requests: Counter
    score_latency: Histogram
    anomaly_score: Gauge
    anomaly_decisions: Counter
    alert_events: Counter
    alerts_active: Gauge
    feature_psi_max: Gauge

    def record_telemetry(self, outcome: str) -> None:
        val = _require(outcome, TELEMETRY_OUTCOMES, "telemetry outcome")
        self.telemetry_events.labels(outcome=val).inc()

    def record_segment_break(self, reason: str) -> None:
        val = _require(reason, SEGMENT_BREAK_REASONS, "segment break reason")
        self.segment_breaks.labels(reason=val).inc()

    def record_score_request(self, outcome: str, duration: float) -> None:
        val = _require(outcome, SCORE_OUTCOMES, "score outcome")
        self.score_requests.labels(outcome=val).inc()
        if duration >= 0.0:
            self.score_latency.observe(duration)

    def record_alert_action(self, action: str) -> None:
        val = _require(action, ALERT_ACTIONS, "alert action")
        self.alert_events.labels(action=val).inc()

    def set_dependency_ready(self, dependency: str, ready: bool) -> None:
        val = _require(dependency, KNOWN_DEPENDENCIES, "dependency")
        self.dependency_ready.labels(dependency=val).set(1.0 if ready else 0.0)

    def set_consumer_lag(self, lag: float) -> None:
        self.kafka_consumer_lag.set(max(0.0, float(lag)))

    def record_valid_window(self, coverage_ratio: float) -> None:
        self.valid_windows.inc()
        self.window_coverage_ratio.set(max(0.0, min(1.0, float(coverage_ratio))))

    def record_anomaly_decision(self, score: float, is_anomaly: bool) -> None:
        self.anomaly_score.set(float(score))
        if is_anomaly:
            self.anomaly_decisions.inc()

    def set_active_alerts(self, count: int) -> None:
        self.alerts_active.set(max(0.0, float(count)))

    def set_feature_psi_max(self, psi: float) -> None:
        self.feature_psi_max.set(max(0.0, float(psi)))

    def record_replay_session_failure(self, error_code: str) -> None:
        # Bounded error code label
        self.replay_session_failures.labels(error_code=str(error_code)).inc()


def build_runtime_metrics(registry: CollectorRegistry | None = None) -> RuntimeMetrics:
    reg = registry if registry is not None else CollectorRegistry()

    dependency_ready = Gauge(
        "irp_dependency_ready",
        "Readiness state of external system dependencies (1=ready, 0=not ready)",
        ["dependency"],
        registry=reg,
    )
    replay_session_failures = Counter(
        "irp_replay_session_failures_total",
        "Total number of failed replay sessions by error code",
        ["error_code"],
        registry=reg,
    )
    kafka_consumer_lag = Gauge(
        "irp_kafka_consumer_lag",
        "Kafka consumer lag in records",
        registry=reg,
    )
    telemetry_events = Counter(
        "irp_telemetry_events_total",
        "Total number of ingested telemetry events by outcome",
        ["outcome"],
        registry=reg,
    )
    segment_breaks = Counter(
        "irp_segment_breaks_total",
        "Total number of time-series window segment breaks by reason",
        ["reason"],
        registry=reg,
    )
    valid_windows = Counter(
        "irp_valid_windows_total",
        "Total number of valid feature windows generated",
        registry=reg,
    )
    window_coverage_ratio = Gauge(
        "irp_window_coverage_ratio",
        "Telemetry sample coverage ratio in the most recent feature window",
        registry=reg,
    )
    score_requests = Counter(
        "irp_score_requests_total",
        "Total scoring requests by outcome",
        ["outcome"],
        registry=reg,
    )
    score_latency = Histogram(
        "irp_score_latency_seconds",
        "Scoring request duration in seconds",
        registry=reg,
    )
    anomaly_score = Gauge(
        "irp_anomaly_score",
        "Most recent anomaly score emitted by champion detector",
        registry=reg,
    )
    anomaly_decisions = Counter(
        "irp_anomaly_decisions_total",
        "Total positive anomaly decisions emitted",
        registry=reg,
    )
    alert_events = Counter(
        "irp_alert_events_total",
        "Total alert state transitions by action",
        ["action"],
        registry=reg,
    )
    alerts_active = Gauge(
        "irp_alerts_active",
        "Current count of active open/escalated alerts",
        registry=reg,
    )
    feature_psi_max = Gauge(
        "irp_feature_psi_max",
        "Maximum Population Stability Index across active features vs train reference",
        registry=reg,
    )

    return RuntimeMetrics(
        registry=reg,
        dependency_ready=dependency_ready,
        replay_session_failures=replay_session_failures,
        kafka_consumer_lag=kafka_consumer_lag,
        telemetry_events=telemetry_events,
        segment_breaks=segment_breaks,
        valid_windows=valid_windows,
        window_coverage_ratio=window_coverage_ratio,
        score_requests=score_requests,
        score_latency=score_latency,
        anomaly_score=anomaly_score,
        anomaly_decisions=anomaly_decisions,
        alert_events=alert_events,
        alerts_active=alerts_active,
        feature_psi_max=feature_psi_max,
    )


def mount_api_metrics(app: FastAPI, metrics: RuntimeMetrics) -> None:
    metrics_app = make_asgi_app(registry=metrics.registry)
    app.mount("/metrics", metrics_app)


def start_process_metrics(port: int, registry: CollectorRegistry) -> Any:
    # Starts Prometheus HTTP server on port binding to 0.0.0.0 for container network
    return start_http_server(port, addr="0.0.0.0", registry=registry)
