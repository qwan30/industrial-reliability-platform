from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from industrial_reliability.migrations import (
    Migration,
    MigrationError,
    apply_migrations,
    discover_migrations,
    main,
)


def copy_migrations(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for file in src.glob("[0-9][0-9][0-9]_*.sql"):
        shutil.copy2(file, dst / file.name)


class FakeCursor:
    def __init__(self, db_state: dict[str, str]) -> None:
        self.db_state = db_state
        self._last_result: tuple[str] | None = None
        self.executed_statements: list[str] = []

    def execute(self, query: str, params: tuple | None = None) -> None:
        self.executed_statements.append(query)
        normalized = " ".join(query.split())
        if "SELECT sha256 FROM schema_migrations WHERE name = %s" in normalized:
            assert params is not None
            name = params[0]
            if name in self.db_state:
                self._last_result = (self.db_state[name],)
            else:
                self._last_result = None
        elif "INSERT INTO schema_migrations" in normalized:
            assert params is not None
            name, sha256 = params[0], params[1]
            self.db_state[name] = sha256
            self._last_result = None
        else:
            self._last_result = None

    def fetchone(self) -> tuple[str] | None:
        return self._last_result

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


class FakeConnection:
    def __init__(self, db_state: dict[str, str]) -> None:
        self.db_state = db_state
        self.committed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.db_state)

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


def test_discover_migrations_is_ordered_and_hashed() -> None:
    migrations = discover_migrations(Path("db/migrations"))
    assert len(migrations) >= 4
    assert [item.name for item in migrations] == sorted(item.name for item in migrations)
    assert migrations[-1].name == "004_alert_runtime_state.sql"
    assert all(len(item.sha256) == 64 for item in migrations)
    assert all(isinstance(item, Migration) for item in migrations)
    for item in migrations:
        expected_sha = hashlib.sha256(item.path.read_bytes()).hexdigest()
        assert item.sha256 == expected_sha


def test_discover_migrations_filtering_and_sorting(tmp_path: Path) -> None:
    (tmp_path / "002_second.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "003_third.sql").write_text("SELECT 3;", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("IGNORE", encoding="utf-8")
    (tmp_path / "not_a_migration.sql").write_text("IGNORE", encoding="utf-8")

    migrations = discover_migrations(tmp_path)
    assert len(migrations) == 3
    assert [m.name for m in migrations] == ["001_first.sql", "002_second.sql", "003_third.sql"]
    assert migrations[0].sha256 == hashlib.sha256(b"SELECT 1;").hexdigest()
    assert migrations[0].path == tmp_path / "001_first.sql"


def test_apply_migrations_idempotent(tmp_path: Path) -> None:
    copy_migrations(Path("db/migrations"), tmp_path)
    db_state: dict[str, str] = {}

    def fake_connect(db_url: str):
        return FakeConnection(db_state)

    with patch("psycopg.connect", side_effect=fake_connect):
        first_applied = apply_migrations("postgresql://test:test@localhost:5432/test", tmp_path)
        assert len(first_applied) == 4
        assert first_applied == (
            "001_alert_lifecycle.sql",
            "002_console_stream.sql",
            "003_rca_reports.sql",
            "004_alert_runtime_state.sql",
        )
        assert len(db_state) == 4

        second_applied = apply_migrations("postgresql://test:test@localhost:5432/test", tmp_path)
        assert second_applied == ()
        assert len(db_state) == 4


def test_changed_applied_migration_fails(tmp_path: Path) -> None:
    copy_migrations(Path("db/migrations"), tmp_path)
    db_state: dict[str, str] = {}

    def fake_connect(db_url: str):
        return FakeConnection(db_state)

    with patch("psycopg.connect", side_effect=fake_connect):
        apply_migrations("postgresql://test:test@localhost:5432/test", tmp_path)

        changed = tmp_path / "001_alert_lifecycle.sql"
        changed.write_text(changed.read_text(encoding="utf-8") + "\nSELECT 1;\n", encoding="utf-8")

        with pytest.raises(MigrationError, match="migration checksum changed: 001_alert_lifecycle.sql"):
            apply_migrations("postgresql://test:test@localhost:5432/test", tmp_path)


def test_cli_main(tmp_path: Path) -> None:
    copy_migrations(Path("db/migrations"), tmp_path)
    db_state: dict[str, str] = {}

    def fake_connect(db_url: str):
        return FakeConnection(db_state)

    with patch("psycopg.connect", side_effect=fake_connect):
        exit_code = main(["--database-url", "postgresql://test:test@localhost:5432/test", "--path", str(tmp_path)])
        assert exit_code == 0
