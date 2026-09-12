from __future__ import annotations

from unittest.mock import Mock

import pytest
from deploy.preflight import PreflightConfig, verify_host_environment


def test_preflight_checks_required_ports_and_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.disk_usage", lambda _: (100 * 1024**3, 50 * 1024**3, 50 * 1024**3))
    mock_psutil = Mock()
    mock_psutil.virtual_memory.return_value = Mock(available=8 * 1024**3)
    monkeypatch.setattr("deploy.preflight.psutil", mock_psutil)

    result = verify_host_environment(
        PreflightConfig(min_memory_gb=4, min_disk_gb=10, required_paths=())
    )
    assert result.passed is True
    assert len(result.errors) == 0


def test_preflight_fails_on_low_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.disk_usage", lambda _: (100 * 1024**3, 50 * 1024**3, 50 * 1024**3))
    mock_psutil = Mock()
    mock_psutil.virtual_memory.return_value = Mock(available=1 * 1024**3)
    monkeypatch.setattr("deploy.preflight.psutil", mock_psutil)
    result = verify_host_environment(
        PreflightConfig(min_memory_gb=4, min_disk_gb=10, required_paths=())
    )
    assert result.passed is False
    assert any("ram" in err.lower() or "memory" in err.lower() for err in result.errors)


def test_default_preflight_uses_compose_ports() -> None:
    from deploy.preflight import DEFAULT_PREFLIGHT_CONFIG

    assert DEFAULT_PREFLIGHT_CONFIG.required_ports == (8000, 5173, 5432, 29092, 9090, 3001, 5000)


def test_preflight_fails_without_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("deploy.preflight.shutil.which", lambda _: None)
    result = verify_host_environment(
        PreflightConfig(required_ports=(), required_paths=(), check_artifacts=False)
    )
    assert result.passed is False
    assert "Docker CLI" in result.errors[0]


def test_preflight_fails_on_missing_required_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.disk_usage", lambda _: (100 * 1024**3, 50 * 1024**3, 50 * 1024**3))
    mock_psutil = Mock()
    mock_psutil.virtual_memory.return_value = Mock(available=8 * 1024**3)
    monkeypatch.setattr("deploy.preflight.psutil", mock_psutil)
    monkeypatch.setattr("deploy.preflight.shutil.which", lambda _: "docker")
    result = verify_host_environment(
        PreflightConfig(required_ports=(), required_paths=("missing-compose.yaml",))
    )
    assert result.passed is False
    assert any("Required path missing: missing-compose.yaml" in error for error in result.errors)
