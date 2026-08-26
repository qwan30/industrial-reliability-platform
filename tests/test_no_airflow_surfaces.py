from __future__ import annotations

import tomllib
from pathlib import Path


def test_repository_has_no_airflow_runtime_surface() -> None:
    # 1. Verify pyproject dependencies
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.is_file()
    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dependencies = project["project"].get("dependencies", [])
    extras = [
        item
        for group in project["project"].get("optional-dependencies", {}).values()
        for item in group
    ]
    all_deps = [*dependencies, *extras]
    assert all("airflow" not in item.lower() for item in all_deps), (
        f"Found airflow in dependencies: {all_deps}"
    )

    # 2. Verify docker compose services
    compose_path = Path("compose.yaml")
    assert compose_path.is_file()
    compose_text = compose_path.read_text(encoding="utf-8")
    assert "airflow" not in compose_text.lower(), "Found airflow in compose.yaml"

    # 3. Verify no DAGs or airflow dirs exist
    assert not Path("airflow").exists()
    assert not Path("dags").exists()

    # 4. Verify ADR exists
    assert Path("docs/decisions/2026-08-24-airflow-not-adopted.md").is_file()
