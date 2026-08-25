# System Architecture & Component Diagrams

```mermaid
graph TD
    subgraph Data Layer
        A[Raw Parquet Telemetry] -->|Ordered Replay| B[Kafka Replay Producer]
    end

    subgraph Messaging & Streaming
        B -->|telemetry.events| C[Kafka Broker]
        C -->|Raw Stream| D[Python Streaming Worker]
        D -->|Feature Aggregation| D
        D -->|features.events| C
    end

    subgraph Scoring & Decision Layer
        D -->|POST /v1/score| E[FastAPI Scoring Service]
        E -->|Detector Model| E
        E -->|Score & Decision| D
        D -->|score.decisions| C
    end

    subgraph State & Persistence
        D -->|Alert State Machine| F[(PostgreSQL Database)]
        F -->|Alerts & Events| F
        F -->|rca_reports| F
    end

    subgraph Operator Surface
        G[React Operator Console] -->|Control APIs /v1/replays| E
        G -->|SSE Stream /v1/replays/events| E
        G -->|Generate RCA /v1/alerts/id/rca| E
        E -->|Evidence Projection| H[OpenAI Structured RCA]
    end

    subgraph Observability
        E -->|/metrics| I[Prometheus Scraper]
        B -->|:9101/metrics| I
        D -->|:9102/metrics| I
        I -->|Scrape Targets| J[Grafana Operator Dashboards]
    end
```

---

## Data Flow Sequences

1. **Replay Ingestion:** Replay Producer reads source Parquet files and emits timestamp-ordered `TelemetryEventV1` messages to Kafka topic `irp.telemetry.events`.
2. **Online Feature Computation:** Streaming worker consumes raw telemetry, builds 5-minute bins and 30-minute rolling causal windows, and detects sequence breaks.
3. **Stateless Anomaly Scoring:** Streaming worker sends `FeatureVectorV1` to FastAPI `/v1/score`, which evaluates the champion model and returns a `ScoreDecisionV1`.
4. **Alert State Machine & Persistence:** Streaming worker transitions alert states (`OPEN`, `ACKNOWLEDGED`, `RESOLVED`) based on locked policy, storing decisions and alerts in PostgreSQL.
5. **Grounded RCA Generation:** When requested via the console or API, the platform gathers a deterministic 4-tool evidence bundle, invokes OpenAI `responses.parse`, validates citations, and persists immutable `COMPLETE` reports.
