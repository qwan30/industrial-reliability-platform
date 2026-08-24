import json
import subprocess
import tomllib
from pathlib import Path

import pytest


@pytest.mark.integration
def test_mlflow_service_is_local_and_persistent() -> None:
    config = json.loads(
        subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    service = config["services"]["mlflow"]
    assert service["ports"][0]["host_ip"] == "127.0.0.1"
    assert service["environment"]["MLFLOW_BACKEND_STORE_URI"].startswith("postgresql+psycopg://")
    assert service["build"]["dockerfile"] == "docker/mlflow.Dockerfile"
    assert "mlflow-artifacts" in json.dumps(service["volumes"])
    core = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    assert all(not dependency.startswith("mlflow") for dependency in core)
    mlops = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]["mlops"]
    assert any(dependency.startswith("mlflow") for dependency in mlops)
