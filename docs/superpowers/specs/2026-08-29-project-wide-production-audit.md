# Project-Wide Production and Evidence Audit

**Status:** `BLOCK` — remediation not implemented

**Audit date:** 2026-08-29

**Current snapshot:** `main` / `origin/main` at `2d054c65db8ce63ff6aebbf48d472c5c0586b0fc`

**Change axis:** `300a13679be64457745676a36d0135093affde4b...2d054c65db8ce63ff6aebbf48d472c5c0586b0fc`

**Companion data audit:** [`docs/data-pipeline-audit-2026-08-29.md`](../../data-pipeline-audit-2026-08-29.md)

**Companion data remediation plan:** [`docs/superpowers/plans/2026-08-29-data-pipeline-audit-remediation.md`](../plans/2026-08-29-data-pipeline-audit-remediation.md)

## 1. Executive verdict

Production audit: **41/100, blocked**. The repository has strong unit coverage, typed contracts, a localhost-only Compose topology, and green exact-SHA CI. It is not a production-certified platform or a reproducible one-command live demo because release-grade evidence can still be self-declared by in-process checks, the public benchmark is generated from constants, the demo omits the deployed lifecycle, and a completed RCA can be returned after persistence fails.

The permanent scientific result remains truthful and unchanged: Phase 1B is **`NOT FEASIBLE`** with **`selected_model: null`**. Nothing in this audit authorizes rerunning or retuning the viewed holdout.

### Release decision

- **Local interview demo:** blocked until Gates A-C below pass.
- **Release certification:** invalid until fresh exact-SHA dependency-backed evidence exists.
- **Shared or internet exposure:** prohibited until Gate D passes.
- **Merge assessment for the reviewed hardening range:** not ready despite green CI.

## 2. Scope and method

This audit covers the current FastAPI API, RCA workflow, release/evidence gates, replay benchmark, portfolio runner, operator-console browser path, CI, Compose/deployment surface, documentation claims, and cross-cutting code standards. The companion data audit owns ingestion, lineage, split integrity, database lifecycle, promotion, data monitoring, and quarantine findings; those are referenced rather than duplicated here.

The review used three independent axes:

1. **Standards:** global ECC rules, `pyproject.toml`, CI, and documented repository behavior.
2. **Spec:** the 2026-08-27 hardening plan, roadmap, and earlier blocked review.
3. **Production:** runtime failure behavior, evidence provenance, deployment, browser coverage, security boundaries, and operator claims.

Every defect below is either reproduced by a deterministic local harness or tied to an exact current source/CI observation. No application code, historical artifact, Git state, or companion audit file was modified.

## 3. Evidence checked

| Evidence | Result |
|---|---|
| `git status --short --branch` | `main...origin/main`; companion audit and plan are untracked and preserved |
| `git diff 300a136...HEAD` | 57 files; 3,856 insertions; 482 deletions |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | Tracked code passes; only the user-owned untracked data remediation plan would be reformatted |
| `uv run mypy src` | PASS — 54 source files |
| `uv run python -m pip check` | PASS |
| `uv run pytest -m "not slow and not integration" --cov` | PASS — 450 passed, 1 PostgreSQL-dependent test skipped; 86.79% coverage |
| Operator-console Vitest/build | PASS — 45 tests and production build |
| `docker compose config --quiet` | PASS |
| Local Docker-backed/live checks | NOT RUN — Docker Desktop engine unavailable |
| Exact-SHA GitHub CI run `33097945787` | PASS — quality and integration jobs |
| Remote integration detail | 7 passed, 3 MLflow modules skipped because `mlflow` was not installed |
| Remote browser evidence | Mocked Playwright only; live project not invoked |
| `git diff --check 300a136...HEAD` | One blank line at EOF in the roadmap spec |

Green CI therefore proves static checks, unit/mocked behavior, and selected PostgreSQL/Kafka integration. It does not prove the deployed console, MLflow lifecycle, live RCA provider, real fault recovery, measured capacity, or release certification.

## 4. Confirmed findings

### P0-1 — Evidence producers can self-promote doubles into release-accepted levels

**Locations:**

- `src/industrial_reliability/phase8_live_gate.py:36-43, 101-120, 139-164`
- `src/industrial_reliability/phase9_live_gate.py:55-60, 97-117, 138-173`
- `src/industrial_reliability/release_certification.py:22, 154-184`

**Observed behavior:**

- Phase 8 explicitly uses a mocked scoring client, Kafka producer, and isolated metrics registry, but accepts caller-supplied `INTEGRATION`.
- Phase 9 derives `LIVE_OPENAI` from any non-empty key. Its “live” checks inspect SDK support and doubles; they do not require a successful provider response or persisted-alert POST/GET round trip.
- Release certification validates the label, schema, self-hash, exact SHA, and check names. It has no independent proof that the named dependency interaction occurred.

**Deterministic red signals:**

```text
Phase 8: {'evidence_level': 'INTEGRATION', 'simulated_components': (...in-process double...)}
Phase 9: {'evidence_level': 'LIVE', 'provider_mode': 'LIVE_OPENAI',
          'simulated_components': ['alert store (in-process double)',
                                   'OpenAI client (in-process double; no live API calls)']}
```

**Root cause:** evidence provenance is represented by caller-controlled strings instead of being owned by mutually exclusive producers whose runtime observations establish the level.

**Required contract:**

1. In-process Phase 8/9 commands have fixed `IN_PROCESS` output and cannot accept an evidence-level flag.
2. Dependency-backed producers derive `INTEGRATION`/`LIVE` only after prerequisite and interaction checks succeed.
3. Phase 9 `LIVE_OPENAI` requires a real persisted alert, a successful provider response with valid closed-world citations, persistence of the `COMPLETE` report, and a matching GET response.
4. Release validation rejects `simulated_components` for `INTEGRATION`/`LIVE` and validates producer-specific observations, not only check names.
5. Missing prerequisites publish `BLOCKED` and exit non-zero; they never downgrade or relabel.

The data remediation plan's Task 8 owns the shared evidence-level boundary. This spec adds the Phase 9/provider and release-consumer acceptance requirements.

### P0-1A — Phase 1B semantics are preserved, but authoritative artifact identity is forgeable

**Locations:** `src/industrial_reliability/release_certification.py:288-341`, `tests/test_phase1b_published_results.py`

The validator correctly rejects a feasible verdict and requires `selected_model: null`, but it accepts any `run_id`, any 64-character contract/dataset strings, and minimally shaped model objects. A fabricated nine-field JSON document with `run_id: "fabricated"`, arbitrary hashes, empty event results, and the preserved negative verdict was accepted as Phase 1B and contributed to `is_certified: true`.

```text
{'is_certified': True, 'run_id': 'fabricated'}
```

**Root cause:** semantic shape was used as a substitute for the identity of the permanent authoritative evidence.

**Required contract:** the copied certification artifact must byte-hash to the committed authoritative `docs/results/phase-1b-metrics.json` (or a separately committed immutable attestation), and its run/source/contract/model matrix must pass the existing published-result invariants. A correctly spelled negative verdict is necessary but insufficient.

### P0-2 — The public replay benchmark fabricates runtime measurements

**Locations:** `src/industrial_reliability/replay_benchmark.py:171-249`, `tests/test_replay_benchmark.py`

`--range-start`, `--range-end`, `--speed`, and `--restart-repetition` do not drive a replay. `main()` constructs samples from hardcoded counts, latency, throughput, lag, CPU, RSS, and recovery values. It also uses placeholder manifest, contract, dataset, and workload hashes when inputs are absent.

Two runs with different ranges and speeds produced identical material results:

```text
source_events: (7488, 7488)
valid_windows: (248, 248)
throughput_events_per_second: (12375.0, 12375.0)
max_consumer_lag: (115.0, 115.0)
peak_rss_bytes: (84500000, 84500000)
```

**Root cause:** the pure aggregator and a synthetic fixture generator were published as the operational runner before a real observation adapter existed.

**Required contract:** immediately classify this command/report as `SYNTHETIC` and exclude it from claims/certification. Add a real runner only when it can persist raw samples from the API, Kafka/Prometheus, process resource counters, and an injected restart. Aggregate values must be recomputable from those samples and bound to exact workload/package/dataset/contract/Git identities.

### P0-3 — The advertised one-command demo cannot execute the specified deployed journey

**Locations:**

- `scripts/run_portfolio_demo.ps1:1-108`
- `tests/test_portfolio_demo_scripts.py:123-132`
- `docs/superpowers/plans/2026-08-27-interview-readiness-hardening.md:630-731, 1325`

The script never runs `docker compose up -d --build`, never polls readiness, never runs the live Playwright project, and never prints a teardown command. `SkipDocker` is declared but unused. Its Phase 8 and Phase 9 wrapper scripts emit `IN_PROCESS` by default, which release certification correctly rejects, so the advertised success path is structurally unreachable without manually supplying different artifacts.

Preflight compounds this: it never checks the required processed telemetry path and treats a missing research-candidate manifest as a warning, although both are required for the demo.

The test checks only that URLs occur as text. It omits the plan's required assertions for stack start, readiness, live browser execution, teardown, and absence of destructive volume deletion.

**Deterministic red signal:**

```text
{'starts_stack': False, 'waits_readiness': False,
 'runs_live_browser': False, 'uses_skip_docker': False}
```

**Root cause:** implementation satisfied a weak string-presence test rather than the approved lifecycle contract.

**Required contract:** one command must preflight, verify/build the research package, set explicit opt-in, start the stack, poll every required service, run the bounded replay/alert/RCA journey, run live Playwright, collect qualifying evidence, certify exact SHA, and print `docker compose down` only after success. Failure must print bounded `compose ps`/logs and return non-zero without deleting volumes or artifacts.

### P1-4 — RCA persistence failure is swallowed and returned as `200 COMPLETE`

**Locations:** `src/industrial_reliability/api.py:440-489`, `tests/test_rca_api.py:126-168`

`contextlib.suppress(Exception)` surrounds `store.save_complete_rca(report)`. A deterministic TestClient harness configured the store to raise `RuntimeError("database unavailable")`; the API returned:

```text
{'status_code': 200, 'success': True, 'rca_status': 'COMPLETE', 'persist_calls': 1}
```

The response is not durable, a retry can repeat provider cost, and the later GET cannot return the claimed report.

**Root cause:** persistence was treated as best-effort even though the route's complete-response contract and Phase 9 evidence require persistence.

**Required contract:** a `COMPLETE` RCA is successful only after `save_complete_rca()` succeeds. Persistence failure must be logged without secret/evidence leakage and return a stable retryable `5xx` envelope such as `RCA_PERSISTENCE_FAILED`. Add one API regression test with a raising store and one integration assertion that POST and GET return the same persisted report.

### P1-5 — Green CI omits the deployed browser path and skips MLflow integration

**Locations:**

- `.github/workflows/ci.yml:35-91`
- `apps/operator-console/package.json:12-13`
- `apps/operator-console/playwright.config.ts:19-38`
- `apps/operator-console/e2e/operator-console.live.spec.ts:3-40`

The quality job calls `npm run test:e2e`, which is hardwired to `--project=mocked`. The integration job starts only PostgreSQL and Kafka, installs `.[dev]` without `.[mlops]`, and does not build/start the scoring API or console. Exact-SHA CI succeeded, but its log reports three MLflow modules skipped because `mlflow` was missing.

**Root cause:** “integration” is a test marker/job label rather than a declared capability matrix with required dependencies and no-skip enforcement per capability.

**Required contract:** retain fast mocked browser CI, and add an explicit deployed job that builds the images, starts required services, waits for readiness, runs `test:e2e:live`, and always emits bounded diagnostics. Install MLflow for MLflow-owned checks or split those checks into an explicit required job; a required capability must fail rather than collection-skip.

### P1-5A — An invalid OpenAI report shadows valid fallback evidence

**Locations:** `src/industrial_reliability/release_certification.py:40-48, 373-392`

The validator iterates OpenAI before fallback and breaks as soon as either filename exists, even when the first report is invalid. A valid fallback-only directory certified; adding an empty `phase-9-rca-openai.json` changed the same directory to invalid:

```text
{'fallback_only_certified': True, 'with_invalid_openai_sibling': False}
```

**Root cause:** file discovery order implicitly selects the evidence profile.

**Required contract:** certification must receive one explicit Phase 9 profile and reject ambiguous extra profile files, or evaluate candidates without stopping until a valid explicitly permitted profile is found. Add a two-file regression test; filesystem/dictionary order must never choose release semantics.

### P1-6 — Interview documentation publishes unearned and internally false claims

**Locations:**

- `docs/INTERVIEW_GUIDE.md:89-112`
- `README.md:98-138, 168-176`
- `docs/results/release-certification.json`
- `apps/operator-console/nginx.conf:1-33`

The guide presents Phase 8/9 as PASS and Release as `is_certified: true` using artifact paths that do not exist in the checkout. The committed release report is bound to the all-zero SHA and still says the runtime is “fully functional and certified.” The guide also claims strict CSP compliance, but nginx sets no `Content-Security-Policy` header.

`task.md:12, 19-24, 28, 41` independently claims 100% remediation, clean diff, and a final production certification report even though the corresponding blockers remain open.

**Root cause:** status prose is hand-maintained independently of current exact-SHA artifacts and deploy configuration.

**Required contract:** status tables default to `UNPROVEN/BLOCKED` and link only to existing exact-SHA artifacts. Remove the CSP claim until the deployed response proves an appropriate policy. Historical all-zero evidence must remain historical but must not be presented as current certification.

### P2-7 — Security is acceptable only because every published service is localhost-bound

**Locations:** `compose.yaml`, `src/industrial_reliability/api.py:192-551`, `.env.example`

The API exposes score, replay mutation, alert data, RCA generation, SSE, metrics, and OpenAPI without authentication, authorization, rate limits, request-size policy, or transport security. Compose correctly binds published ports to `127.0.0.1`, so this is not a blocker for a truthful single-user local demo. Any shared, tunneled, container-platform, or internet deployment would cross the current trust boundary.

**Required contract before non-local exposure:** server-side authentication and authorization, endpoint-specific rate limits, TLS at the ingress, restrictive CORS/host policy, request-size limits, non-default credentials, secret-history review, and a deployment-specific threat model. Keep localhost binding until those checks pass.

### P2-8 — Standards debt concentrates risk in the certification path

The standards review found the largest changed functions exceed the documented `<50 lines` rule (`ReleaseCertificationValidator.evaluate`, replay benchmark `main`, and preflight verification), while mutable accumulator state is used in evidence generation and certification. It also found duplicated validator loops and a redundant Phase 9 middle-man method.

This is not an independent release blocker, but it increases the chance that future evidence modes bypass a branch. Remediation must stay behind P0/P1 correctness and should delete dead/synthetic branches before adding abstractions.

## 5. Ranked diagnostic hypotheses and outcomes

| Rank | Hypothesis | Prediction | Outcome |
|---|---|---|---|
| 1 | Evidence levels are caller labels, not provenance | In-process execution can emit accepted labels | Confirmed by Phase 8/9 red harnesses |
| 2 | Tests encode document/string presence instead of real lifecycle behavior | Demo structure test passes while lifecycle requirements are absent | Confirmed |
| 3 | Benchmark aggregation was connected to fixtures rather than runtime observations | Material metrics remain identical across different ranges/speeds | Confirmed |
| 4 | API treats RCA persistence as optional | Store failure still returns `200 COMPLETE` | Confirmed |
| 5 | Release evidence selection relies on shape/order instead of authoritative identity/profile | A fabricated Phase 1B document certifies and an invalid OpenAI sibling shadows valid fallback | Confirmed |
| 6 | Green CI is capability-incomplete | Live browser is absent and optional services skip | Confirmed from exact-SHA workflow and log |

No fixes were attempted; this audit ends at confirmed root causes and remediation contracts.

## 6. Minimal remediation sequence

### Gate A — Restore truthful evidence and claims

1. Make evidence level producer-owned and close P0-1.
2. Disable release/portfolio use of the synthetic benchmark and close P0-2.
3. Mark Phase 8, Phase 9, benchmark, and release documentation `UNPROVEN/BLOCKED` until fresh exact-SHA evidence exists.

**Gate:** no in-process/synthetic command can create an artifact accepted by release certification, and no current document claims certification without a present qualifying artifact.

### Gate B — Make the deployed local journey real

1. Complete the one-command lifecycle and strengthen its structural test.
2. Make RCA persistence fail closed.
3. Add the deployed live-browser job and no-skip capability checks.

**Gate:** from a clean checkout with documented prerequisites, one command reaches a healthy stack, completes a persisted replay/alert/RCA journey, verifies it in the browser, and tears down non-destructively on operator request.

### Gate C — Earn operational evidence

1. Run real Phase 8 dependency interruption/recovery drills.
2. Run persisted-alert Phase 9 fallback and, only when configured, real-provider round trips.
3. Capture a real raw-sample benchmark.
4. Certify only the exact Git SHA that produced all artifacts.

**Gate:** all aggregates and claims are recomputable from retained observations; missing Docker, data, package, database, Kafka, browser, or provider prerequisites block certification.

### Gate D — Security before exposure

Implement P2-7 only if the deployment ceases to be localhost-only.

**Gate:** authenticated, authorized, rate-limited, TLS-terminated endpoints pass a focused security review; default credentials are absent.

## 7. Required regression checks

Minimum new checks, named by behavior rather than implementation:

- `test_phase8_in_process_gate_rejects_release_evidence_levels`
- `test_phase9_dummy_key_cannot_produce_live_openai_evidence`
- `test_release_rejects_simulated_components_at_integration_or_live_level`
- `test_release_requires_authoritative_phase1b_artifact_identity`
- `test_release_phase9_profile_selection_is_explicit_and_order_independent`
- `test_benchmark_cli_fails_without_runtime_observations`
- `test_portfolio_demo_owns_stack_readiness_live_browser_and_safe_teardown`
- `test_post_rca_returns_retryable_error_when_persistence_fails`
- `test_live_rca_post_and_get_return_same_persisted_report`
- CI assertion that the live Playwright project ran against deployed nginx/API
- CI assertion that required capability jobs have zero skipped tests

The smallest full verification set after remediation is:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -m "not slow and not integration" --cov
uv run pytest -m integration
npm --prefix apps/operator-console run test:coverage
npm --prefix apps/operator-console run build
docker compose config --quiet
pwsh -File scripts/run_portfolio_demo.ps1
git diff --check
```

The final three commands require a working Docker engine and documented local prerequisites. Local success is not RELEASE evidence until the exact-SHA remote jobs and generated artifacts are inspected.

## 8. Done criteria

- [ ] All P0 and P1 findings have a failing regression test before implementation and pass afterward.
- [ ] Evidence level is not exposed as a caller-selectable release privilege.
- [ ] No synthetic benchmark number appears in README, interview guide, release evidence, or certification.
- [ ] RCA POST cannot return `COMPLETE` unless the exact report is durable and readable.
- [ ] The one-command demo starts, waits, exercises, verifies, and reports safe teardown.
- [ ] Remote exact-SHA CI runs mocked and deployed browser projects and reports no skip for required capabilities.
- [ ] Fresh Phase 8/9/benchmark artifacts are bound to current Git/package/data/contract identities and retained observations.
- [ ] Release certification returns `INVALID` for every missing, simulated, mislabeled, stale, or semantically incomplete artifact.
- [ ] Phase 1B certification input is cryptographically bound to the committed authoritative artifact, not only schema-shaped.
- [ ] Phase 1B remains `NOT FEASIBLE` with `selected_model: null`; the viewed holdout is not rerun or retuned.
- [ ] Companion data-audit Gates A-C also pass before any production-readiness claim.
- [ ] A fresh independent standards review and spec review report zero Critical/Important findings.

## 9. Out of scope

- Implementing fixes in this audit turn.
- Editing, formatting, staging, or committing the companion data audit/plan.
- Rerunning or retuning Phase 1/1B holdouts.
- Adding authentication/TLS while the product remains explicitly localhost-only.
- Adding a new platform, benchmark framework, abstraction layer, or dependency where existing Python, pytest, PowerShell, Compose, Playwright, and Prometheus are sufficient.
