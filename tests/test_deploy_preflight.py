from __future__ import annotations

from unittest.mock import Mock

import pytest
from deploy.preflight import PreflightConfig, verify_host_environment


def test_preflight_checks_required_ports_and_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.disk_usage", lambda _: (100 * 1024**3, 50 * 1024**3, 50 * 1024**3))
    mock_psutil = Mock()
    mock_psutil.virtual_memory.return_value = Mock(available=8 * 1024**3)
    monkeypatch.setattr("deploy.preflight.psutil", mock_psutil)

    result = verify_host_environment(PreflightConfig(min_memory_gb=4, min_disk_gb=10))
    assert result.passed is True
    assert len(result.errors) == 0


def test_preflight_fails_on_low_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.disk_usage", lambda _: (100 * 1024**3, 50 * 1024**3, 50 * 1024**3))
    mock_psutil = Mock()
    mock_psutil.virtual_memory.return_value = Mock(available=1 * 1024**3)
    monkeypatch.setattr("deploy.preflight.psutil", mock_psutil)
    result = verify_host_environment(PreflightConfig(min_memory_gb=4, min_disk_gb=10))
    assert result.passed is False
    assert any("ram" in err.lower() or "memory" in err.lower() for err in result.errors)
