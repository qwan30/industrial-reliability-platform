# Code Review: Interview Readiness Hardening

**Review date:** 2026-08-27

**Branch:** `fix/interview-readiness-hardening`

**Base:** `300a13679be64457745676a36d0135093affde4b`

**Head:** `31259f059be7cb01bc9b2c21357a88842b734753`

**Scope:** 13 committed changes, 44 files, 2,846 insertions, 289 deletions

**Requirements:** `docs/superpowers/plans/2026-08-27-interview-readiness-hardening.md` and `docs/superpowers/specs/2026-08-27-codebase-state-audit-and-forward-roadmap.md`

## Verdict

**BLOCK — not ready to merge.**

The branch improves local validation, documentation structure, console wiring, and aggregate release failure behavior. However, its central evidence path still promotes in-process doubles and synthetic inputs to `LIVE`, accepts semantically empty fabricated artifacts, can reverse the permanent Phase 1B result, and can print demo success after certification failure. The CI and deployed-browser gates required by the plan are also incomplete.

## Findings

### Critical — must fix

#### C1. Phase 8 certifies in-process doubles as `LIVE`

- **Locations:** `src/industrial_reliability/phase8_live_gate.py:36-59`, `src/industrial_reliability/phase8_live_gate.py:101-114`
- `execute_live_drills()` invokes the existing in-process drill runners. The generated Markdown explicitly says that the scoring client, Kafka producer, and metrics registry are doubles and that no broker, scoring API, or database is contacted.
- Despite that disclosure, `publish_live_drill_report()` and `run_phase8_live_gate()` default to `evidence_level="LIVE"` and emit the exact schema and filename accepted by release certification.
- **Impact:** mocked recovery behavior can certify Phase 8 as real dependency-backed evidence.
- **Required fix:** implement the planned non-injectable, prerequisite-checked Kafka/PostgreSQL/API/telemetry recovery drills. Synthetic runners must be forced to `UNIT` or `IN_PROCESS`; callers must not be able to select a release evidence level.

#### C2. Phase 9 infers `LIVE_OPENAI` from key presence and labels synthetic fallback `LIVE`

- **Locations:** `src/industrial_reliability/phase9_live_gate.py:37-40`, `src/industrial_reliability/phase9_live_gate.py:55-60`, `src/industrial_reliability/phase9_live_gate.py:97-150`
- Provider mode is selected from whether the API-key string is non-empty. The checks inspect SDK support or use synthetic evidence and in-process client/store doubles; they do not execute a deployed RCA POST/GET round trip, verify a persisted alert, or require a successful provider response.
- The no-key fallback path also defaults to `evidence_level="LIVE"`.
- **Impact:** any non-empty string can yield `LIVE_OPENAI`, while a completely synthetic fallback can yield `LIVE/FALLBACK_ONLY/PASS`.
- **Required fix:** derive evidence from matching deployed POST/GET responses for a real persisted alert. Emit fallback as `INTEGRATION/FALLBACK_ONLY`; emit `LIVE/LIVE_OPENAI` only after a persisted `COMPLETE` provider response with valid citations.

#### C3. Release certification accepts fabricated, semantically empty evidence and can reverse Phase 1B

- **Locations:** `src/industrial_reliability/release_certification.py:88-112`, `src/industrial_reliability/release_certification.py:215-230`, `tests/test_release_certification.py:29-80`
- Phase 8/9 validation checks headers, evidence labels, exact SHA, and a recomputable self-hash, but does not validate required drill/check contents or internal semantics. The passing test helpers explicitly use `drills: []` and `checks: []`.
- Phase 1B accepts any object with `schema_version="phase1b-benchmark-v1"`; `verdict="FEASIBLE"` is enough to produce `FEASIBLE_PLATFORM_RELEASE`, without authoritative metrics, `selected_model`, provenance, or immutable artifact identity.
- **Reproduced:** a temporary three-file fixture with header-only `FEASIBLE` Phase 1B evidence and empty Phase 8/9 lists returned:

  ```json
  {
    "verdict": "FEASIBLE_PLATFORM_RELEASE",
    "is_certified": true,
    "phases_passed": [
      "phase1b",
      "phase8_observability_fault_drills",
      "phase9_grounded_rca"
    ]
  }
  ```

- A second proof generated the repository's default mocked Phase 8 and synthetic fallback Phase 9 reports; the validator accepted them as `NEGATIVE_RESEARCH_RELEASE` with `is_certified: true`.
- **Impact:** recomputed hashes make fabricated content internally consistent but not truthful; the permanent `NOT FEASIBLE` / `selected_model: null` result can be contradicted.
- **Required fix:** validate complete typed schemas and mandatory drill/check semantics. Bind Phase 1B to the immutable authoritative artifact and require the preserved `NOT FEASIBLE` result with `selected_model: null`.

#### C4. The portfolio demo neither runs the deployed journey nor gates its success message

- **Locations:** `scripts/run_portfolio_demo.ps1:18-58`
- The script does not start Compose, set and verify research-candidate identity, poll service readiness, run replay/browser/benchmark checks, or copy authoritative Phase 1B evidence into the certification directory.
- It does not explicitly stop after each native command's non-zero exit before printing `Portfolio Demo Completed Successfully!`.
- **Impact:** on a fresh checkout the release command lacks mandatory Phase 1B evidence and exits non-zero, yet the demo can still announce success; the executed Phase 8/9 commands are the synthetic gates described above.
- **Required fix:** implement the ordered Task 6 lifecycle, check every native exit code, use qualifying Phase 8/9/benchmark evidence, validate the final report, and print success only after `is_certified` is proven true.

### Important — should fix before another review

#### I1. Replay benchmark output remains synthetic

- **Locations:** `src/industrial_reliability/replay_benchmark.py:34-57`, `src/industrial_reliability/replay_benchmark.py:93-116`
- Only optional latency percentiles are calculated from samples. Throughput, lag, CPU, RSS, recovery, counts, digests, and identity hashes remain constants. CLI range, speed, and restart arguments are unused; the CLI defaults to an all-zero Git SHA.
- **Impact:** `benchmark.json` presents fabricated capacity/recovery values rather than captured runtime measurements.
- **Required fix:** implement the planned V2 raw-sample report, frozen workload, real API/Prometheus/runtime observations, deterministic aggregation, identity validation, and self-hash.

#### I2. The integration CI job is guaranteed to fail while other dependency tests can still skip

- **Locations:** `.github/workflows/ci.yml:44-73`, `tests/integration/test_kafka_replay.py:29-45`, `tests/integration/test_console_stream_persistence.py:36`, `tests/integration/test_online_worker.py:39-43`, `tests/integration/test_rca_persistence.py:29`
- The job sets `REQUIRE_INTEGRATION_SERVICES=true` and runs all integration-marked tests but provisions only PostgreSQL. `test_kafka_replay_end_to_end` requires Kafka at `localhost:29092` and therefore fails.
- Other required dependency modules still call `pytest.skip` unconditionally because they do not share the new environment contract.
- **Impact:** the job cannot pass as written and, after Kafka is added, still cannot prove all required dependencies were exercised.
- **Required fix:** provision Kafka and PostgreSQL, use one fail-closed environment variable/helper across every required integration module, run the explicit dependency-backed test list, and capture bounded Compose diagnostics on failure.

#### I3. Live Playwright coverage is excluded rather than separated

- **Locations:** `apps/operator-console/playwright.config.ts:5-28`, `.github/workflows/ci.yml:35-42`
- The top-level negative-lookbehind `testMatch` excludes `operator-console.live.spec.ts` from the only `chromium` project. The config always starts Vite and defines no `mocked` or `live` project.
- **Impact:** CI provides neither deployed-nginx proxy evidence nor a live-console journey, contrary to Task 7.
- **Required fix:** define explicit mocked/live projects, make the live project opt-in and deployed-server-backed, build/smoke the console container, and run the live project in the Compose job.

#### I4. Documentation asserts qualifying evidence that does not exist

- **Locations:** `docs/INTERVIEW_GUIDE.md:89-96`, `README.md:129-135`, `README.md:166-172`
- The new guide declares Phase 8/9 `LIVE/PASS` and release `PASS/VALID`. The README changes previously truthful `IN_PROCESS` labels to `LIVE`, although the source still uses doubles and synthetic evidence.
- **Impact:** the interview package violates the repository's evidence-integrity objective and misleads reviewers about current release state.
- **Required fix:** state that the gates are `BLOCKED`/unproven until fresh exact-SHA qualifying artifacts exist; do not hardcode PASS status.

#### I5. Preflight checks the wrong topology and omits required prerequisites

- **Locations:** `deploy/preflight.py:17-22`, `deploy/preflight.py:42-72`, `compose.yaml:22`, `compose.yaml:126`, `tests/test_portfolio_demo_scripts.py:17-25`
- Preflight checks host ports `3000`, `9092`, `9102`, and `9103`; Compose publishes the console on `5173` and Kafka on `29092`, while `9102/9103` are internal service metric ports.
- It does not require Docker Compose, processed telemetry, or the research-package inputs/manifest. The tests codify the incorrect ports.
- **Impact:** preflight can pass while the actual demo is unrunnable.
- **Required fix:** use the actual published topology and fail closed on Docker/Compose and required data/package paths.

#### I6. Default certification output can overwrite committed historical evidence

- **Locations:** `src/industrial_reliability/release_certification.py:335-345`, `src/industrial_reliability/release_certification.py:381-386`, `README.md:184-188`
- The default output remains `docs/results/release-certification.json`, and the documented exact-SHA command omits `--output`.
- **Impact:** running the documented command mutates tracked historical evidence instead of writing dynamic exact-SHA artifacts.
- **Required fix:** require an explicit output or derive `artifacts/certification/<git-sha>/release-certification.json`.

### Minor — nice to fix

#### M1. The committed range fails `git diff --check`

- **Locations:** `apps/operator-console/src/components/RcaPanel.tsx:213`, `docs/results/phase-10a-spark-decision.md:10`, `docs/superpowers/specs/2026-08-27-codebase-state-audit-and-forward-roadmap.md:3-6`, `ops/prometheus/prometheus.yml:25`
- Blank lines at EOF and trailing whitespace leave the final clean-diff gate failing.

#### M2. Interview-guide links are workstation-specific

- **Locations:** `docs/INTERVIEW_GUIDE.md:65-93`
- `file:///d:/projects/...` links will not work for GitHub readers or other checkouts. Use repository-relative links.

## Strengths

- Aggregate release logic now rejects absent or header-invalid Phase 8/9 artifacts instead of setting `is_certified` unconditionally.
- Phase 1B/model-card quantitative claims were corrected against the authoritative committed metrics.
- Console proxy/RCA environment wiring, alert-service Prometheus discovery, persisted alert metrics, and RCA/event rendering are directionally sound.
- The branch retains exact-SHA and self-hash checks, which are useful integrity primitives once combined with complete semantic validation and truthful evidence producers.

## Verification evidence

| Check | Result |
|---|---|
| `ruff check .` | PASS |
| `ruff format --check .` | PASS — 185 files formatted |
| `mypy src` | PASS — 54 source files |
| `pytest -m "not slow and not integration"` | PASS — 445 passed, 1 skipped, 9 deselected, 87.11% coverage |
| Operator-console Vitest coverage | PASS — 45 tests; 95.01% statements, 88.97% branches |
| Operator-console production build | PASS |
| Mocked Playwright flow | BLOCKED locally — required Chromium revision was not installed |
| `docker compose config --quiet` | PASS |
| Docker-backed/live checks | NOT RUN — Docker Desktop engine unavailable |
| `git diff --check BASE..HEAD` | FAIL — whitespace findings listed in M1 |
| GitHub branch/PR/checks | NONE — HEAD is local-only; no remote commit, branch, PR, check run, or workflow run exists for `31259f0` |

Local unit/static passes do not establish dependency-backed, live-provider, release, or merge evidence. The checkout's pre-existing untracked `.superpowers/` directory was excluded from review and preserved.

## Assessment

**Ready to merge:** No.

Complete the real evidence producers and semantic validators first, repair the demo and CI topology, make the documentation truthful again, then request a fresh review against a pushed exact HEAD with remote CI evidence.
