# CI test-helper import fix

## Scope

Clean head: `bf073e49c7f1e0cd9050c74485a8662ca9e101c5`.

Linux CI failed during pytest collection because `tests` was not an explicit
package. The smallest fix is `tests/__init__.py`; no pipeline, data, artifact,
contract, or benchmark-result files changed.

## RED evidence

Remote Linux CI evidence recorded in the SDD ledger:

```text
ImportError while loading tests/conftest.py
tests/conftest.py:9: in <module>
    from tests.helpers import write_sample_csv
E   ModuleNotFoundError: No module named 'tests.helpers'
```

The local SDD ledger was not present in this worktree, so the supplied remote
failure is quoted verbatim at its known failure boundary. Before the fix, the
new targeted test reached collection locally but this machine's default
Python 3.9 lacked `numpy`; the project Python 3.12 environment was used for
the final gates.

## Change and regression coverage

- Added `tests/__init__.py` to make `tests.helpers` an unambiguous package
  import in CI.
- Added `tests/test_test_helpers_package.py`, which imports `tests.helpers`
  and verifies the shared CSV helper is provided by that package.

## GREEN verification

Run from the worktree using `.venv\\Scripts\\python.exe` (Python 3.12.10):

```text
python -m pytest tests/test_test_helpers_package.py -q --no-cov
1 passed in 0.02s

python -m pytest -m "not slow"
155 passed, 1 deselected in 18.35s
Required test coverage of 80% reached. Total coverage: 92.25%

python -m ruff check .
All checks passed!

python -m ruff format --check .
29 files already formatted

python -m mypy src
Success: no issues found in 8 source files

python -m pip check
No broken requirements found.

python -m build --outdir <temporary directory>
Successfully built industrial_reliability_platform-0.1.0.tar.gz and
industrial_reliability_platform-0.1.0-py3-none-any.whl

git diff --check
exit 0
```
