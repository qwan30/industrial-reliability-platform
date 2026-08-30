from __future__ import annotations

import argparse
import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    name: str
    path: Path
    sha256: str


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_migrations(path: Path) -> tuple[Migration, ...]:
    return tuple(
        Migration(name=file.name, path=file, sha256=sha256_file(file))
        for file in sorted(path.glob("[0-9][0-9][0-9]_*.sql"))
        if file.is_file()
    )


def apply_migrations(db_url: str, path: Path) -> tuple[str, ...]:
    applied: list[str] = []
    with psycopg.connect(db_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              name text PRIMARY KEY,
              sha256 char(64) NOT NULL,
              applied_at timestamptz NOT NULL DEFAULT now()
            );
            """
        )
        for migration in discover_migrations(path):
            cursor.execute(
                "SELECT sha256 FROM schema_migrations WHERE name = %s",
                (migration.name,),
            )
            row = cursor.fetchone()
            if row and row[0] != migration.sha256:
                raise MigrationError(f"migration checksum changed: {migration.name}")
            if row:
                continue
            cursor.execute(migration.path.read_text(encoding="utf-8"))
            cursor.execute(
                "INSERT INTO schema_migrations (name, sha256) VALUES (%s, %s)",
                (migration.name, migration.sha256),
            )
            applied.append(migration.name)
        connection.commit()
    return tuple(applied)


def main(argv: list[str] | Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply ordered IRP database migrations")
    default_url = os.environ.get(
        "DATABASE_URL", "postgresql://irp:irp_password@localhost:5432/irp"
    )
    parser.add_argument(
        "--database-url",
        default=default_url,
        help="PostgreSQL database connection URL",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("db/migrations"),
        help="Directory containing migration SQL files",
    )
    args = parser.parse_args(argv)
    applied = apply_migrations(args.database_url, args.path)
    for name in applied:
        print(f"Applied migration: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
