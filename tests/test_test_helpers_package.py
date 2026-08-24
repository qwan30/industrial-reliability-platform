"""Regression coverage for test-helper package imports."""

from __future__ import annotations

from importlib import import_module


def test_helpers_are_importable_as_a_package() -> None:
    """Keep the shared test helpers importable during pytest collection."""
    helpers = import_module("tests.helpers")

    assert helpers.write_sample_csv.__module__ == "tests.helpers"
