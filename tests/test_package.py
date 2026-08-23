"""Smoke tests for the industrial_reliability package."""

from __future__ import annotations

import industrial_reliability


def test_package_exposes_version() -> None:
    assert isinstance(industrial_reliability.__version__, str)
    assert industrial_reliability.__version__ != ""
