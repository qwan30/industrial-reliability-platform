# Interview Readiness Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Prongs 0–4 of the codebase-state roadmap truthful and reproducible: certification fails closed, the deployed local demo works, real dependency evidence replaces mocked operational claims, runtime measurements replace constants, and interview claims trace to current artifacts.

**Architecture:** Keep the existing FastAPI/Kafka/PostgreSQL/React topology and repair the narrow seams that are already present. Separate contract tests (`UNIT`/`IN_PROCESS`) from dependency-backed certification (`INTEGRATION`/`LIVE`), write dynamic exact-SHA evidence only under `artifacts/`, and aggregate a release only when every mandatory artifact validates.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, aiokafka, psycopg 3, Prometheus, Docker Compose, PowerShell, React 18, TypeScript 5.4, Vite 5, Vitest, Playwright, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-codebase-state-audit-and-forward-roadmap.md`

## Global Constraints

- Preserve Phase 1 and Phase 1B as permanently `NOT FEASIBLE`; never create or imply a production champion.
- Do not rerun, retune, or select policy against either viewed holdout.
- The runtime package remains `RESEARCH_CANDIDATE` / `RESEARCH_ONLY` and requires `ALLOW_RESEARCH_CANDIDATE=true`.
- Evidence levels are exact: mocks are `UNIT`, in-process gates are `IN_PROCESS`, real local dependencies are `INTEGRATION`, complete provider/deployed interactions are `LIVE`, and aggregation is `RELEASE`.
- Missing Docker, data, package, Kafka, PostgreSQL, browser, or provider prerequisites must block the applicable gate; they may not produce a downgraded pass.
- Dynamic certification outputs belong under `artifacts/certification/$sha/`, where `$sha` is the resolved exact Git SHA; do not refresh committed `docs/results/` files as a substitute.
- Keep every published host binding on `127.0.0.1`; Prong 5 security controls are mandatory before shared or internet-accessible deployment.
- Use only environment-provided secrets. Never print, persist, pass on a command line, or commit `RCA_OPENAI_API_KEY`.
- Keep Airflow `NOT_ADOPTED` and Spark/OpenVINO `PLATFORM_PATH_STOPPED` unless their predeclared measured reconsideration triggers fire.
- Maintain Python coverage at or above 80%, strict mypy for `src`, Ruff check/format, frontend 80% coverage, and fail-closed input validation at trust boundaries.
- Preserve unrelated working-tree changes. Stage exact paths only; never use `git add .`, stash, reset, blanket checkout, or force-push.

---

## Scope and file responsibility map

This plan is one dependency-ordered interview-readiness program because each prong consumes evidence produced by the previous prong. Prong 5 is retained as a localhost-only boundary, not implemented here. Prong 6 is a separate future research plan requiring fresh evidence.

### Certification and claim integrity

- `src/industrial_reliability/release_certification.py` — validate the mandatory release profile and compute the aggregate verdict.
- `tests/test_release_certification.py` — freeze missing/invalid/foreign/unit-level evidence as non-certifying behavior.
- `src/industrial_reliability/portfolio_claims.py` — derive interview metrics from the committed Phase 1B schema, never free-form fixture numbers.
- `tests/test_portfolio_claims.py` — bind portfolio output to `docs/results/phase-1b-metrics.json`.
- `README.md`, `docs/MODEL_CARD.md`, `pyproject.toml`, `src/industrial_reliability/__init__.py` — remove production/champion claim debt and correct the autoencoder figures.
- `src/industrial_reliability/phase10a_gate.py`, `tests/test_phase10a_gate.py` — keep the stopped Spark path from emitting an unmeasured capacity claim.

### Deployed demo wiring

- `apps/operator-console/nginx.conf` — proxy the built console to the real Compose service name.
- `compose.yaml` — pass optional RCA settings, expose alert metrics to Prometheus, and preserve localhost-only ports.
- `.env.example`, `docs/RUNBOOK.md` — document local-only credentials, optional provider settings, and teardown.
- `ops/prometheus/prometheus.yml`, `tests/test_observability_config.py` — scrape alert-service and freeze the wiring.
- `src/industrial_reliability/persistence.py` — count current open alerts after committed transitions.
- `src/industrial_reliability/alert_consumer.py`, `src/industrial_reliability/alert_service.py` — record real alert transition metrics using the existing `RuntimeMetrics` object.
- `tests/test_persistence.py`, `tests/test_alert_consumer.py`, `tests/test_alert_service.py` — prove metrics follow persisted state and are wired by the service.
- `apps/operator-console/src/components/RcaPanel.tsx` — replace unavailable Tailwind classes with the console's existing inline-style approach.
- `apps/operator-console/src/components/AlertPanel.tsx`, `apps/operator-console/src/types.ts` — render the already-fetched event and decision evidence.
- `apps/operator-console/src/components/__tests__/RcaPanel.test.tsx`, `apps/operator-console/src/components/__tests__/AlertPanel.test.tsx` — freeze readable fallback/status/timeline output.
- `deploy/preflight.py`, `tests/test_deploy_preflight.py` — check the actual ports, Docker/Compose, and local artifacts.
- `scripts/run_portfolio_demo.ps1`, `tests/test_portfolio_demo_script.py` — own the one-command stack lifecycle without hiding missing prerequisites.

### Real evidence, benchmark, and interview package

- `.github/workflows/ci.yml` — run mocked Playwright normally and required dependency-backed checks in a Compose job.
- `src/industrial_reliability/phase8_live_gate.py`, `tests/test_phase8_live_gate.py`, `tests/integration/test_phase8_fault_drills.py`, `scripts/run_phase8_live_fault_drills.ps1` — produce real broker/database/malformed/known-abnormal recovery evidence.
- `src/industrial_reliability/phase9_live_gate.py`, `tests/test_phase9_live_gate.py`, `tests/integration/test_rca_persistence.py`, `scripts/run_phase9_live_gate.ps1` — classify fallback only after a deployed persisted-alert round trip and classify `LIVE_OPENAI` only after a real provider response.
- `src/industrial_reliability/decision_gate.py`, `src/industrial_reliability/replay_benchmark.py`, `tests/test_replay_benchmark.py`, `ops/benchmarks/replay-workload.json` — capture raw samples and recomputable runtime aggregates.
- `docs/INTERVIEW_GUIDE.md`, `README.md`, `docs/RUNBOOK.md`, `tests/test_portfolio_claims.py` — publish the capability/evidence/limitation matrix and ten-minute script.

## Planned commit stack

1. `docs: define interview readiness hardening roadmap`
2. `fix: fail release certification closed`
3. `docs: align model and platform claims with evidence`
4. `fix: wire deployed console rca and alert metrics`
5. `fix: publish persisted alert transition metrics`
6. `fix: render grounded rca evidence without tailwind`
7. `feat: run the localhost portfolio demo from one command`
8. `ci: require browser and dependency-backed integration checks`
9. `feat: collect real phase 8 recovery evidence`
10. `feat: certify deployed phase 9 fallback and provider modes`
11. `perf: measure the frozen replay workload`
12. `docs: publish the evidence-traceable interview guide`

---

### Task 0: Preserve the approved roadmap and execution plan

**Files:**
- Create: `docs/superpowers/specs/2026-08-27-codebase-state-audit-and-forward-roadmap.md` (already present in the planning checkout; preserve its exact reviewed content)
- Create: `docs/superpowers/plans/2026-08-27-interview-readiness-hardening.md`

**Interfaces:**
- Consumes: merged base `300a13679be64457745676a36d0135093affde4b` and branch `fix/interview-readiness-hardening`.
- Produces: one committed spec/plan pair that every later task cites.

- [ ] **Step 1: Verify the execution checkout without altering it**

Run:

```powershell
git status --short --branch
git rev-parse HEAD
git branch --show-current
```

Expected: HEAD is descended from `300a13679be64457745676a36d0135093affde4b`; only reviewed in-scope planning files may be staged in this task.

- [ ] **Step 2: Re-read the roadmap boundary**

Run:

```powershell
rg -n "Prong 0|Prong 4|Prong 5|Prong 6|Out of Scope|NOT FEASIBLE" docs/superpowers/specs/2026-08-27-codebase-state-audit-and-forward-roadmap.md
```

Expected: Prongs 0–4 are the interview-readiness gate, Prong 5 blocks non-local exposure, and Prong 6 forbids reuse of viewed holdouts.

- [ ] **Step 3: Commit only the planning artifacts**

```powershell
git add docs/superpowers/specs/2026-08-27-codebase-state-audit-and-forward-roadmap.md docs/superpowers/plans/2026-08-27-interview-readiness-hardening.md
git commit -m "docs: define interview readiness hardening roadmap"
git status --short
```

Expected: the commit contains exactly two Markdown files; any unrelated files remain uncommitted.

---

### Task 1: Make release certification fail closed

**Files:**
- Modify: `src/industrial_reliability/release_certification.py:19-318`
- Modify: `tests/test_release_certification.py:42-250`

**Interfaces:**
- Consumes: exact lowercase 40-hex Git SHA, Phase 1B metrics, a Phase 8 report, and a Phase 9 report from one artifact directory.
- Produces: `ReleaseCertificationValidator.evaluate(git_sha: str | None) -> ReleaseCertificationReportV1`; `is_certified` is true only when Phase 1B is recognized and Phase 8 plus Phase 9 have valid exact-SHA `INTEGRATION`/`LIVE` evidence.

- [ ] **Step 1: Replace the optimistic regression with a failing closed-gate test**

Update the passing helpers to emit `evidence_level: "INTEGRATION"`, and add these assertions:

```python
def test_rejected_phase8_makes_aggregate_invalid(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase9_report(tmp_path)
    report = ReleaseCertificationValidator(tmp_path).evaluate(git_sha="a" * 40)
    assert report.verdict == "INVALID"
    assert report.is_certified is False
    assert "phase8_observability_fault_drills" not in report.phases_passed


def test_rejected_phase9_makes_aggregate_invalid(tmp_path: Path) -> None:
    _write_phase1b_metrics(tmp_path)
    _write_passing_phase8_report(tmp_path)
    report = ReleaseCertificationValidator(tmp_path).evaluate(git_sha="a" * 40)
    assert report.verdict == "INVALID"
    assert report.is_certified is False
    assert "phase9_grounded_rca" not in report.phases_passed
```

- [ ] **Step 2: Run the focused tests and observe the current false-positive behavior**

Run:

```powershell
python -m pytest tests/test_release_certification.py -q
```

Expected: the new aggregate assertions fail because the current implementation sets `is_certified` to `True` unconditionally.

- [ ] **Step 3: Tighten eligible evidence and provider-mode binding**

Use these exact eligibility rules:

```python
_RELEASE_EVIDENCE_LEVELS = frozenset({"INTEGRATION", "LIVE"})

_CURRENT_SCHEMAS = frozenset(
    {
        "phase8-live-fault-drills-v1",
        "phase-9-rca-openai-v1",
        "phase-9-rca-fallback-v1",
    }
)

_P8_EVIDENCE_SPECS = {
    "phase-8-live-fault-drills.json": (
        "phase8-live-fault-drills-v1",
        "verdict",
        "PASS",
    )
}

_P9_EVIDENCE_SPECS = {
    "phase-9-rca-openai.json": ("phase-9-rca-openai-v1", "verdict", "PASS"),
    "phase-9-rca-fallback.json": ("phase-9-rca-fallback-v1", "verdict", "PASS"),
}

_P9_PROVIDER_MODES = {
    "phase-9-rca-openai.json": "LIVE_OPENAI",
    "phase-9-rca-fallback.json": "FALLBACK_ONLY",
}
```

Extend `_verify_release_evidence` with `expected_provider_mode: str | None = None`; when non-null, require `data.get("provider_mode") == expected_provider_mode`. Keep schema, verdict, self-hash, exact-SHA, and evidence-level checks conjunctive.

- [ ] **Step 4: Compute the aggregate from mandatory phase validity**

Track `phase1b_valid`, `phase8_valid`, and `phase9_valid` booleans. Always add a limitation when a mandatory phase is absent or rejected. Finish with:

```python
mandatory_evidence_valid = phase1b_valid and phase8_valid and phase9_valid
verdict: ReleaseVerdict = (
    "FEASIBLE_PLATFORM_RELEASE"
    if mandatory_evidence_valid and is_feasible
    else "NEGATIVE_RESEARCH_RELEASE"
    if mandatory_evidence_valid
    else "INVALID"
)
is_certified = mandatory_evidence_valid
```

Delete the unconditional runtime-certified limitation. Retain only limitations derived from actual phase results.

- [ ] **Step 5: Freeze CLI exit behavior**

Change the existing CLI test with only Phase 1B evidence to expect exit code `1`. Add a second CLI test with valid Phase 8/9 integration reports and expect exit code `0`, exact SHA, `NEGATIVE_RESEARCH_RELEASE`, and a valid self-hash.

- [ ] **Step 6: Verify the focused module**

Run:

```powershell
python -m pytest tests/test_release_certification.py tests/test_report_hashes.py -q
ruff check src/industrial_reliability/release_certification.py tests/test_release_certification.py
mypy src/industrial_reliability/release_certification.py
```

Expected: all commands pass; missing, unreadable, failing, unit/in-process, foreign-SHA, foreign-schema, or wrong-provider evidence yields `INVALID` and exit code `1`.

- [ ] **Step 7: Commit the trust blocker**

```powershell
git add src/industrial_reliability/release_certification.py tests/test_release_certification.py
git commit -m "fix: fail release certification closed"
```

---

### Task 2: Bind model and platform claims to authoritative metrics

**Files:**
- Modify: `src/industrial_reliability/portfolio_claims.py:1-17`
- Modify: `tests/test_portfolio_claims.py:1-19`
- Modify: `docs/MODEL_CARD.md:1-40`
- Modify: `README.md:1-15`
- Modify: `pyproject.toml:8-13`
- Modify: `src/industrial_reliability/__init__.py:1`
- Modify: `src/industrial_reliability/phase10a_gate.py:126-138`
- Modify: `tests/test_phase10a_gate.py:35-54`

**Interfaces:**
- Consumes: `docs/results/phase-1b-metrics.json` schema `phase1b-benchmark-v1` and a concrete model key.
- Produces: `generate_portfolio_claims(metrics: Mapping[str, Any], model_id: str) -> dict[str, str | list[str]]` with values derived only from the selected model row and its event results.

- [ ] **Step 1: Write artifact-backed claim tests**

```python
def test_claims_match_committed_phase1b_metrics() -> None:
    metrics = json.loads(Path("docs/results/phase-1b-metrics.json").read_text(encoding="utf-8"))
    claims = generate_portfolio_claims(metrics, "autoencoder")
    assert claims["event_detection_rate"] == "100.0% (4/4 events)"
    assert claims["false_alarm_rate"] == "30.670 false episodes/day"
    assert claims["pr_auc"] == "0.2295"
    assert claims["operational_verdict"] == "NOT FEASIBLE"


def test_claim_generation_rejects_unknown_model() -> None:
    with pytest.raises(KeyError, match="unknown model_id"):
        generate_portfolio_claims({"models": {}}, "missing")
```

Also add a test that the stopped Phase 10A report contains `Platform path stopped` and does not contain `satisfies streaming SLA` when `baseline is None`.

- [ ] **Step 2: Run the tests and confirm the current synthetic fixture contract fails**

Run:

```powershell
python -m pytest tests/test_portfolio_claims.py tests/test_phase10a_gate.py -q
```

Expected: failures show the old one-argument claims API and unconditional Phase 10A capacity sentence.

- [ ] **Step 3: Derive claims with stdlib statistics**

Implement the minimum schema projection:

```python
from collections.abc import Mapping
from statistics import median
from typing import Any


def generate_portfolio_claims(
    metrics: Mapping[str, Any], model_id: str
) -> dict[str, str | list[str]]:
    models = metrics.get("models")
    if not isinstance(models, Mapping) or model_id not in models:
        raise KeyError(f"unknown model_id: {model_id}")
    model = models[model_id]
    leads = [
        row["lead_seconds_to_source_start"]
        for row in model["event_results"]
        if row["detected"] and row["lead_seconds_to_source_start"] is not None
    ]
    return {
        "event_detection_rate": (
            f"{100 * model['detected_events'] / model['total_events']:.1f}% "
            f"({model['detected_events']}/{model['total_events']} events)"
        ),
        "false_alarm_rate": f"{model['false_episodes_per_day']:.3f} false episodes/day",
        "lead_time_summary": f"{median(leads):.0f}s median lead time",
        "pr_auc": f"{model['pr_auc']:.4f}",
        "operational_verdict": str(metrics["verdict"]),
        "unsupported_claims": [],
    }
```

- [ ] **Step 4: Correct prose and package metadata**

Use `Evidence-led negative-research industrial reliability case study` as the README/package description. Correct the Model Card autoencoder row to `4/4`, `31.68%` time in alert, and `30.670` false episodes/day. Keep `selected_model: null`, the research-only opt-in, and all prohibited claims visible.

Render the Phase 10A rationale conditionally: the stopped path states only that offline feasibility stopped platform optimization; the SLA sentence appears only when a measured baseline exists.

- [ ] **Step 5: Verify claim consistency**

Run:

```powershell
python -m pytest tests/test_portfolio_claims.py tests/test_phase10a_gate.py tests/test_phase1b_published_results.py -q
rg -n "Production-oriented|Autoencoder.*3/4|16\.32|fully functional and certified|satisfies streaming SLA" README.md docs/MODEL_CARD.md pyproject.toml src/industrial_reliability docs/results/phase-10a-spark-decision.md
```

Expected: tests pass; the search returns no live source/current documentation claim that contradicts the authoritative Phase 1B metrics. Historical plans may retain historical wording.

- [ ] **Step 6: Commit the claim correction separately**

```powershell
git add src/industrial_reliability/portfolio_claims.py tests/test_portfolio_claims.py docs/MODEL_CARD.md README.md pyproject.toml src/industrial_reliability/__init__.py src/industrial_reliability/phase10a_gate.py tests/test_phase10a_gate.py
git commit -m "docs: align model and platform claims with evidence"
```

---

### Task 3: Repair Compose, console proxy, RCA, and Prometheus wiring

**Files:**
- Modify: `apps/operator-console/nginx.conf:12-30`
- Modify: `compose.yaml:44-169`
- Modify: `.env.example:18-21`
- Modify: `ops/prometheus/prometheus.yml:5-19`
- Modify: `tests/test_observability_config.py:7-47`

**Interfaces:**
- Consumes: Compose service DNS names, optional host `RCA_OPENAI_API_KEY`, `RCA_OPENAI_MODEL`, and `RCA_TIMEOUT_SECONDS`.
- Produces: working `/v1`, `/healthz`, `/readyz` proxy routes; provider settings inside `scoring-api`; Prometheus target `alert-service:9103`.

- [ ] **Step 1: Add static wiring regressions**

```python
def test_deployed_console_proxies_to_scoring_api() -> None:
    nginx = Path("apps/operator-console/nginx.conf").read_text(encoding="utf-8")
    assert "http://scoring-api:8000" in nginx
    assert "http://api:8000" not in nginx


def test_compose_passes_optional_rca_settings() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    assert "RCA_OPENAI_API_KEY: ${RCA_OPENAI_API_KEY:-}" in compose
    assert "RCA_OPENAI_MODEL: ${RCA_OPENAI_MODEL:-}" in compose
    assert "RCA_TIMEOUT_SECONDS: ${RCA_TIMEOUT_SECONDS:-20}" in compose


def test_prometheus_scrapes_alert_service() -> None:
    config = Path("ops/prometheus/prometheus.yml").read_text(encoding="utf-8")
    assert 'job_name: "alert-service"' in config
    assert 'targets: ["alert-service:9103"]' in config
```

- [ ] **Step 2: Run the static tests and observe all three gaps**

Run:

```powershell
python -m pytest tests/test_observability_config.py -q
```

Expected: the new proxy, RCA environment, and alert scrape assertions fail.

- [ ] **Step 3: Apply the minimal native configuration fixes**

Replace each nginx upstream `http://api:8000` with `http://scoring-api:8000`. Add these keys under `scoring-api.environment`:

```yaml
      RCA_OPENAI_API_KEY: ${RCA_OPENAI_API_KEY:-}
      RCA_OPENAI_MODEL: ${RCA_OPENAI_MODEL:-}
      RCA_TIMEOUT_SECONDS: ${RCA_TIMEOUT_SECONDS:-20}
```

Add this Prometheus scrape job:

```yaml
  - job_name: "alert-service"
    metrics_path: "/metrics"
    static_configs:
      - targets: ["alert-service:9103"]
```

Add `alert-service` to Prometheus dependencies. Keep the API key blank in `.env.example`; document that the fallback path is expected when blank.

- [ ] **Step 4: Validate parsed Compose and focused tests**

Run:

```powershell
docker compose config --quiet
python -m pytest tests/test_observability_config.py -q
```

Expected: both commands pass and `docker compose config` output does not print a secret value.

- [ ] **Step 5: Commit the cross-layer wiring slice**

```powershell
git add apps/operator-console/nginx.conf compose.yaml .env.example ops/prometheus/prometheus.yml tests/test_observability_config.py
git commit -m "fix: wire deployed console rca and alert metrics"
```

---

### Task 4: Publish metrics from persisted alert transitions

**Files:**
- Modify: `src/industrial_reliability/persistence.py:74-110`
- Modify: `src/industrial_reliability/alert_consumer.py:34-113`
- Modify: `src/industrial_reliability/alert_service.py:83-134`
- Modify: `tests/test_persistence.py:211-220`
- Modify: `tests/test_alert_consumer.py:28-105`
- Modify: `tests/test_alert_service.py:49-78`

**Interfaces:**
- Consumes: `TransitionResult.event`, the committed PostgreSQL alert state, and optional `RuntimeMetrics`.
- Produces: `RuntimeStore.count_active_alerts() -> int`; `AlertConsumer(store, policy, producer=None, consumer=None, machine_id="metropt3", metrics: RuntimeMetrics | None = None)`; real `irp_alert_events_total` and `irp_alerts_active` updates after successful persistence only.

- [ ] **Step 1: Write failing persistence and metrics tests**

```python
def test_count_active_alerts() -> None:
    store = RuntimeStore("postgresql://test")
    with patch("industrial_reliability.persistence.psycopg.connect") as connect:
        connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = {
            "count": 2
        }
        assert store.count_active_alerts() == 2


@pytest.mark.asyncio
async def test_consumer_records_only_persisted_transition_metrics() -> None:
    metrics = build_runtime_metrics(CollectorRegistry())
    consumer = AlertConsumer(store=mock_store, policy=policy, metrics=metrics)
    assert await consumer.process(record) == ProcessOutcome.COMMITTED
    assert metrics.alert_events.labels(action="opened")._value.get() == 1
    assert metrics.alerts_active._value.get() == 1
```

Set `mock_store.count_active_alerts.return_value = 1`. Add a no-event decision case proving the counter does not increment. Extend the service lifecycle test to assert its `AlertConsumer` receives the same `RuntimeMetrics` instance.

- [ ] **Step 2: Run focused tests and verify the missing interface**

Run:

```powershell
python -m pytest tests/test_persistence.py tests/test_alert_consumer.py tests/test_alert_service.py -q
```

Expected: failures identify the absent `count_active_alerts` method and `metrics` constructor parameter.

- [ ] **Step 3: Count open alerts with one direct query**

```python
def count_active_alerts(self) -> int:
    with psycopg.connect(self.db_url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM alerts WHERE state = 'OPEN';")
        row = cur.fetchone()
    return int(row["count"]) if row is not None else 0
```

- [ ] **Step 4: Record metrics only after the transaction succeeds**

Store `metrics` on `AlertConsumer`. Immediately after `record_decision_transition(decision, result)` returns, use:

```python
if self.metrics is not None and result.event is not None:
    self.metrics.record_alert_action(result.event.action.lower())
    self.metrics.set_active_alerts(self.store.count_active_alerts())
```

Pass `metrics=self.metrics` when `AlertService.start()` constructs `AlertConsumer`. Do not record metrics for decode quarantine, identity failure, duplicate/no-op transitions, or failed database writes.

- [ ] **Step 5: Verify metric behavior and static checks**

Run:

```powershell
python -m pytest tests/test_metrics.py tests/test_persistence.py tests/test_alert_consumer.py tests/test_alert_service.py -q
ruff check src/industrial_reliability/persistence.py src/industrial_reliability/alert_consumer.py src/industrial_reliability/alert_service.py
mypy src/industrial_reliability/persistence.py src/industrial_reliability/alert_consumer.py src/industrial_reliability/alert_service.py
```

Expected: counters/gauge change only after committed state transitions and remain bounded-label metrics.

- [ ] **Step 6: Commit the runtime metrics slice**

```powershell
git add src/industrial_reliability/persistence.py src/industrial_reliability/alert_consumer.py src/industrial_reliability/alert_service.py tests/test_persistence.py tests/test_alert_consumer.py tests/test_alert_service.py
git commit -m "fix: publish persisted alert transition metrics"
```

---

### Task 5: Render RCA, event, and decision evidence with the existing UI system

**Files:**
- Modify: `apps/operator-console/src/types.ts:29-66`
- Modify: `apps/operator-console/src/components/RcaPanel.tsx:1-119`
- Modify: `apps/operator-console/src/components/AlertPanel.tsx:142-188`
- Modify: `apps/operator-console/src/components/__tests__/RcaPanel.test.tsx:16-100`
- Modify: `apps/operator-console/src/components/__tests__/AlertPanel.test.tsx:56-87`

**Interfaces:**
- Consumes: `AlertDetail.events`, `AlertDetail.decisions`, and `RcaReportV1` already returned by `GET /v1/alerts/{alert_id}`.
- Produces: typed `AlertEventDetail` and `ScoreDecisionDetail`; readable event timeline, decision table, fallback status, citations, and uncertainty without Tailwind.

- [ ] **Step 1: Add failing rendering tests**

Populate the alert-detail response with one `OPENED` event and one anomalous score decision, then assert:

```typescript
expect(await screen.findByTestId('alert-event-timeline')).toHaveTextContent('OPENED');
expect(screen.getByTestId('alert-decision-table')).toHaveTextContent('1400.000');
expect(screen.getByTestId('alert-decision-table')).toHaveTextContent('1200.000');
```

Add an `UNAVAILABLE` RCA report test that checks the badge, evidence-only summary, and non-causal uncertainty remain visible. Add `expect(screen.getByTestId('rca-panel').className).toBe('')` so unavailable Tailwind utilities cannot silently return.

- [ ] **Step 2: Run component tests and observe the missing output**

Run:

```powershell
Push-Location apps/operator-console
npm test -- --run src/components/__tests__/AlertPanel.test.tsx src/components/__tests__/RcaPanel.test.tsx
Pop-Location
```

Expected: event/decision test IDs are absent and `RcaPanel` still contains Tailwind-only class names.

- [ ] **Step 3: Define the payload types already emitted by the API**

```typescript
export interface AlertEventDetail {
  action: 'OPENED' | 'UPDATED' | 'RESOLVED' | 'REOPENED';
  source_timestamp?: string;
  occurred_at?: string;
}

export interface ScoreDecisionDetail {
  decision_id: string;
  source_timestamp: string;
  score: number;
  threshold: number;
  is_anomaly: boolean;
}
```

Change `AlertDetail.events` and `AlertDetail.decisions` to these arrays. Do not introduce a CSS framework.

- [ ] **Step 4: Render existing detail fields**

In `AlertPanel`, add an ordered event list with `data-testid="alert-event-timeline"` and a three-column decision table with `data-testid="alert-decision-table"`. Show source time, score, threshold, and anomaly/normal outcome; render empty-state text when either list is empty.

- [ ] **Step 5: Convert RcaPanel to inline styles and safe error typing**

Follow the inline style tokens already used in `AlertPanel`: `#1e293b` surface, `#334155` border, `#f8fafc` primary text, `#94a3b8` secondary text, `#38bdf8` citations, `#10b981` complete, and `#f59e0b` unavailable. Replace `catch (err: any)` with:

```typescript
} catch (err: unknown) {
  setError(err instanceof Error ? err.message : 'Failed to generate root-cause analysis');
}
```

Set `type="button"`, `aria-busy={isLoading}`, and `aria-live="polite"` on the changing status/content region.

- [ ] **Step 6: Verify frontend behavior and coverage**

Run:

```powershell
Push-Location apps/operator-console
npm run test:coverage
npm run build
Pop-Location
```

Expected: all frontend suites pass at the configured 80% thresholds and TypeScript/Vite build succeeds without Tailwind.

- [ ] **Step 7: Commit the focused UI repair**

```powershell
git add apps/operator-console/src/types.ts apps/operator-console/src/components/RcaPanel.tsx apps/operator-console/src/components/AlertPanel.tsx apps/operator-console/src/components/__tests__/RcaPanel.test.tsx apps/operator-console/src/components/__tests__/AlertPanel.test.tsx
git commit -m "fix: render grounded rca evidence without tailwind"
```

---

### Task 6: Make the localhost portfolio demo one command

**Files:**
- Modify: `deploy/preflight.py:14-80`
- Modify: `tests/test_deploy_preflight.py:9-27`
- Modify: `scripts/run_portfolio_demo.ps1:1-53`
- Create: `tests/test_portfolio_demo_script.py`
- Modify: `.env.example:1-21`
- Modify: `docs/RUNBOOK.md`

**Interfaces:**
- Consumes: Docker with Compose, free/bound localhost ports, processed Phase 1B telemetry, research-candidate inputs/package, and optional provider environment variables.
- Produces: `verify_host_environment(config: PreflightConfig | None = None) -> PreflightResult`; one `scripts/run_portfolio_demo.ps1` command that starts and verifies the local stack, runs the bounded journey, and prints an explicit teardown command.

- [ ] **Step 1: Write failing preflight tests for the actual topology**

```python
def test_default_preflight_uses_compose_ports() -> None:
    assert DEFAULT_PREFLIGHT_CONFIG.required_ports == (8000, 5173, 5432, 29092, 9090, 3001, 5000)


def test_preflight_fails_without_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("deploy.preflight.shutil.which", lambda _: None)
    result = verify_host_environment()
    assert result.passed is False
    assert "Docker CLI" in result.errors
```

Inject `required_paths=()` in unit tests that do not exercise file checks. Add one path test requiring `compose.yaml`, the processed telemetry parquet, and either an existing research package or all inputs consumed by `build_research_candidate.ps1`.

- [ ] **Step 2: Add a static contract for the PowerShell runner**

```python
def test_demo_script_owns_stack_start_readiness_and_teardown_message() -> None:
    script = Path("scripts/run_portfolio_demo.ps1").read_text(encoding="utf-8")
    assert "python -m deploy.preflight" in script
    assert "docker compose up -d --build" in script
    assert "ALLOW_RESEARCH_CANDIDATE" in script
    assert "SCORING_MANIFEST_SHA256" in script
    assert "operator-console.live.spec.ts" in script
    assert "docker compose down" in script
    assert "docker compose down -v" not in script
```

- [ ] **Step 3: Run focused tests and confirm the orphaned preflight/script behavior**

Run:

```powershell
python -m pytest tests/test_deploy_preflight.py tests/test_portfolio_demo_script.py -q
```

Expected: tests fail on outdated ports, missing Docker/path checks, and absent Compose/browser orchestration.

- [ ] **Step 4: Implement explicit preflight checks**

Extend the frozen config with:

```python
required_ports: tuple[int, ...] = (8000, 5173, 5432, 29092, 9090, 3001, 5000)
required_paths: tuple[str, ...] = (
    "compose.yaml",
    "data/processed/phase1b/metropt3/telemetry.parquet",
)
```

Use `shutil.which("docker")` and `subprocess.run(["docker", "compose", "version"], check=False, capture_output=True, text=True)`. Append exact missing paths to `errors`. Keep already-bound ports as warnings because an existing healthy local stack is reusable.

- [ ] **Step 5: Implement ordered PowerShell orchestration**

The script must perform this exact order and stop on any non-zero command:

```powershell
python -m deploy.preflight
if (-not (Test-Path -LiteralPath "artifacts/research-candidate/manifest.json")) {
    & "$PSScriptRoot/build_research_candidate.ps1"
}
$env:ALLOW_RESEARCH_CANDIDATE = "true"
$env:SCORING_MANIFEST_SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath "artifacts/research-candidate/manifest.json").Hash.ToLowerInvariant()
docker compose up -d --build
```

Poll `http://127.0.0.1:8000/readyz`, `http://127.0.0.1:5173/`, `http://127.0.0.1:9090/-/ready`, `http://127.0.0.1:3001/api/health`, and `http://127.0.0.1:5000/health` for at most 120 seconds. On timeout, run `docker compose ps` and `docker compose logs --tail 100` and exit non-zero.

After readiness, run the live Playwright file from `apps/operator-console`. Print `docker compose down` as the non-volume-destroying teardown command. Do not automatically delete containers, volumes, artifacts, or evidence.

- [ ] **Step 6: Document boundaries and credentials**

In `.env.example` and `docs/RUNBOOK.md`, state that all services bind to localhost, the checked-in PostgreSQL/Grafana values are local-demo credentials only, blank RCA key means evidence-preserving fallback, and non-local exposure is prohibited until Prong 5.

- [ ] **Step 7: Verify script structure without starting the stack**

Run:

```powershell
python -m pytest tests/test_deploy_preflight.py tests/test_portfolio_demo_script.py -q
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path scripts/run_portfolio_demo.ps1), [ref]$null, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -ne 0) { $parseErrors; exit 1 }
```

Expected: tests and PowerShell parsing pass. Do not execute the demo until Task 10 supplies qualifying Phase 8/9 evidence.

- [ ] **Step 8: Commit the demo orchestration slice**

```powershell
git add deploy/preflight.py tests/test_deploy_preflight.py scripts/run_portfolio_demo.ps1 tests/test_portfolio_demo_script.py .env.example docs/RUNBOOK.md
git commit -m "feat: run the localhost portfolio demo from one command"
```

---

### Task 7: Require browser and dependency-backed checks in CI

**Files:**
- Modify: `.github/workflows/ci.yml:12-40`
- Modify: `apps/operator-console/playwright.config.ts:1-30`
- Modify: `apps/operator-console/e2e/operator-console.live.spec.ts:1-39`
- Modify: `tests/integration/test_alert_persistence.py:18-33`
- Modify: `tests/integration/test_console_stream_persistence.py:13-39`
- Modify: `tests/integration/test_kafka_replay.py:26-38`
- Modify: `tests/integration/test_online_worker.py:33-45`
- Modify: `tests/integration/test_rca_persistence.py:15-32`
- Create: `tests/build_compose_fixture.py`

**Interfaces:**
- Consumes: normal CI with no runtime dependencies and a separate Compose-backed job with required PostgreSQL/Kafka services.
- Produces: mocked Playwright evidence on every PR; required dependency tests that fail instead of skip when `REQUIRE_RUNTIME_DEPS=1`; console image build/smoke evidence; live-backend Playwright in the Compose job.

- [ ] **Step 1: Add fail-closed dependency fixture behavior**

In each dependency test module, centralize the existing availability catch locally with this rule:

```python
def dependency_unavailable(message: str) -> None:
    if os.environ.get("REQUIRE_RUNTIME_DEPS") == "1":
        pytest.fail(message)
    pytest.skip(message)
```

Replace direct PostgreSQL/Kafka `pytest.skip` calls with `dependency_unavailable(message)`. Add one unit test per helper branch or a parametrized helper test proving required mode calls `pytest.fail`.

- [ ] **Step 2: Split Playwright projects by evidence type**

Define `mocked` and `live` Playwright projects with `testMatch` values `operator-console.spec.ts` and `operator-console.live.spec.ts`. Gate the live spec with `test.skip(process.env.RUN_LIVE_UI !== '1', 'RUN_LIVE_UI=1 required')`; absent live opt-in must skip rather than masquerade as a live pass. Set the top-level server condition so CI does not start Vite over the deployed console:

```typescript
webServer: process.env.RUN_LIVE_UI === '1' ? undefined : {
  command: 'npm run dev',
  url: 'http://127.0.0.1:5173',
  reuseExistingServer: !process.env.CI,
  timeout: 15000,
},
```

- [ ] **Step 3: Run local browser contract checks**

Run:

```powershell
Push-Location apps/operator-console
npm ci
npx playwright install chromium
npx playwright test --project=mocked
Pop-Location
```

Expected: mocked browser tests pass without a backend and are labeled only as mocked evidence.

- [ ] **Step 4: Extend the normal quality job**

After frontend build, install Chromium and run only the mocked project:

```yaml
      - name: Install Playwright Chromium
        working-directory: apps/operator-console
        run: npx playwright install --with-deps chromium
      - name: Run mocked browser flow
        working-directory: apps/operator-console
        run: npx playwright test --project=mocked
      - name: Build console container
        run: docker build -t irp-operator-console-ci apps/operator-console
```

- [ ] **Step 5: Add the Compose-backed integration job**

Create `runtime-integration` with `needs: quality`. Start only PostgreSQL and Kafka, export host URLs plus `REQUIRE_RUNTIME_DEPS=1`, and run:

```yaml
      - run: docker compose up -d postgres kafka
      - run: pytest tests/integration/test_alert_persistence.py tests/integration/test_console_stream_persistence.py tests/integration/test_kafka_replay.py tests/integration/test_online_worker.py tests/integration/test_rca_persistence.py -q
        env:
          REQUIRE_RUNTIME_DEPS: "1"
          DATABASE_URL: postgresql://irp:irp_password@127.0.0.1:5432/irp
          KAFKA_BOOTSTRAP_SERVERS: 127.0.0.1:29092
```

Use `if: always()` to print `docker compose ps` and bounded logs after failures. Use `docker compose down` without `-v` in CI cleanup.

- [ ] **Step 6: Add console image smoke and deployed-proxy coverage**

Create this bounded CI-only package builder by reusing the existing test helper:

```python
from __future__ import annotations

import shutil
from pathlib import Path

from tests.helpers_champion import build_research_candidate_from_mock_run


def main() -> None:
    fixture = build_research_candidate_from_mock_run(Path("artifacts/ci-compose-fixture"))
    target = Path("artifacts/research-candidate")
    shutil.copytree(fixture.package_dir, target, dirs_exist_ok=True)
    print(fixture.manifest_sha256)


if __name__ == "__main__":
    main()
```

In the integration job, use:

```yaml
      - name: Build CI-only research package
        run: echo "SCORING_MANIFEST_SHA256=$(python -m tests.build_compose_fixture)" >> "$GITHUB_ENV"
      - name: Start deployed API and console
        run: docker compose up -d --build scoring-api operator-console
        env:
          ALLOW_RESEARCH_CANDIDATE: "true"
      - name: Run deployed console flow
        working-directory: apps/operator-console
        run: npx playwright test --project=live
        env:
          RUN_LIVE_UI: "1"
```

Assert `/healthz` through port 5173 returns the scoring API health envelope. This specifically exercises nginx service DNS rather than Vite's development proxy; the fixture is test evidence and never release evidence.

- [ ] **Step 7: Validate workflow syntax and focused tests**

Run:

```powershell
python -m pytest tests/integration/test_alert_persistence.py tests/integration/test_console_stream_persistence.py tests/integration/test_kafka_replay.py tests/integration/test_online_worker.py tests/integration/test_rca_persistence.py -q
docker compose config --quiet
```

Expected locally: dependencies may skip only because `REQUIRE_RUNTIME_DEPS` is absent. Expected in `runtime-integration`: the same missing dependency is a failure.

- [ ] **Step 8: Commit the CI evidence boundary**

```powershell
git add .github/workflows/ci.yml apps/operator-console/playwright.config.ts apps/operator-console/e2e/operator-console.live.spec.ts tests/integration/test_alert_persistence.py tests/integration/test_console_stream_persistence.py tests/integration/test_kafka_replay.py tests/integration/test_online_worker.py tests/integration/test_rca_persistence.py tests/build_compose_fixture.py
git commit -m "ci: require browser and dependency-backed integration checks"
```

---

### Task 8: Replace Phase 8 in-process certification with real recovery drills

**Files:**
- Modify: `src/industrial_reliability/phase8_live_gate.py:1-147`
- Modify: `tests/test_phase8_live_gate.py`
- Modify: `tests/integration/test_phase8_fault_drills.py:1-211`
- Modify: `scripts/run_phase8_live_fault_drills.ps1:1-4`
- Preserve: `src/industrial_reliability/fault_report.py` and its `UNIT`/`IN_PROCESS` contract drills

**Interfaces:**
- Consumes: healthy Compose stack, exact Git SHA, host Kafka `127.0.0.1:29092`, API `127.0.0.1:8000`, Prometheus `127.0.0.1:9090`, PostgreSQL-backed alert API, and the fixed known-abnormal range `2020-05-29T22:00:00` through `2020-05-30T00:30:00` at 1000×.
- Produces: `run_phase8_live_gate(output_dir: Path | None, git_sha: str | None) -> LiveFaultReportV1`; schema `phase8-live-fault-drills-v1`; evidence level `INTEGRATION`; four real drill records with recovery, offset, loss/duplicate, quarantine, and alert-persistence observations. Only this public function may emit the integration report, and it always uses native real command/network implementations.

- [ ] **Step 1: Define and test the live evidence schema**

```python
@dataclass(frozen=True)
class LiveDrillResultV1:
    drill_type: str
    expected_classification: str
    actual_classification: str
    passed: bool
    recovery_seconds: float | None
    messages_before: int
    messages_after: int
    committed_offset_before: int | None
    committed_offset_after: int | None
    lost_messages: int
    duplicate_messages: int
    quarantine_messages: int
    alert_persisted: bool | None
    alert_id: str | None
    evidence_summary: str
```

Add `LiveFaultReportV1` with exact SHA, `evidence_level="INTEGRATION"`, `verdict`, four drills, prerequisite errors, timestamp, and `self_sha256`. Tests must reject an all-zero/foreign SHA and verify the self-hash.

- [ ] **Step 2: Inject native command and HTTP seams for unit tests**

Define private native helpers:

```python
def _run_command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True, shell=False)


def _request_json(method: str, url: str, payload: Mapping[str, Any] | None) -> Mapping[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10.0) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, Mapping):
        raise ValueError(f"expected JSON object from {url}")
    return decoded
```

Keep `run_phase8_live_gate` non-injectable and route native subprocess work through `_run_command`; route HTTP through `_request_json`. Extract pure parsing/classification helpers for unit tests; their synthetic report builder must force `evidence_level="UNIT"`. Unit tests may exercise `BLOCKED` preflight output but may never create an `INTEGRATION`/`LIVE` passing artifact. Only the required Compose integration test can exercise the passing public path.

- [ ] **Step 3: Add fail-closed preflight behavior**

Before drills, require `docker compose config --quiet`, healthy required services, reachable Prometheus, the real telemetry parquet, and research package manifest. If any check fails, write a self-hashed `verdict: "BLOCKED"` report with the error list and return exit code `1`; never call `build_fault_report` from the in-process path.

- [ ] **Step 4: Implement broker interruption and recovery**

Start a bounded replay, capture consumer group offsets and message counts, stop Kafka with `docker compose stop kafka`, observe the service-fault signature, restart with `docker compose start kafka`, wait for health, and capture post-recovery offsets/counts. Always restart Kafka in `finally`. Pass only when recovery occurs within the recorded time, the consumer resumes, offsets do not move backward, and computed loss/duplicate counts are zero.

- [ ] **Step 5: Implement database interruption and recovery**

Capture the alert-service committed offset, stop PostgreSQL, publish a score decision that would create/update an alert, verify the failed write does not advance that offset, restart PostgreSQL in `finally`, and verify the record is persisted exactly once after recovery. Record recovery time and `alert_persisted=True` only after a real API/database read.

- [ ] **Step 6: Implement malformed telemetry isolation**

Publish invalid raw bytes to the real telemetry topic with `AIOKafkaProducer`. Read the quarantine topic and Prometheus counter before/after. Pass only when quarantine increases, the worker remains alive, and no score/alert is produced for that invalid record.

- [ ] **Step 7: Implement known-abnormal replay evidence**

POST the fixed range to `/v1/replays`, wait for terminal replay status, then query `/v1/replays/{session_id}/alerts`. Pass only when a persisted alert exists and its evidence/decision identities bind to the replay session and research package. This is runtime demonstration of an already-published interval, not model selection or holdout retuning.

- [ ] **Step 8: Replace the old mocked integration test**

Keep in-process classification tests under unit scope. Rewrite `tests/integration/test_phase8_fault_drills.py` so `REQUIRE_RUNTIME_DEPS=1` invokes the real runner against Compose and asserts all four drill names, zero loss/duplicates, restored services, `INTEGRATION`, exact SHA, and valid self-hash.

- [ ] **Step 9: Verify unit contracts, then run the real gate only with prerequisites**

Run:

```powershell
python -m pytest tests/test_phase8_live_gate.py tests/test_fault_report.py -q
$sha = (git rev-parse HEAD).Trim().ToLowerInvariant()
python -m industrial_reliability.phase8_live_gate --git-sha $sha --output-dir "artifacts/certification/$sha"
```

Expected: unit tests pass. The live command either produces a four-drill `PASS` report from real dependencies or exits non-zero with `BLOCKED`/`FAIL`; it never emits an in-process pass.

- [ ] **Step 10: Commit the Phase 8 evidence implementation**

```powershell
git add src/industrial_reliability/phase8_live_gate.py tests/test_phase8_live_gate.py tests/integration/test_phase8_fault_drills.py scripts/run_phase8_live_fault_drills.ps1
git commit -m "feat: collect real phase 8 recovery evidence"
```

---

### Task 9: Certify Phase 9 only after a deployed persisted-alert round trip

**Files:**
- Modify: `src/industrial_reliability/phase9_live_gate.py:1-213`
- Modify: `tests/test_phase9_live_gate.py:1-78`
- Modify: `tests/integration/test_rca_persistence.py`
- Modify: `scripts/run_phase9_live_gate.ps1:1-4`
- Preserve: `src/industrial_reliability/rca_gate_checks.py` as the in-process contract gate

**Interfaces:**
- Consumes: real `alert_id` produced by Task 8, deployed `POST /v1/alerts/{alert_id}/rca`, deployed `GET /v1/alerts/{alert_id}`, exact Git SHA, and optional provider configuration already inside `scoring-api`.
- Produces: `classify_deployed_rca(posted: Mapping[str, Any], stored: Mapping[str, Any]) -> tuple[str, str, str]`; `run_phase9_live_gate(alert_id: str, output_dir: Path | None, git_sha: str | None, base_url: str = "http://127.0.0.1:8000") -> dict[str, Any]`. The public runner uses real HTTP only; fallback is `INTEGRATION/FALLBACK_ONLY`; a complete real provider report is `LIVE/LIVE_OPENAI`.

- [ ] **Step 1: Replace configured-key inference with response-derived tests**

```python
def _rca_payload(status: str, provider_model: str | None) -> dict[str, Any]:
    return {
        "report_id": "rca-1",
        "alert_id": "11111111-1111-1111-1111-111111111111",
        "status": status,
        "provider_model": provider_model,
        "summary": "Provider RCA unavailable; evidence preserved.",
        "observations": [],
        "uncertainty": ["Anomaly evidence does not prove a mechanical root cause."],
        "evidence_ids": ["evidence-111111111111111111111111"],
        "evidence_bundle_sha256": "c" * 64,
    }


def test_classifies_verified_unavailable_round_trip_as_fallback() -> None:
    rca = _rca_payload("UNAVAILABLE", None)
    assert classify_deployed_rca(rca, rca) == (
        "FALLBACK_ONLY",
        "INTEGRATION",
        "phase-9-rca-fallback-v1",
    )


def test_classifies_verified_complete_round_trip_as_live() -> None:
    rca = _rca_payload("COMPLETE", "gpt-4o-mini")
    assert classify_deployed_rca(rca, rca) == (
        "LIVE_OPENAI",
        "LIVE",
        "phase-9-rca-openai-v1",
    )
```

Add failing cases for missing alert, POST/GET report mismatch, absent citations, invalid self-hash input, provider model on `UNAVAILABLE`, and configured key with an `UNAVAILABLE` response. The last case must remain fallback, proving a non-empty key never establishes live evidence.

- [ ] **Step 2: Run the focused tests and observe current in-process inference**

Run:

```powershell
python -m pytest tests/test_phase9_live_gate.py -q
```

Expected: tests fail because the current gate never calls the deployed API and sets `LIVE_OPENAI` from environment presence.

- [ ] **Step 3: Use a small stdlib deployed round-trip**

Implement one private `request_json` helper using `urllib.request` with JSON bodies and a bounded timeout. Do not expose injection on the public runner. Execute:

1. `POST /v1/alerts/{alert_id}/rca`.
2. `GET /v1/alerts/{alert_id}`.
3. Confirm the stored `data.rca.report_id`, alert ID, evidence bundle hash, status, provider model, citations, and uncertainty equal the POST result.

Derive mode only from the verified stored response:

```python
if rca["status"] == "COMPLETE" and rca.get("provider_model"):
    provider_mode = "LIVE_OPENAI"
    evidence_level = "LIVE"
    schema_version = "phase-9-rca-openai-v1"
elif rca["status"] == "UNAVAILABLE" and rca.get("provider_model") is None:
    provider_mode = "FALLBACK_ONLY"
    evidence_level = "INTEGRATION"
    schema_version = "phase-9-rca-fallback-v1"
else:
    raise ValueError("deployed RCA response does not match a certifiable provider mode")
```

- [ ] **Step 4: Preserve closed-world and secret boundaries**

Require every observation evidence ID to occur in `rca.evidence_ids`, require the non-causal uncertainty sentence, and include no request headers, environment values, raw telemetry, connection strings, or local paths in report details. Report only mode, status, IDs, hashes, endpoint origin, and pass/fail check summaries.

- [ ] **Step 5: Bind the PowerShell wrapper to the Phase 8 alert**

Make `scripts/run_phase9_live_gate.ps1` read the exact Phase 8 report under `artifacts/certification/$sha`, select the known-abnormal drill's `alert_id`, and pass it as `--alert-id`. If Phase 8 is absent, non-passing, or lacks an alert ID, exit before calling Phase 9.

- [ ] **Step 6: Add the real persistence integration assertion**

Under `REQUIRE_RUNTIME_DEPS=1`, create/persist an alert through the real stack, call the deployed RCA endpoint without a provider key, fetch the detail, and assert the report is stored once with `UNAVAILABLE`, evidence IDs, and `INTEGRATION/FALLBACK_ONLY` gate output. Live-provider CI remains opt-in because credentials are not a repository prerequisite.

- [ ] **Step 7: Verify fallback locally; use a rotated key only when explicitly available**

Run:

```powershell
python -m pytest tests/test_phase9_live_gate.py tests/test_rca_openai.py tests/test_rca_evidence.py -q
$sha = (git rev-parse HEAD).Trim().ToLowerInvariant()
& scripts/run_phase9_live_gate.ps1
```

Expected without a key: real API/persistence round trip, `INTEGRATION`, `FALLBACK_ONLY`, `PASS`. Expected with an environment-provided rotated key: `LIVE` only if the returned and persisted report is `COMPLETE`; provider failure remains `INTEGRATION/FALLBACK_ONLY` or fails according to the requested release profile.

- [ ] **Step 8: Commit the Phase 9 operational gate**

```powershell
git add src/industrial_reliability/phase9_live_gate.py tests/test_phase9_live_gate.py tests/integration/test_rca_persistence.py scripts/run_phase9_live_gate.ps1
git commit -m "feat: certify deployed phase 9 fallback and provider modes"
```

---

### Task 10: Replace replay benchmark constants with captured samples

**Files:**
- Create: `ops/benchmarks/replay-workload.json`
- Modify: `src/industrial_reliability/decision_gate.py:30-69`
- Modify: `src/industrial_reliability/replay_benchmark.py:1-99`
- Modify: `tests/test_replay_benchmark.py:1-39`
- Modify: `scripts/run_portfolio_demo.ps1`

**Interfaces:**
- Consumes: frozen calibration-range workload, deployed replay API, Prometheus counters/histograms, `docker stats`, package/contract/dataset hashes, exact Git SHA, and per-repetition raw samples.
- Produces: `ReplayBenchmarkSampleV1`; `ReplayBenchmarkConfig`; `ReplayBenchmarkResultV2`; `run_benchmark(config: ReplayBenchmarkConfig) -> ReplayBenchmarkResultV2`; dynamic report under `artifacts/benchmarks/$sha/benchmark.json`. The public runner uses real API, Prometheus, and Docker observations; unit tests target pure parsers and aggregation.

- [ ] **Step 1: Freeze a non-holdout performance workload**

Create exactly:

```json
{
  "schema_version": "replay-workload-v1",
  "range_start": "2020-02-25T00:00:00",
  "range_end": "2020-02-25T06:00:00",
  "speed": 1000,
  "repetitions": 5,
  "restart_repetition": 3
}
```

This calibration-range workload measures runtime performance only and never updates a detector threshold, policy, or feasibility verdict.

- [ ] **Step 2: Write aggregation tests from explicit raw samples**

```python
def test_aggregate_samples_is_recomputable() -> None:
    samples = (
        ReplayBenchmarkSampleV1(
            repetition=1,
            source_events=1000,
            valid_windows=40,
            p50_latency_ms=100.0,
            p95_latency_ms=140.0,
            throughput_events_per_second=250.0,
            max_consumer_lag=8.0,
            lag_drain_seconds=1.2,
            duplicate_rows=0,
            quarantine_rows=0,
            cpu_seconds=3.0,
            peak_rss_bytes=80_000_000,
            recovery_passed=True,
        ),
        ReplayBenchmarkSampleV1(
            repetition=2,
            source_events=1000,
            valid_windows=40,
            p50_latency_ms=110.0,
            p95_latency_ms=160.0,
            throughput_events_per_second=245.0,
            max_consumer_lag=6.0,
            lag_drain_seconds=0.9,
            duplicate_rows=0,
            quarantine_rows=1,
            cpu_seconds=3.2,
            peak_rss_bytes=82_000_000,
            recovery_passed=True,
        ),
    )
    result = aggregate_samples(
        git_sha="a" * 40,
        package_sha256="b" * 64,
        contract_sha256="c" * 64,
        source_dataset_sha256="d" * 64,
        workload_sha256="e" * 64,
        samples=samples,
    )
    assert result.source_events == 2000
    assert result.valid_windows == 80
    assert result.p50_latency_ms == 105.0
    assert result.p95_latency_ms == 159.0
    assert result.peak_rss_bytes == 82_000_000
    assert result.raw_samples == samples
```

Add tests that empty samples, NaN/negative metrics, mismatched hashes, zero Git SHA, missing raw sample fields, and a requested regression budget without an existing baseline fail closed.

- [ ] **Step 3: Run tests and prove defaults currently fabricate the result**

Run:

```powershell
python -m pytest tests/test_replay_benchmark.py tests/test_phase10a_gate.py -q
```

Expected: the new sample API is absent and the current CLI still emits hard-coded `4.2`, `12.8`, and `12500.0` values.

- [ ] **Step 4: Define immutable sample and result records**

`ReplayBenchmarkSampleV1` must store repetition, source events, valid windows, p50/p95 latency, throughput, peak/drained lag, drain seconds, duplicate/quarantine counts, CPU seconds, peak RSS, and recovery pass. `ReplayBenchmarkConfig` stores the parsed frozen workload, exact Git SHA, verified manifest path, API/Prometheus origins, and output directory. `ReplayBenchmarkResultV2` stores identities, workload hash, tuple of raw samples, recomputed aggregates, and a self-hash. Validate every numeric field as finite/non-negative and every identity hash at construction.

Use this stdlib linear percentile so aggregates are deterministic:

```python
def percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight
```

- [ ] **Step 5: Capture real timing and runtime observations**

Use `time.perf_counter_ns()` for elapsed/recovery timing. Query Prometheus for score latency histogram, consumer lag peak/drain, duplicate/quarantine counters, and valid windows. Poll `docker stats --no-stream --format "{{json .}}"` once per second through `subprocess.run` with an argument list; retain timestamped CPU-percent and memory samples, integrate CPU percent over elapsed time to derive container CPU seconds, and take the maximum memory usage as peak RSS. Retain every raw timing, Prometheus, and container-stat sample needed to recompute the aggregates.

- [ ] **Step 6: Remove the constants-only CLI path**

Require `--workload ops/benchmarks/replay-workload.json`, `--git-sha`, `--package-manifest`, and `--output-dir`. Resolve contract/source/package hashes from the verified manifest. A missing service, metric, identity, sample, or recovery result exits non-zero and writes no passing report.

- [ ] **Step 7: Defer the regression budget until the baseline exists**

The first successful report sets `regression_budget: null` and states `baseline only; no budget established`. A later plan may add a budget using at least one reviewed exact-SHA baseline. Do not invent thresholds in this task.

- [ ] **Step 8: Add measured benchmark collection to the demo**

After the deployed journey and before aggregate certification, call the benchmark CLI and print its artifact path. Do not feed the result into the stopped Spark/OpenVINO gates; their reconsideration triggers remain dormant.

- [ ] **Step 9: Verify aggregation and one real baseline**

Run:

```powershell
python -m pytest tests/test_replay_benchmark.py tests/test_phase10a_gate.py -q
$sha = (git rev-parse HEAD).Trim().ToLowerInvariant()
python -m industrial_reliability.replay_benchmark --workload ops/benchmarks/replay-workload.json --git-sha $sha --package-manifest artifacts/research-candidate/manifest.json --output-dir "artifacts/benchmarks/$sha"
```

Expected: unit tests pass; the live command either writes a self-hashed V2 report with raw samples and recomputable aggregates or exits non-zero without a synthetic pass.

- [ ] **Step 10: Commit the measured benchmark implementation**

```powershell
git add ops/benchmarks/replay-workload.json src/industrial_reliability/decision_gate.py src/industrial_reliability/replay_benchmark.py tests/test_replay_benchmark.py scripts/run_portfolio_demo.ps1
git commit -m "perf: measure the frozen replay workload"
```

---

### Task 11: Publish the evidence-traceable interview package

**Files:**
- Create: `docs/INTERVIEW_GUIDE.md`
- Modify: `README.md`
- Modify: `docs/RUNBOOK.md`
- Modify: `tests/test_portfolio_claims.py`
- Modify: `scripts/run_portfolio_demo.ps1`

**Interfaces:**
- Consumes: authoritative Phase 1B metrics, exact-SHA Phase 8/9 reports, measured benchmark output, current architecture/results links, and the one-command demo.
- Produces: one capability/evidence/limitation table; one timed ten-minute demo; a README entry point; a final demo command that certifies only after mandatory evidence passes.

- [ ] **Step 1: Write documentation contract tests before prose**

```python
def test_interview_guide_preserves_claim_boundaries() -> None:
    guide = Path("docs/INTERVIEW_GUIDE.md").read_text(encoding="utf-8")
    required = (
        "13.146",
        "30.670",
        "selected_model: null",
        "RESEARCH_CANDIDATE",
        "No production champion",
        "No distributed Big Data claim",
        "No availability SLO claim",
        "No certified production release claim",
    )
    assert all(value in guide for value in required)


def test_interview_guide_links_every_quantitative_section() -> None:
    guide = Path("docs/INTERVIEW_GUIDE.md").read_text(encoding="utf-8")
    assert "docs/results/phase-1b-metrics.json" in guide
    assert "artifacts/certification/$sha" in guide
    assert "artifacts/benchmarks/$sha/benchmark.json" in guide
```

- [ ] **Step 2: Run the tests and observe the absent guide**

Run:

```powershell
python -m pytest tests/test_portfolio_claims.py -q
```

Expected: the guide contract fails because the file does not yet exist.

- [ ] **Step 3: Write the capability/evidence/limitation matrix**

Use these rows in this order: 10.77M-row memory-bounded ingestion; leakage-safe frozen evaluation; deterministic model ladder; operational false-alarm benchmark; online/offline parity; event-driven runtime; grounded RCA fallback; evidence-gated technology decisions; automated quality; real recovery evidence; measured runtime baseline. Each row must link one current artifact and state one explicit limitation.

- [ ] **Step 4: Write the timed ten-minute script**

Use this exact timing:

1. `0:00–1:00` — truth statement and permanent `NOT FEASIBLE` verdict.
2. `1:00–2:30` — 10.77M-row ingestion and leakage-safe split contract.
3. `2:30–4:00` — 4/4 detection versus 13.146–30.670 false episodes/day.
4. `4:00–6:30` — one-command deployed replay, score, alert, and console flow.
5. `6:30–8:00` — grounded RCA fallback, citations, and non-causal disclaimer.
6. `8:00–9:00` — real recovery evidence and measured benchmark report.
7. `9:00–10:00` — limitations: no champion, no breakthrough claim, no distributed Big Data, no availability SLO, no non-local deployment, no production release.

- [ ] **Step 5: Finish the demo's evidence order**

After Tasks 8–10, update `run_portfolio_demo.ps1` to run Phase 8, read its persisted alert ID, run Phase 9, run the measured benchmark, then invoke release certification against `artifacts/certification/$sha`. Because Task 1 returns exit code `1` for incomplete evidence, the script cannot print completion unless all mandatory evidence validates.

Before invoking release certification, copy the immutable authoritative metrics into the exact-SHA set without modifying the source:

```powershell
$certDir = "artifacts/certification/$sha"
Copy-Item -LiteralPath "docs/results/phase-1b-metrics.json" -Destination "$certDir/phase-1b-metrics.json"
python -m industrial_reliability.release_certification --artifact-dir $certDir --output "$certDir/release-certification.json" --git-sha $sha
```

- [ ] **Step 6: Link the guide without expanding the README chronology**

Put the negative result, one-command demo, evidence-level table, and `docs/INTERVIEW_GUIDE.md` link before phase chronology. Keep deep architecture links below. Update the runbook with prerequisites, expected fallback behavior, artifact locations, and non-destructive teardown.

- [ ] **Step 7: Run documentation, quality, and full local gates**

Run:

```powershell
python -m pytest tests/test_portfolio_claims.py tests/test_phase1b_published_results.py -q
ruff check .
ruff format --check .
mypy src
python -m pytest -m "not slow"
python -m pip check
python -m build
Push-Location apps/operator-console
npm run test:coverage
npm run build
npx playwright test --project=mocked
Pop-Location
docker compose config --quiet
```

Expected: all static/local automated gates pass. These commands do not by themselves certify real dependency recovery or provider behavior.

- [ ] **Step 8: Run the exact-SHA demo/certification gate**

Run:

```powershell
& scripts/run_portfolio_demo.ps1
$sha = (git rev-parse HEAD).Trim().ToLowerInvariant()
$report = Get-Content -Raw "artifacts/certification/$sha/release-certification.json" | ConvertFrom-Json
if (-not $report.is_certified -or $report.git_sha -ne $sha -or $report.verdict -eq "INVALID") { exit 1 }
```

Expected: the command passes only with real Phase 8 `INTEGRATION`, real Phase 9 `INTEGRATION` fallback or `LIVE` provider evidence, exact hashes/SHA, and a measured benchmark. If prerequisites are missing, record the blocked gate and do not claim completion.

- [ ] **Step 9: Commit only the interview package**

```powershell
git add docs/INTERVIEW_GUIDE.md README.md docs/RUNBOOK.md tests/test_portfolio_claims.py scripts/run_portfolio_demo.ps1
git commit -m "docs: publish the evidence-traceable interview guide"
```

---

## Final branch and GitHub gate

- [ ] **Step 1: Verify the smart-commit stack and clean scope**

Run:

```powershell
git status --short
git log --oneline --decorate 300a13679be64457745676a36d0135093affde4b..HEAD
git diff --check 300a13679be64457745676a36d0135093affde4b..HEAD
```

Expected: the planned intent commits are present, no unrelated files are staged, and dynamic `artifacts/` outputs are not committed.

- [ ] **Step 2: Review before publishing**

Use `superpowers:requesting-code-review` for spec compliance, then an independent code-quality/security review. Block publishing on any certification bypass, secret exposure, non-local binding, hidden skipped dependency test, holdout-policy mutation, or unsupported claim.

- [ ] **Step 3: Push the existing feature branch without rewriting history**

```powershell
git push -u origin fix/interview-readiness-hardening
```

Do not rebase after other contributors use the branch and do not force-push.

- [ ] **Step 4: Create the PR with evidence-scoped language**

```powershell
$body = @'
## What
Hardens fail-closed release certification, repairs the localhost deployed demo, replaces mocked operational claims with dependency-backed evidence, captures a measured replay baseline, and publishes an evidence-traceable interview guide.

## Why
The negative ML result is valuable, but current deployment seams and certification logic let prose outrun committed evidence.

## Testing
- Python quality, typing, package build, and non-slow tests
- Frontend coverage/build and mocked Playwright
- Required PostgreSQL/Kafka integration job
- Local exact-SHA Phase 8 and Phase 9 certification artifacts
- Measured replay benchmark with raw samples

## Claim boundary
No production champion, breakthrough benchmark, distributed Big Data, availability SLO, non-local deployment, or production-certified release is claimed.
'@
gh pr create --base main --head fix/interview-readiness-hardening --title "fix: harden interview readiness and release evidence" --body $body
```

Before executing the command, extend the here-string with the exact commit list, local command results, Compose result, exact-SHA Phase 8/9/benchmark artifact paths, localhost security boundary, and any blocked prerequisites from the completed run. Do not claim unavailable evidence.

- [ ] **Step 5: Use read-only GitHub checks before merge**

```powershell
$pr = gh pr view --json number,headRefOid,mergeable,reviewDecision,statusCheckRollup,url | ConvertFrom-Json
gh pr checks $pr.number
git rev-parse HEAD
```

Expected: PR head OID equals local HEAD, mergeable is not conflicting, required CI jobs pass, review is approved, and no security/quality blocker remains. A local pass or generated artifact alone is not merge evidence.

- [ ] **Step 6: Merge only after all gates support it**

Use the repository's normal reviewed merge method from GitHub. After merge, verify the resulting `main` workflow against the merge SHA with `gh run list --branch main --limit 5` and `gh run view`; do not describe the release as production-certified unless the exact merged SHA has a fresh valid mandatory evidence set.

---

## Self-review record

- **Spec coverage:** Prong 0 is Tasks 1–2; Prong 1 is Tasks 3–6; Prong 2 is Tasks 7–9; Prong 3 is Task 10; Prong 4 is Task 11. Prong 5 is preserved as a localhost-only constraint. Prong 6 and opportunistic code health remain deliberately deferred.
- **Placeholder scan:** Every implementation step names concrete files, interfaces, commands, expected outcomes, and commit boundaries. No deferred implementation marker is used.
- **Type consistency:** `ReleaseCertificationReportV1`, `RuntimeMetrics`, `AlertConsumer.metrics`, `LiveFaultReportV1`, deployed Phase 9 report fields, `ReplayBenchmarkSampleV1`, and `ReplayBenchmarkResultV2` have one name and contract throughout the plan.
- **Evidence boundary:** Unit/mocked checks stay non-release evidence; required runtime prerequisites fail closed; exact-SHA artifacts stay outside committed results; no step authorizes model retraining or holdout-based selection.
