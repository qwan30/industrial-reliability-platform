# Phase 6 Operator Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a React operator demo console that controls a real replay and shows live telemetry, score, durable alert, evidence, and provenance through real FastAPI/Kafka/PostgreSQL paths.

**Architecture:** FastAPI publishes versioned replay commands and runs one console-feed Kafka consumer that persists only status/score/alert stream references while broadcasting source-time-downsampled telemetry in memory. An SSE endpoint first returns a durable snapshot, replays persisted events after `Last-Event-ID`, then streams live events. A small React + Vite app uses the REST/SSE contracts; Playwright certifies the full path with real clicks and no route interception.

**Tech Stack:** Python 3.12, FastAPI `StreamingResponse`, Kafka, PostgreSQL, React, TypeScript, Vite, native SVG, Vitest, Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-24-post-phase-1-evidence-gated-roadmap-design.md`

## Global Constraints

- Begin only after Phase 5 produced a passing `artifacts/phase5/<replay-session-id>/phase5-gate.json` tied to the exact champion, contract, dataset, and locked alert-policy hashes.
- The console is an operator demo surface: include replay start/pause/resume/stop, speed/range, status/health, live downsampled telemetry and score, alerts, evidence, provenance, and RCA status/output.
- Exclude auth/RBAC, model promotion, policy editing, ML administration, raw-data exploration, multi-tenancy, and public-network operation.
- Bind host ports to localhost. Do not put API keys, local raw-data paths, stack traces, or database errors in browser responses.
- The browser consumes durable state from REST and live updates from SSE. Reconnect uses `Last-Event-ID` plus a fresh durable snapshot; raw telemetry is not stored in PostgreSQL.
- At replay speed, source timestamps stay unchanged. Downsample telemetry by source time, not wall-clock time.
- Use real Kafka, PostgreSQL, scoring API, worker, and alert consumer for Playwright certification. Do not use `page.route`, fixture-only UI state, mocked EventSource, or direct database seeding for the certified path.
- Keep branch coverage at or above 80% for Python and TypeScript logic; preserve keyboard operation, labels, focus visibility, semantic status, and non-color alert indicators.
- Synthetic CI evidence and private real-data evidence remain separately labeled.

---

### Task 1: Add durable stream cursors and the console event feed

**Files:**
- Create: `db/migrations/002_console_stream.sql`
- Create: `src/industrial_reliability/console_stream.py`
- Modify: `src/industrial_reliability/persistence.py`
- Create: `tests/test_console_stream.py`
- Create: `tests/integration/test_console_stream_persistence.py`

**Interfaces:**
- Consumes: Kafka `irp.replay.status.v1`, `irp.telemetry.v1`, `irp.scores.v1`, `irp.alerts.v1`; `ReplayStatusV1`, `TelemetryEventV1`, `ScoreDecisionV1`, `AlertEventV1`; Phase 5 `RuntimeStore`.
- Produces: `ConsoleEventV1(event_id, replay_session_id, event_type, source_timestamp, payload, durable)`, `ConsoleEventBroker.subscribe(session_id)`, `ConsoleFeed.process(record)`, store methods `append_console_event` and `events_after`; telemetry emits at most once per machine per 60 source seconds and is never persisted.

- [ ] **Step 1: Write failing downsample and cursor tests**

```python
def test_telemetry_downsamples_by_source_time() -> None:
    feed = ConsoleFeed(store=FakeStore(), broker=FakeBroker(), telemetry_interval_seconds=60)
    for seconds in (0, 10, 59, 60):
        feed.process(telemetry_record(datetime(2020, 4, 18) + timedelta(seconds=seconds)))
    assert [event.source_timestamp.second for event in feed.broker.events] == [0, 0]
    assert feed.store.console_events == []


@pytest.mark.integration
def test_durable_event_insert_is_idempotent(runtime_store: RuntimeStore) -> None:
    event = score_console_event(event_id="decision-1")
    runtime_store.append_console_event(event)
    runtime_store.append_console_event(event)
    assert runtime_store.events_after("session-1", after_event_id=None) == (event,)
```

- [ ] **Step 2: Run focused tests before adding the stream table**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_console_stream.py tests/integration/test_console_stream_persistence.py -q`

Expected: FAIL because `console_stream` and `console_events` do not exist.

- [ ] **Step 3: Add the pointer-only event table and feed**

```sql
CREATE TABLE console_events (
  stream_sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id text NOT NULL UNIQUE,
  replay_session_id text NOT NULL REFERENCES replay_sessions,
  event_type text NOT NULL CHECK (event_type IN ('status','score','alert')),
  source_timestamp timestamp NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX console_events_session_sequence_idx
  ON console_events (replay_session_id, stream_sequence);
```

```python
@dataclass(frozen=True)
class ConsoleEventV1:
    event_id: str
    replay_session_id: str
    event_type: Literal["status", "telemetry", "score", "alert"]
    source_timestamp: datetime
    payload: Mapping[str, JSONValue]
    durable: bool


def process(self, record: ConsumerRecord) -> None:
    event = self._decode(record)
    if event.event_type == "telemetry" and not self._downsampler.accept(event):
        self._consumer.commit(record)
        return
    if event.durable:
        self._store.append_console_event(event)
    self._broker.publish(event)
    self._consumer.commit(record)
```

Use immutable broker subscriber tuples and bounded queues of 256 events. A slow subscriber receives one `resync_required` marker and its queue is replaced; it cannot block Kafka consumption.

- [ ] **Step 4: Apply the migration and verify unit/integration behavior**

Run: `docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U irp -d irp -f /migrations/002_console_stream.sql`

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_console_stream.py tests/integration/test_console_stream_persistence.py -q`

Expected: PASS; only status/score/alert payloads occupy PostgreSQL.

- [ ] **Step 5: Commit the event feed**

```powershell
git add db/migrations/002_console_stream.sql src/industrial_reliability/console_stream.py src/industrial_reliability/persistence.py tests/test_console_stream.py tests/integration/test_console_stream_persistence.py
git commit -m "feat: add durable console event feed"
```

### Task 2: Add replay command REST routes and reconnectable SSE

**Files:**
- Modify: `src/industrial_reliability/api.py`
- Create: `tests/test_console_api.py`

**Interfaces:**
- Consumes: Phase 3 `ReplayCommandV1`, Kafka producer wrapper, `ConsoleEventBroker`, and Phase 5 replay/alert store methods.
- Produces: `POST /v1/replays`, `POST /v1/replays/{replay_session_id}/commands`, and `GET /v1/replays/{replay_session_id}/stream`; request models `StartReplayRequestV1(range_start, range_end, speed)` and `ReplayControlRequestV1(action)`; speed is exactly `1`, `100`, or `1000`.

- [ ] **Step 1: Write REST and SSE contract tests**

```python
def test_start_replay_publishes_versioned_command(client: TestClient, kafka: FakeProducer) -> None:
    response = client.post(
        "/v1/replays",
        json={
            "range_start": "2020-04-17T23:00:00",
            "range_end": "2020-04-18T02:00:00",
            "speed": 100,
        },
    )
    assert response.status_code == 202
    command = ReplayCommandV1.model_validate(kafka.messages[0].value)
    assert command.action == "START"
    assert command.speed == 100


def test_sse_reconnect_starts_with_snapshot_then_missed_event(client: TestClient) -> None:
    with client.stream(
        "GET",
        "/v1/replays/session-1/stream",
        headers={"Last-Event-ID": "status-1"},
    ) as response:
        events = take_sse_events(response.iter_lines(), count=2)
    assert [event.event for event in events] == ["snapshot", "score"]
    assert events[1].id == "decision-2"
```

- [ ] **Step 2: Run tests and observe missing command/SSE routes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_console_api.py -q`

Expected: FAIL with HTTP 404 for all three routes.

- [ ] **Step 3: Implement validated commands and stdlib SSE framing**

```python
class StartReplayRequestV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    range_start: datetime
    range_end: datetime
    speed: Literal[1, 100, 1000]

    @model_validator(mode="after")
    def bounded_range(self) -> Self:
        if self.range_start >= self.range_end:
            raise ValueError("range_start must precede range_end")
        return self


def encode_sse(event: str, data: Mapping[str, object], event_id: str | None = None) -> bytes:
    lines = ([f"id: {event_id}"] if event_id else []) + [f"event: {event}"]
    lines.append(f"data: {json.dumps(data, separators=(',', ':'), allow_nan=False)}")
    return ("\n".join(lines) + "\n\n").encode()
```

The SSE generator always emits a current durable snapshot first. If `Last-Event-ID` resolves to a persisted event, emit later durable events in sequence, then subscribe live. If it is unknown or points to non-durable telemetry, emit `resync_required` followed by the snapshot. Send a comment heartbeat every 15 wall-clock seconds; cancel the broker subscription when the client disconnects.

- [ ] **Step 4: Verify API validation, reconnect, and cancellation**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_console_api.py tests/test_alert_api.py tests/test_api.py -q`

Expected: PASS; invalid speed/range returns 422, unknown session returns 404, and the subscriber count returns to zero after disconnect.

- [ ] **Step 5: Commit the operator API surface**

```powershell
git add src/industrial_reliability/api.py tests/test_console_api.py
git commit -m "feat: add replay control and SSE APIs"
```

### Task 3: Scaffold the typed Vite console and API client

**Files:**
- Create: `apps/operator-console/package.json`
- Create: `apps/operator-console/package-lock.json`
- Create: `apps/operator-console/tsconfig.json`
- Create: `apps/operator-console/vite.config.ts`
- Create: `apps/operator-console/index.html`
- Create: `apps/operator-console/src/main.tsx`
- Create: `apps/operator-console/src/api.ts`
- Create: `apps/operator-console/src/api.test.ts`
- Create: `apps/operator-console/src/useReplayStream.ts`
- Create: `apps/operator-console/src/useReplayStream.test.tsx`

**Interfaces:**
- Consumes: the Phase 5 read routes and Task 2 replay/SSE routes under same-origin `/v1`.
- Produces: `startReplay`, `controlReplay`, `getReplay`, `listAlerts`, `getAlert`, and `useReplayStream(replaySessionId)`; immutable UI domain types `ReplaySnapshot`, `TelemetryPoint`, `ScorePoint`, `AlertSummary`, and `AlertDetail`.

- [ ] **Step 1: Create the package manifest and install exact locked dependencies**

Create scripts `dev`, `build`, `test`, `test:coverage`, and `e2e`. Then run:

```powershell
Set-Location apps/operator-console
npm install --save-exact react react-dom
npm install --save-dev --save-exact typescript vite @vitejs/plugin-react vitest jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom @playwright/test
```

Expected: `package-lock.json` records exact resolved versions; no chart, state-management, component, or SSE dependency is added.

- [ ] **Step 2: Write failing client and reconnect-hook tests**

```typescript
it("sends a bounded replay request", async () => {
  fetchMock.mockResolvedValue(ok({ replay_session_id: "session-1" }));
  await startReplay({ range_start: "2020-04-17T23:00:00", range_end: "2020-04-18T02:00:00", speed: 100 });
  expect(fetchMock).toHaveBeenCalledWith("/v1/replays", expect.objectContaining({ method: "POST" }));
});

it("replaces state from the reconnect snapshot", () => {
  const { result } = renderHook(() => useReplayStream("session-1"));
  emitSse("snapshot", snapshotFixture({ state: "PAUSED" }));
  expect(result.current.snapshot.state).toBe("PAUSED");
});
```

- [ ] **Step 3: Run tests and observe missing exports**

Run: `npm test -- --run`

Expected: FAIL because `api.ts` and `useReplayStream.ts` do not export the declared functions.

- [ ] **Step 4: Implement the minimal typed fetch/EventSource layer**

```typescript
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  const envelope: ApiEnvelope<T> = await response.json();
  if (!response.ok || !envelope.success || envelope.data === null) {
    throw new ApiClientError(envelope.error?.code ?? "HTTP_ERROR", envelope.error?.message ?? "Request failed");
  }
  return envelope.data;
}

function reduceStream(state: ReplayStreamState, event: ReplayEvent): ReplayStreamState {
  if (event.type === "snapshot") return { ...state, snapshot: event.data, connection: "open" };
  if (event.type === "telemetry") {
    return { ...state, telemetry: [...state.telemetry, event.data].slice(-600) };
  }
  if (event.type === "score") {
    return { ...state, scores: [...state.scores, event.data].slice(-600) };
  }
  return state;
}

export function useReplayStream(replaySessionId: string | null): ReplayStreamState {
  const [state, dispatch] = useReducer(reduceStream, INITIAL_STREAM_STATE);
  useEffect(() => {
    if (replaySessionId === null) return;
    const source = new EventSource(`/v1/replays/${replaySessionId}/stream`);
    const parse = <T,>(event: MessageEvent<string>): T => JSON.parse(event.data) as T;
    source.addEventListener("snapshot", event => dispatch({ type: "snapshot", data: parse(event) }));
    source.addEventListener("telemetry", event => dispatch({ type: "telemetry", data: parse(event) }));
    source.addEventListener("score", event => dispatch({ type: "score", data: parse(event) }));
    source.addEventListener("alert", async () => {
      dispatch({ type: "alerts", data: await listAlerts(replaySessionId) });
    });
    source.addEventListener("resync_required", async () => {
      const [snapshot, alerts] = await Promise.all([getReplay(replaySessionId), listAlerts(replaySessionId)]);
      dispatch({ type: "snapshot", data: { ...snapshot, alerts } });
    });
    source.onerror = () => dispatch({ type: "connection", data: "reconnecting" });
    return () => source.close();
  }, [replaySessionId]);
  return state;
}
```

Use a reducer with immutable updates. `snapshot` replaces durable state; telemetry and score append to bounded arrays; alert events trigger `listAlerts`; `resync_required` fetches replay and alerts. EventSource errors set `connection="reconnecting"` without discarding the durable snapshot.

- [ ] **Step 5: Verify the typed client and commit the scaffold**

Run: `npm test -- --run`

Run: `npm run build`

Expected: PASS; TypeScript and Vite builds exit 0.

```powershell
git add apps/operator-console/package.json apps/operator-console/package-lock.json apps/operator-console/tsconfig.json apps/operator-console/vite.config.ts apps/operator-console/index.html apps/operator-console/src/main.tsx apps/operator-console/src/api.ts apps/operator-console/src/api.test.ts apps/operator-console/src/useReplayStream.ts apps/operator-console/src/useReplayStream.test.tsx
git commit -m "feat: scaffold typed operator console"
```

### Task 4: Build replay controls and dependency health

**Files:**
- Create: `apps/operator-console/src/App.tsx`
- Create: `apps/operator-console/src/App.test.tsx`
- Create: `apps/operator-console/src/components/ReplayControls.tsx`
- Create: `apps/operator-console/src/components/HealthPanel.tsx`
- Create: `apps/operator-console/src/styles.css`

**Interfaces:**
- Consumes: Task 3 client/hook, `/readyz`, replay snapshot states `CREATED|RUNNING|PAUSED|STOPPED|COMPLETED|FAILED`.
- Produces: labeled range and speed controls, Start/Pause/Resume/Stop buttons with state-derived availability, dependency health list, source-time/session/error status.

- [ ] **Step 1: Write keyboard-level interaction tests**

```typescript
it("starts and pauses a replay through labeled controls", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.type(screen.getByLabelText("Range start"), "2020-04-17T23:00");
  await user.type(screen.getByLabelText("Range end"), "2020-04-18T02:00");
  await user.selectOptions(screen.getByLabelText("Replay speed"), "100");
  await user.click(screen.getByRole("button", { name: "Start replay" }));
  expect(startReplay).toHaveBeenCalledTimes(1);
  emitSse("snapshot", snapshotFixture({ state: "RUNNING" }));
  await user.click(screen.getByRole("button", { name: "Pause replay" }));
  expect(controlReplay).toHaveBeenCalledWith("session-1", "PAUSE");
});
```

- [ ] **Step 2: Run the component test before UI implementation**

Run: `npm test -- --run src/App.test.tsx`

Expected: FAIL because `App` and the controls are absent.

- [ ] **Step 3: Implement state-derived controls and accessible status**

```tsx
<form aria-label="Replay controls" onSubmit={onStart}>
  <label>Range start<input name="rangeStart" type="datetime-local" required /></label>
  <label>Range end<input name="rangeEnd" type="datetime-local" required /></label>
  <label>Replay speed<select name="speed" defaultValue="100">
    <option value="1">1×</option><option value="100">100×</option><option value="1000">1000×</option>
  </select></label>
  <button type="submit" disabled={isActive}>Start replay</button>
</form>
<p role="status" aria-live="polite">{statusText}</p>
```

Use visible focus styles, text plus icon/status labels, and native controls. A failed replay shows the stable `error_code` and a retry instruction; it never hides the previous durable evidence.

- [ ] **Step 4: Verify components and production build**

Run: `npm test -- --run src/App.test.tsx`

Run: `npm run build`

Expected: PASS with no React act warnings or TypeScript errors.

- [ ] **Step 5: Commit replay controls**

```powershell
git add apps/operator-console/src/App.tsx apps/operator-console/src/App.test.tsx apps/operator-console/src/components/ReplayControls.tsx apps/operator-console/src/components/HealthPanel.tsx apps/operator-console/src/styles.css
git commit -m "feat: add operator replay controls"
```

### Task 5: Add live charts and alert evidence detail

**Files:**
- Create: `apps/operator-console/src/components/LiveCharts.tsx`
- Create: `apps/operator-console/src/components/LiveCharts.test.tsx`
- Create: `apps/operator-console/src/components/AlertPanel.tsx`
- Create: `apps/operator-console/src/components/AlertPanel.test.tsx`
- Modify: `apps/operator-console/src/App.tsx`

**Interfaces:**
- Consumes: bounded telemetry/score arrays, alert list/detail APIs, `FeatureDeviationV1`, provenance hashes, and nullable RCA.
- Produces: native SVG telemetry/score plots, threshold line, anomaly markers, alert list/detail, evidence table, provenance block, and explicit `RCA unavailable` until Phase 9.

- [ ] **Step 1: Write rendering tests for evidence and non-color alert state**

```typescript
it("shows score threshold and persisted evidence", async () => {
  render(<AlertPanel alerts={[alertFixture()]} loadAlert={loadAlertFixture} />);
  await userEvent.click(screen.getByRole("button", { name: /open alert alert-1/i }));
  expect(await screen.findByRole("heading", { name: "Alert alert-1" })).toBeVisible();
  expect(screen.getByText("Contract SHA-256")).toBeVisible();
  expect(screen.getByText("RCA unavailable")).toBeVisible();
});


it("renders an accessible chart summary", () => {
  render(<LiveCharts telemetry={telemetryFixture()} scores={scoreFixture()} />);
  expect(screen.getByRole("img", { name: /score 0.91 threshold 0.75 anomaly/i })).toBeVisible();
});
```

- [ ] **Step 2: Run tests and observe missing components**

Run: `npm test -- --run src/components/LiveCharts.test.tsx src/components/AlertPanel.test.tsx`

Expected: FAIL because the chart and alert components do not exist.

- [ ] **Step 3: Implement native SVG and evidence panels**

```tsx
<svg role="img" aria-label={scoreSummary} viewBox="0 0 800 220">
  <polyline points={scorePoints} className="score-line" />
  <line x1="0" x2="800" y1={thresholdY} y2={thresholdY} className="threshold-line" />
  {anomalies.map(point => <circle key={point.decision_id} cx={point.x} cy={point.y} r="4" />)}
</svg>
```

Keep the latest 600 points already bounded by the hook. Show source time on the axis and label replay speed separately. The alert detail renders only allowlisted evidence/provenance fields and treats every identifier as text; do not use `dangerouslySetInnerHTML`.

- [ ] **Step 4: Run component coverage and build**

Run: `npm run test:coverage -- --run`

Run: `npm run build`

Expected: PASS with at least 80% branch coverage for `src/api.ts`, `src/useReplayStream.ts`, and component state logic.

- [ ] **Step 5: Commit visualization and evidence UI**

```powershell
git add apps/operator-console/src/App.tsx apps/operator-console/src/components/LiveCharts.tsx apps/operator-console/src/components/LiveCharts.test.tsx apps/operator-console/src/components/AlertPanel.tsx apps/operator-console/src/components/AlertPanel.test.tsx
git commit -m "feat: show live scores and alert evidence"
```

### Task 6: Containerize the console on localhost

**Files:**
- Create: `apps/operator-console/Dockerfile`
- Create: `apps/operator-console/nginx.conf`
- Modify: `apps/operator-console/vite.config.ts`
- Modify: `compose.yaml`
- Modify: `.env.example`
- Create: `tests/integration/test_console_local_binding.py`

**Interfaces:**
- Consumes: root Compose network, API service name `scoring-api:8000`, committed npm lockfile.
- Produces: Compose service `operator-console`, host URL `http://127.0.0.1:5173`, multi-stage static build, and nginx proxy for `/v1` including unbuffered SSE. Vite's dev proxy remains available only for local frontend development outside Compose.

- [ ] **Step 1: Write the host-binding test**

```python
def test_operator_console_binds_only_loopback() -> None:
    config = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    service = json.loads(config.stdout)["services"]["operator-console"]
    assert service["ports"][0]["host_ip"] == "127.0.0.1"
```

- [ ] **Step 2: Run the test before adding the service**

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_console_local_binding.py -q`

Expected: FAIL because `operator-console` is absent from Compose.

- [ ] **Step 3: Add the locked npm container and localhost mapping**

```dockerfile
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
```

```nginx
server {
  listen 8080;
  root /usr/share/nginx/html;
  location / { try_files $uri /index.html; }
  location /v1/ {
    proxy_pass http://scoring-api:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 1h;
  }
}
```

```yaml
operator-console:
  build: ./apps/operator-console
  ports:
    - "127.0.0.1:5173:8080"
  depends_on:
    scoring-api:
      condition: service_healthy
```

- [ ] **Step 4: Verify binding, container build, and readiness**

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_console_local_binding.py -q`

Run: `docker compose build operator-console`

Run: `docker compose up -d operator-console`

Run: `Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173 | Select-Object -ExpandProperty StatusCode`

Expected: tests/build succeed and the request prints `200`; no `0.0.0.0:<host-port>` mapping appears in `docker compose ps`.

- [ ] **Step 5: Commit local console packaging**

```powershell
git add apps/operator-console/Dockerfile apps/operator-console/nginx.conf apps/operator-console/vite.config.ts compose.yaml .env.example tests/integration/test_console_local_binding.py
git commit -m "build: run operator console on localhost"
```

### Task 7: Certify the real-click replay-to-evidence path

**Files:**
- Create: `apps/operator-console/playwright.config.ts`
- Create: `apps/operator-console/e2e/operator-console.spec.ts`
- Create: `scripts/write_phase6_gate.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: real Compose stack, a configured bounded private Phase 1B replay range known to produce an alert under the locked policy, Playwright browser clicks, REST/SSE results.
- Produces: Playwright trace/screenshot/video under `artifacts/phase6/<git-sha>/playwright/` and self-hashed `artifacts/phase6/<git-sha>/phase6-gate.json` with exact SHA, replay session, alert, decision, evidence, model, contract, dataset, and policy identities.

- [ ] **Step 1: Write the real-click scenario with an interception guard**

```typescript
test("operator runs replay and opens persisted evidence", async ({ page }) => {
  const intercepted: string[] = [];
  page.on("request", request => {
    if (request.url().startsWith("data:") || request.url().startsWith("blob:")) intercepted.push(request.url());
  });
  await page.goto("/");
  await page.getByLabel("Range start").fill(process.env.PHASE6_RANGE_START!);
  await page.getByLabel("Range end").fill(process.env.PHASE6_RANGE_END!);
  await page.getByLabel("Replay speed").selectOption("1000");
  await page.getByRole("button", { name: "Start replay" }).click();
  await expect(page.getByRole("status")).toContainText("Running");
  await page.getByRole("button", { name: "Pause replay" }).click();
  await expect(page.getByRole("status")).toContainText("Paused");
  await page.getByRole("button", { name: "Resume replay" }).click();
  await expect(page.getByRole("button", { name: /open alert/i }).first()).toBeVisible();
  await page.getByRole("button", { name: /open alert/i }).first().click();
  await expect(page.getByText("Contract SHA-256")).toBeVisible();
  await expect(page.getByText("Evidence ID")).toBeVisible();
  expect(intercepted).toEqual([]);
});
```

The test file must contain no `page.route`, `route.fulfill`, `setContent`, or database insert. A source scan in the gate script fails if any appears.

- [ ] **Step 2: Run the scenario before gate wiring**

Run: `Set-Location apps/operator-console; npx playwright test e2e/operator-console.spec.ts`

Expected: FAIL until the environment range and full stack are configured; no fixture or mocked pass is accepted.

- [ ] **Step 3: Add Playwright retention and the gate writer**

Configure one Chromium worker, `trace: "retain-on-failure"`, `screenshot: "only-on-failure"`, and `video: "retain-on-failure"`. `write_phase6_gate.py` reads the successful Playwright JSON report and API-fetched durable identities; it refuses missing hashes or a replay without at least one persisted alert/evidence snapshot.

- [ ] **Step 4: Run the complete Phase 6 checks**

Run: `.\.venv\Scripts\python.exe -m ruff check .`

Run: `.\.venv\Scripts\python.exe -m ruff format --check .`

Run: `.\.venv\Scripts\python.exe -m mypy src`

Run: `.\.venv\Scripts\python.exe -m pytest -q --cov-branch --cov-fail-under=80`

Run: `.\.venv\Scripts\python.exe -m pip check`

Run: `.\.venv\Scripts\python.exe -m build`

Run: `Set-Location apps/operator-console; npm run test:coverage -- --run; npm run build; npx playwright test e2e/operator-console.spec.ts --reporter=json`

Run from the repository root: `.\.venv\Scripts\python.exe scripts/write_phase6_gate.py --playwright-report apps/operator-console/playwright-report.json --output artifacts/phase6/$(git rev-parse HEAD)/phase6-gate.json`

Expected: every command exits 0 and the gate names the same replay/decision/alert/evidence chain visible in the captured browser run.

- [ ] **Step 5: Commit Phase 6 certification**

```powershell
git add apps/operator-console/playwright.config.ts apps/operator-console/e2e/operator-console.spec.ts scripts/write_phase6_gate.py README.md
git commit -m "test: certify real-click operator console"
```

## Phase 6 Exit Gate

Move Phase 7 to `Ready` only when a real browser click starts, pauses, resumes, and observes a real replay; live score/telemetry arrives by SSE; a persisted alert opens to evidence/provenance; reconnect restores the durable snapshot; localhost binding and accessibility checks pass; and `phase6-gate.json` ties the UI evidence to exact runtime hashes. A mocked UI pass, synthetic-only run, or screenshot without durable identifiers does not pass.
