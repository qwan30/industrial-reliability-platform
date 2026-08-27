from __future__ import annotations

import argparse
import json
import shutil
import socket
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass

try:
    import psutil
except ImportError:
    psutil = None


@dataclass(frozen=True)
class PreflightConfig:
    min_memory_gb: float = 4.0
    min_disk_gb: float = 10.0
    required_ports: tuple[int, ...] = (8000, 3000, 5432, 9092, 9090, 5000, 9102, 9103)


@dataclass(frozen=True)
class PreflightResult:
    passed: bool
    errors: list[str]
    warnings: list[str]


DEFAULT_PREFLIGHT_CONFIG = PreflightConfig()


def verify_host_environment(
    config: PreflightConfig | None = None,
    require_clean_ports: bool = False,
) -> PreflightResult:
    active_config = config or DEFAULT_PREFLIGHT_CONFIG
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Check RAM if psutil is available
    if psutil is not None:
        vm = psutil.virtual_memory()
        available_gb = vm.available / (1024**3)
        if available_gb < active_config.min_memory_gb:
            errors.append(
                f"Insufficient RAM: {available_gb:.1f}GB available, {active_config.min_memory_gb}GB required."
            )
    else:
        warnings.append("psutil not installed; skipping detailed RAM verification.")

    # 2. Check Disk
    _, _, free = shutil.disk_usage(".")
    free_gb = free / (1024**3)
    if free_gb < active_config.min_disk_gb:
        errors.append(
            f"Insufficient Disk Space: {free_gb:.1f}GB free, {active_config.min_disk_gb}GB required."
        )

    # 3. Check Ports
    for port in active_config.required_ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                msg = f"Port {port} is currently bound / in use."
                if require_clean_ports:
                    errors.append(msg)
                else:
                    warnings.append(msg)

    return PreflightResult(passed=len(errors) == 0, errors=errors, warnings=warnings)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preflight check for Industrial Reliability Platform"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument(
        "--require-clean-ports",
        action="store_true",
        help="Treat bound ports as fatal errors instead of warnings",
    )
    args = parser.parse_args(argv)

    res = verify_host_environment(require_clean_ports=args.require_clean_ports)

    if args.json:
        print(json.dumps(asdict(res), indent=2))
    else:
        print(f"Preflight Environment Status: {'PASS' if res.passed else 'FAIL'}")
        if res.errors:
            print("Errors:")
            for err in res.errors:
                print(f" - {err}")
        if res.warnings:
            print("Warnings:")
            for w in res.warnings:
                print(f" - {w}")

    return 0 if res.passed else 1


if __name__ == "__main__":
    sys.exit(main())
