# System Architecture & Component Diagrams

```mermaid
graph TD
    subgraph Data & Ingestion Layer
        A[Raw Parquet Telemetry] -->|Ordered Replay| B[Replay Service / Producer]
        B -->|irp.telemetry.v1| C[Kafka Message Broker]
    end

    subgraph Streaming & Scoring Layer
        C -->|irp.telemetry.v1| D[Streaming Worker]
        D -->|irp.features.v1| C
        D -->|POST /v1/score| E[FastAPI Scoring Service]
        E -->|Stateless Detector| E
        E -->|Score Decision| D
        D -->|irp.scores.v1| C
        D -->|irp.quarantine.v1| C
    end

    subgraph Alert Lifecycle & Outbox Layer
        C -->|irp.scores.v1| F[Alert Service Daemon]
        F -->|State Machine Transition| G[(PostgreSQL Database)]
        F -->|Transactional Outbox| C
        C -->|irp.alerts.v1| C
    end

    subgraph Operator Console & RCA
        H[React Operator Console] -->|POST /v1/replays| E
        E -->|irp.replay.commands.v1| C
        C -->|Replay Control| B
        H -->|SSE Stream /v1/replays/events| E
        H -->|POST /v1/alerts/id/rca| E
        E -->|4-Tool Evidence Bundle| I[Grounded RCA Generator]
        I -->|Structured Output| J[OpenAI Provider / Local Fallback]
        J -->|Validated Citations| G
    end

    subgraph Observability
        E -->|:8000/metrics| K[Prometheus Scraper]
        B -->|:9101/metrics| K
        D -->|:9102/metrics| K
        F -->|:9103/metrics| K
        K -->|Scrape Metrics| L[Grafana Operator Dashboards]
    end
```

---

## Data Flow Sequences

1. **Replay Ingestion & Control:** API emits control commands to `irp.replay.commands.v1`. Replay Service reads source Parquet and emits timestamp-ordered `TelemetryEventV1` messages to `irp.telemetry.v1`.
2. **Online Feature Computation:** Streaming worker consumes raw telemetry, constructs rolling causal windows, catches segment breaks, and routes malformed records to `irp.quarantine.v1`.
3. **Stateless Anomaly Scoring:** Streaming worker sends `FeatureVectorV1` to FastAPI `/v1/score`, which evaluates the candidate model and returns `ScoreDecisionV1` published to `irp.scores.v1`.
4. **Alert State Machine & Outbox:** Dedicated `AlertService` consumes score decisions, evaluates locked alert persistence/cooldown policies, transitions alert state records in PostgreSQL, and dispatches outbox alert events to `irp.alerts.v1`.
5. **Grounded RCA Generation:** On operator request, the platform projects a deterministic 4-tool evidence bundle, validates closed-world citations via OpenAI structured outputs (or graceful local fallback under outage), and writes an immutable report to PostgreSQL.
