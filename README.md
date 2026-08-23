# Industrial Reliability Platform

Production-oriented industrial anomaly detection and reliability intelligence platform.

> **Status:** Phase 0 — repository scaffold and CI quality pipeline.
> Master specification: `docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md`

## Development setup

Requires Python 3.12.

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Quality checks

The same checks CI runs on every push and pull request:

```bash
ruff check .
ruff format --check .
mypy src
pytest -m "not slow"
pip check
python -m build
```

## Project layout

```text
src/industrial_reliability/   # package source (grows with each phase)
tests/                        # test suite
docs/                         # specifications and research notes
references/                   # local-only reference repositories (git-ignored)
data/                         # local-only datasets (git-ignored)
```

## License

MIT — see [LICENSE](LICENSE).
