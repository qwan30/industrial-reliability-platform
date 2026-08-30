from __future__ import annotations

from pathlib import Path


def test_prometheus_alert_rules_definition() -> None:
    alerts_path = Path("ops/prometheus/alerts.yml").resolve()
    assert alerts_path.is_file(), "ops/prometheus/alerts.yml must exist"

    text = alerts_path.read_text(encoding="utf-8")
    assert "industrial-reliability-data" in text
    assert "IRPQuarantineDetected" in text
    assert 'increase(irp_telemetry_events_total{outcome="quarantined"}[5m]) > 0' in text
    assert "IRPKafkaConsumerLag" in text
    assert "irp_kafka_consumer_lag > 1000" in text
    assert "IRPWindowCoverageLow" in text
    assert "irp_window_coverage_ratio < 0.8" in text
    assert "IRPFeatureDriftHigh" in text
    assert "irp_feature_psi_max >= 0.2" in text


def test_prometheus_config_includes_rule_files() -> None:
    prom_path = Path("ops/prometheus/prometheus.yml").resolve()
    assert prom_path.is_file()

    text = prom_path.read_text(encoding="utf-8")
    assert "rule_files:" in text
    assert "/etc/prometheus/alerts.yml" in text


def test_compose_mounts_alerts_and_configures_drift_path() -> None:
    compose_path = Path("compose.yaml").resolve()
    assert compose_path.is_file()

    text = compose_path.read_text(encoding="utf-8")
    assert "./ops/prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro" in text
    assert "DRIFT_REFERENCE_PATH: /runtime/scoring-package/drift-reference.json" in text
