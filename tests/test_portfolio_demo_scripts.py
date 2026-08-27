from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from deploy.preflight import (
    DEFAULT_PREFLIGHT_CONFIG,
    verify_host_environment,
)
from deploy.preflight import (
    main as preflight_main,
)


def test_preflight_default_config_ports() -> None:
    assert 5173 in DEFAULT_PREFLIGHT_CONFIG.required_ports
    assert 29092 in DEFAULT_PREFLIGHT_CONFIG.required_ports
    assert 8000 in DEFAULT_PREFLIGHT_CONFIG.required_ports
    assert 5432 in DEFAULT_PREFLIGHT_CONFIG.required_ports
    assert 9090 in DEFAULT_PREFLIGHT_CONFIG.required_ports
    assert 3001 in DEFAULT_PREFLIGHT_CONFIG.required_ports
    assert 5000 in DEFAULT_PREFLIGHT_CONFIG.required_ports


def test_preflight_verifies_ram_and_disk_passes() -> None:
    with (
        patch("deploy.preflight.psutil") as mock_psutil,
        patch(
            "deploy.preflight.shutil.disk_usage",
            return_value=(100 * 1024**3, 50 * 1024**3, 50 * 1024**3),
        ),
        patch("deploy.preflight.shutil.which", return_value="docker"),
        patch("deploy.preflight.subprocess.run") as mock_subproc,
        patch("socket.socket") as mock_sock,
    ):
        mock_psutil.virtual_memory.return_value = MagicMock(available=8 * 1024**3)
        mock_subproc.return_value = MagicMock(returncode=0)
        mock_sock_inst = MagicMock()
        mock_sock_inst.connect_ex.return_value = 1  # Port free
        mock_sock.return_value.__enter__.return_value = mock_sock_inst

        result = verify_host_environment()
        assert result.passed is True
        assert len(result.errors) == 0


def test_preflight_fails_on_low_memory_or_disk() -> None:
    with (
        patch("deploy.preflight.psutil") as mock_psutil,
        patch(
            "deploy.preflight.shutil.disk_usage",
            return_value=(100 * 1024**3, 98 * 1024**3, 2 * 1024**3),
        ),  # 2GB free < 10GB
        patch("socket.socket") as mock_sock,
    ):
        mock_psutil.virtual_memory.return_value = MagicMock(available=1 * 1024**3)  # 1GB free < 4GB
        mock_sock_inst = MagicMock()
        mock_sock_inst.connect_ex.return_value = 1
        mock_sock.return_value.__enter__.return_value = mock_sock_inst

        result = verify_host_environment()
        assert result.passed is False
        assert any("RAM" in err for err in result.errors)
        assert any("Disk" in err for err in result.errors)


def test_preflight_require_clean_ports_flag() -> None:
    with (
        patch("deploy.preflight.psutil") as mock_psutil,
        patch(
            "deploy.preflight.shutil.disk_usage",
            return_value=(100 * 1024**3, 50 * 1024**3, 50 * 1024**3),
        ),
        patch("deploy.preflight.shutil.which", return_value="docker"),
        patch("deploy.preflight.subprocess.run") as mock_subproc,
        patch("socket.socket") as mock_sock,
    ):
        mock_psutil.virtual_memory.return_value = MagicMock(available=8 * 1024**3)
        mock_subproc.return_value = MagicMock(returncode=0)
        mock_sock_inst = MagicMock()
        mock_sock_inst.connect_ex.return_value = 0  # Port is bound
        mock_sock.return_value.__enter__.return_value = mock_sock_inst

        # By default, bound ports are warnings, not errors
        res_warn = verify_host_environment(require_clean_ports=False)
        assert res_warn.passed is True
        assert len(res_warn.warnings) > 0

        # With require_clean_ports=True, bound ports are errors
        res_err = verify_host_environment(require_clean_ports=True)
        assert res_err.passed is False
        assert len(res_err.errors) > 0


def test_preflight_cli_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("deploy.preflight.psutil") as mock_psutil,
        patch(
            "deploy.preflight.shutil.disk_usage",
            return_value=(100 * 1024**3, 50 * 1024**3, 50 * 1024**3),
        ),
        patch("deploy.preflight.shutil.which", return_value="docker"),
        patch("deploy.preflight.subprocess.run") as mock_subproc,
        patch("socket.socket") as mock_sock,
    ):
        mock_psutil.virtual_memory.return_value = MagicMock(available=8 * 1024**3)
        mock_subproc.return_value = MagicMock(returncode=0)
        mock_sock_inst = MagicMock()
        mock_sock_inst.connect_ex.return_value = 1
        mock_sock.return_value.__enter__.return_value = mock_sock_inst

        code = preflight_main(["--json"])
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["passed"] is True
        assert "errors" in data
        assert "warnings" in data


def test_portfolio_demo_script_structure() -> None:
    script_path = Path("scripts/run_portfolio_demo.ps1")
    assert script_path.exists(), "scripts/run_portfolio_demo.ps1 must exist"
    content = script_path.read_text(encoding="utf-8")
    assert "deploy/preflight.py" in content or "deploy\\preflight.py" in content
    assert "http://127.0.0.1:5173" in content
    assert "http://127.0.0.1:8000" in content
    assert "http://127.0.0.1:9090" in content
    assert "http://127.0.0.1:3001" in content
    assert "http://127.0.0.1:5000" in content
