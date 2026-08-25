from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def generate_release_manifest(root: Path, output_file: Path | None = None) -> Path:
    checksums: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_file():
            if p.name in ("release-manifest.json", "release_manifest.json"):
                continue
            # Skip hidden dirs, virtualenvs, caches and build artifacts
            if any(
                part.startswith(".")
                or part in ("node_modules", "dist", "build", "__pycache__", "venv", ".venv")
                for part in p.parts
            ):
                continue
            rel_str = str(p.relative_to(root)).replace("\\", "/")
            checksums[rel_str] = hashlib.sha256(p.read_bytes()).hexdigest()

    manifest_path = output_file or (root / "release_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"schema_version": "release-manifest-v1", "checksums": checksums},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return manifest_path


def verify_release_manifest(manifest_path: Path, root: Path | None = None) -> bool:
    base_root = (
        root
        if root is not None
        else (manifest_path.parent if manifest_path.parent != Path("docs/results") else Path("."))
    )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rel_path, expected_hash in data.get("checksums", {}).items():
        file_path = base_root / rel_path
        if (
            not file_path.exists()
            or hashlib.sha256(file_path.read_bytes()).hexdigest() != expected_hash
        ):
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package Release Manifest")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("docs/results/release-manifest.json"))
    parser.add_argument("--verify", action="store_true")

    args = parser.parse_args(argv)
    if args.verify:
        ok = verify_release_manifest(args.output, root=args.root)
        print(f"Release manifest verification: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1

    path = generate_release_manifest(args.root, output_file=args.output)
    print(f"Release manifest generated at {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
