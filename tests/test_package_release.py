from __future__ import annotations

from pathlib import Path

from industrial_reliability.package_release import (
    generate_release_manifest,
    verify_release_manifest,
)


def test_generate_and_verify_release_manifest(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("sample content", encoding="utf-8")
    (tmp_path / "data.txt").write_text("data 123", encoding="utf-8")

    manifest = generate_release_manifest(tmp_path)
    assert manifest.is_file()
    assert verify_release_manifest(manifest) is True

    # Tamper with file
    (tmp_path / "data.txt").write_text("tampered", encoding="utf-8")
    assert verify_release_manifest(manifest) is False
