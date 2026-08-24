"""Shared fixtures for the industrial_reliability test suite."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.helpers import write_sample_csv


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Six source rows split by one missing second."""
    start = datetime(2022, 1, 1, 6)
    path = tmp_path / "sample.csv"
    write_sample_csv(
        path,
        [start + timedelta(seconds=offset) for offset in (0, 1, 2, 4, 5, 6)],
    )
    return path
