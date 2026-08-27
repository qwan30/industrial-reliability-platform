from __future__ import annotations

import json
from pathlib import Path


def test_prometheus_configuration_syntax() -> None:
    prom_path = Path("ops/prometheus/prometheus.yml").resolve()
    assert prom_path.is_file(), "prometheus.yml must exist"

    text = prom_path.read_text(encoding="utf-8")
    assert "scoring-api:8000" in text
    assert "replay-producer:9101" in text
    assert "streaming-worker:9102" in text
    assert "scrape_interval" in text


def test_grafana_dashboard_definitions() -> None:
    dashboards_dir = Path("ops/grafana/dashboards").resolve()
    assert dashboards_dir.is_dir(), "ops/grafana/dashboards must exist"

    system_json = dashboards_dir / "system.json"
    data_quality_json = dashboards_dir / "data-quality.json"
    model_machine_json = dashboards_dir / "model-machine.json"

    assert system_json.is_file()
    assert data_quality_json.is_file()
    assert model_machine_json.is_file()

    sys_data = json.loads(system_json.read_text(encoding="utf-8"))
    assert sys_data["uid"] == "irp-system"

    dq_data = json.loads(data_quality_json.read_text(encoding="utf-8"))
    assert dq_data["uid"] == "irp-data-quality"

    mm_data = json.loads(model_machine_json.read_text(encoding="utf-8"))
    assert mm_data["uid"] == "irp-model-machine"
    # Verify the required disclaimer text in model-machine dashboard
    mm_text = model_machine_json.read_text(encoding="utf-8")
    assert "Drift is not a failure diagnosis" in mm_text


def test_compose_ports_bind_strictly_to_localhost() -> None:
    compose_path = Path("compose.yaml").resolve()
    assert compose_path.is_file()
    text = compose_path.read_text(encoding="utf-8")

    # SEC-02 check: All published host ports must explicitly specify 127.0.0.1
    # Check for prometheus and grafana
    assert "127.0.0.1:9090:9090" in text
    assert "127.0.0.1:3001:3000" in text


def test_deployed_console_proxies_to_scoring_api() -> None:
    nginx = Path("apps/operator-console/nginx.conf").read_text(encoding="utf-8")
    assert "http://scoring-api:8000" in nginx
    assert "http://api:8000" not in nginx


def test_compose_passes_optional_rca_settings() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    assert "RCA_OPENAI_API_KEY: ${RCA_OPENAI_API_KEY:-}" in compose
    assert "RCA_OPENAI_MODEL: ${RCA_OPENAI_MODEL:-}" in compose
    assert "RCA_TIMEOUT_SECONDS: ${RCA_TIMEOUT_SECONDS:-20}" in compose


def test_prometheus_scrapes_alert_service() -> None:
    config = Path("ops/prometheus/prometheus.yml").read_text(encoding="utf-8")
    assert 'job_name: "alert-service"' in config
    assert 'targets: ["alert-service:9103"]' in config
