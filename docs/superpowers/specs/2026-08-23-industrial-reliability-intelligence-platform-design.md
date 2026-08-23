# Industrial Reliability Intelligence Platform
## Architectural Design Specification

**Status:** Draft for user review  
**Date:** 2026-08-23  
**Purpose:** Consolidate all major decisions and reasoning from the brainstorming discussion into one source-of-truth document before implementation planning.

---

# 1. Executive Summary

This project is a **production-oriented AI/ML system for industrial reliability**.

The core story is simple:

> A machine is running and continuously produces digital sensor readings such as pressure, temperature, electrical current, and on/off states. The system receives those readings, learns what normal machine behavior looks like, detects abnormal behavior before or around real failure events, raises alerts, and provides an evidence-grounded explanation of why an alert was raised.

The system intentionally begins **after physical sensor acquisition**.

The project does **not** require designing sensors, electronics, PLC wiring, SCADA hardware, or signal-conditioning circuits. It assumes the industrial control layer has already converted physical measurements into timestamped digital telemetry.

The portfolio/recruiting value comes from building the software and ML system around that data:

1. ingesting and validating large real telemetry data,
2. feature engineering over time-series signals,
3. training and evaluating anomaly-detection models without leakage,
4. creating a realistic online replay/streaming path,
5. serving models behind an API,
6. generating operational alerts,
7. tracking experiments and model versions,
8. monitoring model/data/system health,
9. adding an LLM-powered RCA assistant that explains alerts using tools and structured evidence,
10. optionally optimizing PyTorch inference with Intel OpenVINO.

This is **not** intended to be another RAG/chatbot project and **not** a notebook-only ML exercise.

---

# 2. Recommended Project Name

Primary working name:

**Industrial Reliability Intelligence Platform — Real-time Anomaly Detection, Early Failure Warning & Evidence-Grounded RCA**

Alternative shorter name for GitHub/CV:

**Industrial Reliability Intelligence Platform**

Possible GitHub repository slug:

`industrial-reliability-platform`

The title is intentionally broader than “semiconductor predictive maintenance” because the primary dataset is industrial telemetry but not specifically semiconductor-fab equipment.

---

# 3. Why This Project

The project was selected because it creates evidence in areas that are complementary to an existing strong software/backend profile:

- production ML lifecycle,
- time-series ML,
- anomaly detection,
- PyTorch,
- model experimentation,
- data engineering,
- streaming systems,
- model serving,
- data quality,
- observability,
- agent/tool calling over operational evidence,
- inference optimization.

The intended narrative is:

> Software Engineer with strong backend/reliability foundations → distributed/data systems → production AI/ML system → Applied AI / AI Engineer.

The goal is **not** to compete with pure ML researchers on novel architectures.

The competitive advantage is engineering depth:

> real industrial telemetry + leakage-safe ML evaluation + streaming replay + model lifecycle + backend APIs + observability + evidence-grounded AI explanation + measured inference optimization.

---

# 4. Problem Statement

## 4.1 Real-world problem

Industrial equipment contains sensors that measure machine behavior.

Examples:

- pressure,
- temperature,
- electrical current,
- vibration,
- flow,
- valve state,
- compressor state,
- motor state.

A healthy machine normally produces recurring patterns.

Example:

```text
Normal behavior

Temperature: 60 → 61 → 60 → 62
Pressure:     8.0 → 8.1 → 8.0 → 8.1
```

Before or during an abnormal condition, behavior may change:

```text
Potential abnormal behavior

Temperature: 61 → 64 → 68 → 73
Pressure:     8.0 → 7.7 → 7.2 → 6.8
```

The desired software behavior is:

```text
Normal machine operation
        ↓
small deviations
        ↓
sustained abnormal pattern
        ↓
AI/ML anomaly score rises
        ↓
alert generated
        ↓
operator receives evidence-based explanation
```

---

# 5. Domain Boundary

## 5.1 What happens before this project

A real industrial stack may look roughly like:

```text
Physical machine
      ↓
Physical sensor
      ↓
Signal acquisition device / PLC
      ↓
SCADA / IoT gateway / industrial controller
      ↓
Timestamped digital data
```

The project does **not** implement these hardware/control layers.

## 5.2 Where this project begins

The software boundary is:

```text
Timestamped digital telemetry
          ↓
==============================
        PROJECT START
==============================
          ↓
ingestion
          ↓
validation
          ↓
storage
          ↓
feature engineering
          ↓
ML inference
          ↓
alerting
          ↓
monitoring
          ↓
RCA explanation
```

A precise interview statement is:

> “I assume telemetry acquisition is handled by the industrial control layer. My system starts at the software ingestion boundary, where timestamped sensor readings become available.”

---

# 6. Domain Glossary for a Beginner

## 6.1 Core terms

### Sensor
A physical device that measures something.

Examples:

- thermometer → temperature,
- pressure sensor → pressure,
- current sensor → electrical current.

### Telemetry
Measurements automatically sent from a machine/system to software.

Example:

```json
{
  "timestamp": "2026-08-23T14:32:01",
  "machine_id": "APU-01",
  "pressure": 8.2,
  "temperature": 64.1
}
```

### Time series
Data ordered over time.

Example:

```text
14:00 → temperature 61
14:01 → temperature 62
14:02 → temperature 64
...
```

The order matters.

### Normal behavior
Patterns commonly observed while equipment is functioning normally.

### Anomaly
An observation or sequence that differs significantly from learned normal behavior.

Important:

> anomaly ≠ confirmed failure.

Something can be unusual without being a real mechanical failure.

### Failure
A real equipment malfunction or breakdown event.

### Anomaly detection
The ML/statistical task of identifying behavior that appears unusual.

### Predictive maintenance
Using machine data to detect degradation or predict maintenance needs before serious failure.

### Alert
An operational notification that a suspicious condition has persisted strongly enough to deserve attention.

### Root cause
The actual underlying cause of a failure.

### RCA — Root Cause Analysis
The investigation process used to understand why an incident occurred.

In this project the LLM component provides **RCA assistance / anomaly explanation**, not guaranteed mechanical root-cause proof.

### RUL — Remaining Useful Life
A different problem:

> “How long can this machine continue operating before failure?”

RUL is not the flagship problem selected for the first version.

---

# 7. Problem Variants Considered

Three possible project directions were discussed.

## Option A — Detect abnormal machine behavior

Question:

> “Is this machine starting to behave abnormally?”

Flow:

```text
sensor data
    ↓
anomaly detection
    ↓
alert
    ↓
explanation
```

**Selected direction.**

Why:

- works with limited failure events,
- fits real telemetry,
- allows meaningful temporal evaluation,
- supports online/streaming system design,
- enables operational alerting,
- provides a natural use case for an evidence-grounded agent.

## Option B — Product/process quality classification

Question:

> “Will this manufactured item pass or fail?”

Example datasets:

- SECOM,
- Bosch Production Line Performance.

Useful for manufacturing classification but less natural for continuous streaming/RCA.

## Option C — Remaining Useful Life

Question:

> “How many hours/cycles remain before failure?”

Typical dataset:

- NASA C-MAPSS.

Good ML task, but not the selected flagship because the system story becomes more focused on regression/RUL rather than anomaly detection and operational alerting.

---

# 8. Dataset Strategy

## 8.1 Primary dataset: MetroPT 2022

The primary dataset should be a large, real industrial telemetry dataset rather than synthetic data generated by the project.

The current recommended primary source is **MetroPT 2022**.

Characteristics discussed:

- approximately 10.98 million telemetry records,
- real industrial equipment data,
- approximately 1 Hz sampling,
- multiple analog and digital signals,
- large enough to justify real data-engineering work,
- contains known maintenance/failure events,
- suitable for replaying historical data as a simulated live stream.

Primary reason for choosing it:

> It provides enough scale and temporal structure to justify time-series ML, stream processing, data quality, event-time handling, and realistic alert evaluation.

Official references previously discussed:

- MetroPT paper / Scientific Data:
  https://www.nature.com/articles/s41597-022-01877-3
- Zenodo dataset:
  https://zenodo.org/records/6854240

## 8.2 Why synthetic telemetry should not be the main dataset

A weak portfolio implementation would generate values such as:

```python
temperature = random.normal(...)
pressure = random.normal(...)
```

then manually inject 5% anomalies.

Problems:

- anomalies are artificial,
- ML results are easy to manufacture,
- little domain realism,
- limited credibility in interviews,
- data engineering becomes performative.

Synthetic data remains useful only for:

- unit tests,
- CI fixtures,
- integration testing,
- edge-case generation.

It should not be the source of headline ML results.

---

# 9. Secondary Datasets Considered

## 9.1 MetroPT-3

Smaller related Metro dataset.

A high-quality reference implementation found during GitHub research uses approximately 1.5M real sensor records.

Useful for:

- methodological reference,
- leakage-safe temporal splitting,
- event-level evaluation,
- anomaly-model comparison.

Not necessarily required as a separate project dataset if MetroPT 2022 is used.

## 9.2 SECOM

Real semiconductor manufacturing/process-control dataset.

Strength:

- semiconductor relevance.

Weakness:

- only roughly 1.5K samples,
- hundreds of process features,
- too small to justify Kafka/Spark as the primary data workload.

Recommended use:

> optional secondary domain-specific benchmark, not primary streaming data.

Official source:

https://archive.ics.uci.edu/dataset/179/secom

## 9.3 Bosch Production Line Performance

Strength:

- more than one million product records,
- highly relevant manufacturing framing,
- complex feature space.

Weakness:

- anonymized feature semantics,
- difficult to provide physically meaningful RCA,
- well-known competition with many existing solutions,
- not naturally continuous telemetry.

Useful as an alternative manufacturing classification benchmark.

## 9.4 Backblaze Drive Stats

Strength:

- very large real-world reliability dataset,
- longitudinal hardware-health telemetry,
- years of public data.

Weakness:

- daily rather than high-frequency telemetry,
- harder schema/model-family management,
- less direct industrial-equipment framing.

Excellent alternative if a larger reliability project is desired later.

## 9.5 NASA C-MAPSS

Strength:

- common predictive-maintenance benchmark,
- useful for Remaining Useful Life,
- easy to experiment with,
- many public PyTorch/LSTM examples.

Weakness:

- simulated,
- saturated portfolio topic,
- not needed for the main anomaly-detection MVP.

Could be added later as an RUL benchmark, but currently considered YAGNI.

---

# 10. Core Product Scenario

The final demo should tell a coherent story.

## Step 1 — Historical telemetry is replayed

The dataset contains readings such as:

```text
10:00:01 temp=61 pressure=8.1 ...
10:00:02 temp=61 pressure=8.0 ...
10:00:03 temp=62 pressure=8.1 ...
```

A replay service publishes these records in timestamp order.

The replay can be accelerated.

Example:

```text
REPLAY_SPEED=1x
REPLAY_SPEED=100x
REPLAY_SPEED=1000x
```

The data remains historical real telemetry; only playback speed changes.

## Step 2 — Streaming software receives records

Conceptually:

```text
historical file
    ↓
replay producer
    ↓
message stream
    ↓
stream processor
```

## Step 3 — Raw sensor data becomes features

Instead of asking the model to treat each second independently, raw observations are summarized into temporal windows.

Example 1-minute feature window:

```text
~60 raw samples
      ↓
one feature vector
```

Possible analog-sensor features:

- mean,
- min,
- max,
- standard deviation,
- last value,
- slope/trend,
- delta from previous window.

Possible digital-signal features:

- active ratio,
- number of state transitions,
- last state,
- time since transition.

## Step 4 — ML generates anomaly score

Example:

```text
anomaly_score = 0.89
threshold     = 0.74
```

## Step 5 — Alert policy decides whether to alert

A single noisy prediction should not immediately page an operator.

Example persistence rule:

```text
last 4 anomaly decisions

TRUE
TRUE
FALSE
TRUE

3 of 4 abnormal
→ raise alert
```

Possible alert controls:

- persistence requirement,
- cooldown,
- alert merging,
- severity thresholds.

## Step 6 — RCA assistant explains the alert

The LLM does not decide whether the machine is abnormal.

It receives an already-created alert and investigates structured evidence.

---

# 11. Machine Learning Strategy

The ML component is local Python ML code trained on the telemetry dataset.

It is **not** an LLM API.

Recommended stack:

```text
Python
NumPy
Pandas / Polars as needed
scikit-learn
PyTorch
MLflow
```

---

# 12. ML Model Ladder

Models should be introduced from simple to complex.

The deep model is not automatically assumed to be best.

## 12.1 Model A — Statistical baseline

Example:

- Robust Z-score,
- median-based thresholds,
- simple signal deviations.

Purpose:

- establish a minimum benchmark,
- prove complex ML adds measurable value,
- provide an interpretable fallback.

Concept:

```text
normal oil temperature ≈ known range

observed value far outside baseline
→ suspicious
```

## 12.2 Model B — Isolation Forest

Implementation:

`scikit-learn`

Purpose:

- learn which multivariate feature combinations are unusual,
- does not require many labeled failures,
- strong classical anomaly-detection baseline.

Concept:

```text
normal observations cluster in common regions
unusual combinations are easier to isolate
→ anomaly score
```

Possible inputs:

```text
temperature statistics
pressure statistics
current statistics
digital-state behavior
window trends
```

## 12.3 Model C — PyTorch Autoencoder / Temporal Autoencoder

Preferred deep-learning candidate.

Concept:

The model learns to reconstruct normal behavior.

Normal input:

```text
actual     ≈ reconstructed
error      = low
```

Abnormal input:

```text
actual     ≠ reconstructed
error      = high
```

Reconstruction error becomes an anomaly signal.

Advantages:

- works naturally with mostly-normal data,
- produces per-signal reconstruction error,
- useful evidence for explaining why an alert occurred,
- gives genuine PyTorch experience.

Potential later temporal architecture:

- TCN Autoencoder,
- sequence Autoencoder.

The first deep implementation should remain as simple as possible while supporting the use case.

---

# 13. Why Supervised Failure Classification Is Not the Primary Model

A tempting implementation is:

```text
telemetry
   ↓
XGBoost
   ↓
FAIL / NORMAL
```

This can be dangerous when only a few real failure events exist.

A single multi-hour event can create thousands of neighboring positive rows.

Random row splitting could cause:

```text
14:30 → train
14:31 → test
```

The model then sees nearly identical portions of the same event in both train and test.

This is **data leakage**.

Result:

- impressive-looking accuracy,
- weak real generalization,
- poor interview defensibility.

Therefore the selected framing is:

> learn normal behavior and detect abnormal temporal behavior.

Supervised classifiers such as XGBoost can later be added as comparison models only when event structure and temporal splitting are handled correctly.

---

# 14. Data Leakage

## Definition

Data leakage occurs when training accidentally includes information that would not have been available at the time of prediction.

For time-series data, random row train/test split is often unsafe.

## Required rule

Splits must follow time.

Conceptual structure:

```text
PAST                                               FUTURE

TRAIN NORMAL
|------------------|

CALIBRATION
                   |-------|

HOLDOUT / TEST
                           |----------------------|
```

## Train split

Used to:

- fit scalers,
- learn baselines,
- train Isolation Forest,
- train Autoencoder.

## Calibration split

Used to:

- choose anomaly threshold,
- configure alert policy,
- avoid tuning on the final test period.

## Holdout/test split

Used only after preprocessing/model/threshold decisions are locked.

---

# 15. Evaluation Philosophy

The primary success metric should **not** simply be classification accuracy.

A useful operational anomaly detector needs to answer questions such as:

- Did it detect known failure episodes?
- How early?
- How often did it generate false alarms?
- How much of the time was the machine continuously “in alert”?
- Does a more complex model provide enough improvement to justify its cost?

Recommended metrics:

## Event recall

Example:

```text
3 known failure events
model warned before 2
→ event recall = 2/3
```

Prefer reporting absolute event counts when event count is small.

## Lead time

How long before the known event did the system produce a valid warning?

Example:

```text
failure time = 20:00
first valid warning = 17:20
lead time = 2h40m
```

## False alarms per day

How many unrelated alert episodes occur during normal periods?

## PR-AUC

Useful for imbalanced anomaly/failure windows.

## Time in alert

Percentage of operation during which the system remains in alert state.

This helps prevent a meaningless detector that is almost always warning.

---

# 16. Alert Policy

Model score and operational alert are different concepts.

Bad implementation:

```python
if score > threshold:
    alert()
```

Better:

```text
anomaly model
    ↓
score
    ↓
threshold
    ↓
persistence policy
    ↓
cooldown / merge
    ↓
operational alert
```

Possible first policy:

- rolling last 4 predictions,
- alert when 3/4 exceed threshold,
- merge nearby alerts,
- cooldown after an alert.

Exact values must be measured/calibrated rather than claimed in advance.

---

# 17. Data Architecture

Suggested logical data stages:

```text
RAW
 ↓
BRONZE
 ↓
SILVER
 ↓
GOLD / FEATURES
```

## Raw

Original downloaded dataset.

Never silently modify.

## Bronze

Parsed representation preserving source semantics.

## Silver

Cleaned and typed data:

- normalized timestamps,
- schema checks,
- sorted time,
- duplicate handling,
- sampling-gap analysis.

## Gold

ML-ready windows/features.

Potential storage:

- Parquet for analytical/training data,
- TimescaleDB/PostgreSQL for queryable online/replay data.

---

# 18. Data Quality

The system should explicitly detect data problems.

Examples:

- invalid timestamp,
- duplicate timestamp,
- missing sensor,
- impossible value,
- unexpected schema,
- excessive sampling gap,
- malformed record,
- unknown sensor field.

Data quality is part of the product, not only preprocessing.

The project should distinguish:

```text
machine anomaly
```

from:

```text
bad/incomplete telemetry
```

These are not the same problem.

---

# 19. Streaming Layer

## 19.1 Why streaming exists

Streaming is not included just to list Kafka on a CV.

The use case is:

> replay historical telemetry through the same type of online path that a real industrial telemetry system could use.

## 19.2 Replay Producer

Responsibility:

- read historical records in chronological order,
- emit records as events,
- support configurable playback speed,
- preserve source timestamps,
- provide deterministic replay.

## 19.3 Kafka

Suggested role:

```text
sensor.raw
```

Possible later topics:

```text
sensor.features
sensor.alerts
sensor.dlq
```

Kafka provides:

- buffering,
- decoupling,
- replayable event flow,
- multiple independent consumers.

## 19.4 Spark Structured Streaming

Suggested responsibility:

- parse Kafka records,
- enforce schema,
- operate on event time,
- aggregate time windows,
- build streaming features,
- write to storage/model path.

Important concept:

### Event time
The original time when the reading was recorded.

### Processing time
When the software processes it.

Historical replay may happen at 1000x speed, so these two times differ.

---

# 20. Online Inference API

A FastAPI service should expose the selected model.

Possible endpoint:

```text
POST /v1/score
```

Example request concept:

```json
{
  "asset_id": "APU-01",
  "timestamp": "...",
  "features": {
    "...": "..."
  }
}
```

Example response:

```json
{
  "model_version": "ae-1.3",
  "anomaly_score": 0.87,
  "threshold": 0.74,
  "is_anomaly": true,
  "top_signals": [
    "oil_temperature",
    "tp3_pressure",
    "motor_current"
  ]
}
```

Other possible endpoints:

```text
GET /health
GET /models/current
GET /alerts/{alert_id}
GET /assets/{asset_id}/history
```

The API must expose model/version provenance so an alert can be traced back to the exact model that produced it.

---

# 21. Offline ML Lifecycle

Kafka/Spark and Airflow have different jobs.

## Online/replay path

```text
telemetry
  ↓
Kafka
  ↓
stream processing
  ↓
inference
  ↓
alert
```

## Offline/training path

```text
stored historical data
    ↓
Airflow
    ↓
validation
    ↓
feature generation
    ↓
training
    ↓
evaluation
    ↓
model registration
```

---

# 22. Airflow

Airflow should orchestrate reproducible ML/data workflows.

Possible DAG:

```text
validate_data
      ↓
build_training_features
      ↓
train_baseline
      ↓
train_isolation_forest
      ↓
train_autoencoder
      ↓
evaluate_models
      ↓
register_candidate
```

Airflow is not necessary in Phase 1.

The ML methodology must work first.

---

# 23. MLflow

MLflow is used for experiment/model tracking.

Store:

- model type,
- hyperparameters,
- training dataset/version,
- feature version,
- evaluation metrics,
- model artifacts,
- model version,
- plots.

Example conceptual experiment:

```text
model = IsolationForest
n_estimators = ...
feature_version = v3
event_recall = ...
false_alarms_day = ...
lead_time = ...
```

Another:

```text
model = TCN Autoencoder
window_size = ...
latent_dimension = ...
learning_rate = ...
event_recall = ...
false_alarms_day = ...
```

The project should make model selection evidence-based.

---

# 24. Monitoring

Monitoring should distinguish three categories.

## 24.1 System monitoring

Examples:

- API latency,
- request rate,
- error rate,
- Kafka consumer lag,
- service CPU/RAM,
- service availability.

Tools:

- Prometheus,
- Grafana.

## 24.2 Data monitoring

Examples:

- missing sensors,
- schema violations,
- value distributions,
- sampling gaps,
- drift.

Possible tool:

- Evidently.

## 24.3 Model monitoring

Examples:

- anomaly-score distribution,
- alert rate,
- input drift,
- prediction changes,
- model version currently serving.

---

# 25. Data Drift

Concept:

The model may have learned from one operating regime.

Example training distribution:

```text
oil temperature mean ≈ 65
```

Later production/replay distribution:

```text
oil temperature mean ≈ 71
```

This does not necessarily mean failure.

Operating conditions may have changed.

Drift monitoring should compare:

```text
reference data
      VS
recent data
```

The system should distinguish:

- true machine anomaly,
- systematic data distribution shift,
- broken input data.

---

# 26. LLM / Agent Scope

The project does **not** require an LLM to perform anomaly detection.

Core system:

```text
telemetry
    ↓
statistical / ML model
    ↓
anomaly score
    ↓
alert
```

works without any external LLM API.

The LLM is an optional downstream explanation/investigation layer.

---

# 27. LLM Provider Strategy

## Initial recommendation

Use an external provider API only after the core ML/alert flow is working.

Examples:

- OpenAI,
- Gemini,
- Anthropic.

Configuration concept:

```text
LLM_API_KEY=...
```

## Later alternative

Support a local LLM using:

- Ollama,
- small Llama/Qwen/Phi-family model,
- optionally Intel/OpenVINO optimization.

## Long-term abstraction

Application code can define one provider interface:

```text
LLM provider
   ├── cloud API
   └── local runtime
```

But multi-provider support is not required for MVP.

---

# 28. RCA Assistant

The assistant should **not** be a generic chatbot.

It should investigate a specific alert through deterministic tools.

Possible tools:

```text
get_alert(alert_id)
get_sensor_window(asset_id, start, end)
get_anomaly_scores(...)
get_signal_contributions(...)
get_state_transitions(...)
get_nearby_known_events(...)
get_model_card(model_version)
```

Example user question:

> “Why was alert ALT-1042 generated?”

Tool-driven flow:

```text
LLM
 ↓
get_alert
 ↓
get_signal_contributions
 ↓
get_sensor_history
 ↓
get_known_events
 ↓
structured explanation
```

Example output:

```text
Alert ALT-1042 exceeded the active anomaly threshold.

Observed evidence:
1. TP3 pressure began declining before the alert.
2. Oil temperature increased relative to recent baseline.
3. Motor-current behavior became unusually volatile.
4. These signals produced anomaly score 0.89 versus threshold 0.74.

This explanation identifies anomalous evidence; it does not prove a mechanical root cause.
```

Critical principle:

> **ML decides. LLM explains/investigates.**

---

# 29. Why the LLM Should Not Directly Judge Sensor Data

Weak architecture:

```text
sensor values
     ↓
GPT
     ↓
“machine is broken”
```

Problems:

- nondeterministic,
- difficult to evaluate,
- weak numerical grounding,
- poor auditability,
- unnecessary API dependency.

Preferred architecture:

```text
sensor data
    ↓
validated features
    ↓
ML model
    ↓
anomaly score
    ↓
alert
    ↓
structured evidence
    ↓
LLM explanation
```

The whole anomaly-detection platform remains functional if the LLM API is unavailable.

---

# 30. OpenVINO

OpenVINO should be a finishing optimization step, not a core dependency.

Sequence:

```text
PyTorch model
    ↓
validate correctness
    ↓
export/convert
    ↓
OpenVINO Runtime
    ↓
benchmark
```

Possible benchmark:

| Metric | PyTorch | OpenVINO |
|---|---:|---:|
| p50 latency | measured | measured |
| p95 latency | measured | measured |
| throughput | measured | measured |
| memory | measured | measured |
| model size | measured | measured |
| anomaly metric | measured | measured |

Possible optional quantized variant:

- OpenVINO INT8.

No performance improvement should be claimed before measurement.

Official reference repo:

https://github.com/openvinotoolkit/openvino_notebooks

---

# 31. Reference Repositories

These repositories are references, not a source-copying plan.

## 31.1 `firathdr/metroguard-ml`

https://github.com/firathdr/metroguard-ml

Highest-value reference for methodology.

Important ideas:

- temporal split,
- causal preprocessing,
- leakage prevention,
- event-level evaluation,
- threshold calibration,
- statistical baseline,
- Isolation Forest,
- temporal autoencoder,
- model/data card,
- FastAPI,
- reproducibility,
- leakage tests.

Principle:

> learn the methodology and architecture; rewrite the implementation for this project.

## 31.2 `krishna8399/iot-streaming-pipeline`

https://github.com/krishna8399/iot-streaming-pipeline

Useful reference for:

- CSV/historical replay,
- Kafka,
- Spark Structured Streaming,
- TimescaleDB,
- Grafana,
- FastAPI,
- Docker Compose.

Important caution previously discussed:

The repository is useful as an architectural reference, but code should not simply be copied. Reimplement the pattern and make independent design decisions.

## 31.3 DataTalksClub MLOps Zoomcamp

https://github.com/DataTalksClub/mlops-zoomcamp

Useful reference for:

- MLflow,
- experiment tracking,
- orchestration,
- deployment,
- monitoring,
- testing,
- CI/CD.

## 31.4 `Arvo-AI/aurora`

https://github.com/Arvo-AI/aurora

Useful conceptual reference for:

- tool-driven RCA,
- agentic incident investigation,
- evidence gathering before explanation.

Do not reproduce its full production complexity.

## 31.5 OpenVINO notebooks

https://github.com/openvinotoolkit/openvino_notebooks

Use official examples for:

- PyTorch/OpenVINO conversion,
- optimized inference,
- quantization,
- benchmark methodology.

## 31.6 PyTorch C-MAPSS RUL references

Example:

https://github.com/jiaxiang-cheng/PyTorch-LSTM-for-RUL-Prediction

Useful only as an optional model-learning reference.

C-MAPSS RUL is not the primary flagship problem.

---

# 32. Reuse Policy

The intended approach is **reference and integrate**, not “copy several repos and rename variables.”

## Safe/useful forms of reuse

- learn architectural patterns,
- adapt official library examples,
- use open-source libraries,
- reuse generic Docker/config patterns where license permits,
- reproduce published methodology independently,
- cite influences in README,
- write independent interfaces and system integration.

## Components that should be genuinely owned

- project domain framing,
- data contract,
- feature definitions,
- temporal split,
- leakage rules,
- threshold calibration,
- alert policy,
- model evaluation,
- API contracts,
- service integration,
- RCA tool schema,
- model-selection rationale,
- benchmark methodology,
- documentation.

The unique portfolio value is in **integration and defensible decisions**.

---

# 33. Proposed High-Level Architecture

```text
                 Official MetroPT Dataset
                           │
                  download + checksum
                           │
                      Raw storage
                           │
                    Parquet dataset
                           │
                           ├──────────────────────┐
                           │                      │
                           │                      ▼
                           │               Offline ML path
                           │                 Airflow DAG
                           │                      │
                           │              validation/features
                           │                      │
                           │             model training/eval
                           │                      │
                           │                    MLflow
                           │                      │
                           │                champion model
                           │                      │
                           ▼                      ▼
                  Historical Replay         model artifact
                           │                      │
                           ▼                      │
                         Kafka                    │
                           │                      │
                           ▼                      │
                 Spark stream processing         │
                           │                      │
                           ▼                      │
                   online features               │
                           │                      │
                  ┌────────┴─────────┐            │
                  ▼                  ▼            │
          Timescale/Postgres      FastAPI ◄───────┘
                                     │
                                     ▼
                                anomaly score
                                     │
                                     ▼
                                alert policy
                                     │
                                     ▼
                                   alert
                                     │
                         ┌───────────┴───────────┐
                         ▼                       ▼
                   Grafana/metrics        RCA Assistant
                                                 │
                                     deterministic tools
                                                 │
                                                 ▼
                                      structured explanation
```

---

# 34. Suggested Repository Layout

This is a design target, not a requirement to scaffold everything immediately.

```text
industrial-reliability-platform/
│
├── data/
│   └── README.md
│
├── services/
│   ├── replay-producer/
│   ├── feature-stream/
│   ├── inference-api/
│   ├── alert-service/
│   └── rca-agent/
│
├── ml/
│   ├── features/
│   ├── baselines/
│   ├── isolation_forest/
│   ├── autoencoder/
│   ├── evaluation/
│   └── openvino/
│
├── pipelines/
│   └── airflow/
│
├── monitoring/
│   ├── grafana/
│   ├── prometheus/
│   └── evidently/
│
├── infrastructure/
│   └── docker/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── data/
│   └── leakage/
│
├── docs/
│   ├── architecture.md
│   ├── data-card.md
│   └── model-card.md
│
└── docker-compose.yml
```

---

# 35. Build Order

The project must be built inside-out.

Do **not** begin by deploying every infrastructure component.

## Phase 1 — Offline ML feasibility

Question to prove:

> “Can abnormal periods around known MetroPT events be detected using leakage-safe evaluation?”

Build:

- dataset download,
- schema inspection,
- temporal split,
- feature extraction,
- robust statistical baseline,
- Isolation Forest,
- simple PyTorch Autoencoder,
- event-level evaluation.

Exit criteria:

- reproducible benchmark,
- no random time-series split,
- known limitations documented,
- actual metrics generated.

## Phase 2 — Productionize model

Build:

- ML artifact format,
- FastAPI scoring endpoint,
- model/version metadata,
- input validation,
- unit/integration tests.

Exit criteria:

```text
POST /v1/score
```

works reproducibly from a saved model.

## Phase 3 — Historical replay + streaming

Build:

- replay producer,
- Kafka,
- stream schema,
- Spark/window features,
- feature persistence.

Exit criteria:

Historical telemetry can be replayed and processed end-to-end.

## Phase 4 — Alerting

Build:

- threshold logic,
- persistence rule,
- alert merging,
- cooldown,
- alert storage/API.

Exit criteria:

A known abnormal replay period can generate a traceable alert.

## Phase 5 — MLOps

Build:

- MLflow,
- experiment logging,
- Airflow DAG,
- candidate/champion workflow.

Exit criteria:

A model can be reproduced and traced to:

- data version,
- feature version,
- training parameters,
- evaluation metrics.

## Phase 6 — Monitoring

Build:

- Prometheus metrics,
- Grafana dashboards,
- data-quality/drift checks,
- model-monitoring metrics.

Exit criteria:

The operator can distinguish service issues, data issues, and model anomalies.

## Phase 7 — RCA assistant

Build:

- alert investigation tools,
- one LLM provider,
- structured evidence,
- response schema,
- hallucination/grounding constraints.

Exit criteria:

A real alert ID can be explained entirely from tool-returned evidence.

## Phase 8 — OpenVINO

Build:

- PyTorch export/conversion,
- OpenVINO inference path,
- repeatable benchmark,
- optional quantization.

Exit criteria:

Measured comparison with PyTorch exists.

## Phase 9 — Portfolio polish

Build:

- architecture diagram,
- model card,
- data card,
- demo script/video,
- Docker/quickstart,
- benchmark tables,
- README,
- CV bullets.

---

# 36. Development Data Modes

Do not process the full dataset on every developer action.

Recommended modes:

```text
tests/fixtures/
    small synthetic/curated records
    ↓
fast CI and unit tests

dev/sample/
    small real historical slice
    ↓
local development

full dataset
    ↓
training/evaluation benchmark
```

The full dataset should not be committed to Git.

A download command should:

1. fetch official data,
2. verify checksum,
3. record source/version,
4. convert to efficient local format such as Parquet.

---

# 37. Testing Strategy

## Unit tests

Examples:

- feature calculations,
- threshold logic,
- alert persistence,
- schema validation,
- API models.

## Data tests

Examples:

- timestamp monotonicity,
- duplicate handling,
- valid sensor columns,
- null constraints,
- expected sampling properties.

## Leakage tests

Critical.

Examples:

- training rows must occur before calibration/test,
- scaler must only fit training data,
- threshold must not use test data,
- future observations must never enter past features,
- centered rolling windows prohibited for online features.

## Integration tests

Examples:

```text
sample telemetry
      ↓
feature pipeline
      ↓
model
      ↓
alert
```

## API contract tests

Ensure:

- stable response schema,
- model-version metadata,
- deterministic error handling.

---

# 38. Error Handling Principles

## Bad input

Invalid telemetry should be rejected or routed separately.

Possible categories:

- invalid schema,
- malformed timestamp,
- unknown field,
- missing critical value,
- impossible data type.

## Streaming errors

Potential DLQ:

```text
sensor.dlq
```

for records that cannot safely enter the main processing path.

## Model unavailable

Inference API should fail explicitly rather than silently producing defaults.

## LLM unavailable

The anomaly-detection and alert system must continue operating.

The UI/API can report:

```text
RCA explanation temporarily unavailable
```

while still exposing structured alert evidence.

---

# 39. Security / Secrets

LLM API keys must not be committed.

Example:

```text
.env
LLM_API_KEY=...
```

Repository should provide:

```text
.env.example
```

No real secret.

Other development credentials should follow the same pattern.

---

# 40. Explicit Non-Goals

To keep the project feasible, the first flagship version should **not** attempt all possible industrial-AI problems.

Out of scope initially:

- hardware sensor design,
- PLC programming,
- SCADA engineering,
- control-system actuation,
- automatically stopping real machinery,
- safety-critical deployment,
- proving physical root cause,
- custom distributed Kafka cluster,
- Kubernetes production platform,
- multi-cloud infrastructure,
- multiple LLM agents,
- multi-provider LLM routing,
- custom foundation-model training,
- a second unrelated AI project,
- RUL as a full additional subsystem,
- semiconductor-specific hardware simulation.

These can only be revisited after the flagship is complete.

---

# 41. Key Engineering Principles

## Principle 1 — ML before infrastructure

First prove the data/model problem.

Do not spend weeks building Kafka/Airflow before demonstrating meaningful anomaly evaluation.

## Principle 2 — simple baseline first

Always compare complex models with simpler alternatives.

## Principle 3 — temporal correctness over impressive accuracy

A modest leakage-safe result is more valuable than fake 99% accuracy.

## Principle 4 — every tool needs a reason

Kafka, Spark, Airflow, MLflow, Grafana, LLM and OpenVINO must solve different problems.

No tool should exist only for CV keywords.

## Principle 5 — evidence before explanation

The LLM may summarize evidence but must not manufacture measurements or mechanical facts.

## Principle 6 — measured claims only

Never claim:

- latency reduction,
- throughput gain,
- F1,
- detection rate,
- false-alarm rate,
- lead time

until measured by the project.

## Principle 7 — report model trade-offs

If Isolation Forest beats a deep model, report it.

If OpenVINO provides little improvement, report it.

Engineering judgment is part of the portfolio signal.

---

# 42. Competitive Differentiation

The project should avoid becoming any of these common weak patterns:

```text
CSV → notebook → XGBoost → 99% accuracy
```

or:

```text
synthetic sensor generator → Kafka → dashboard
```

or:

```text
sensor JSON → GPT → “machine is broken”
```

or:

```text
20 technologies in docker-compose with no evaluated ML question
```

The stronger target is:

```text
large real telemetry
      ↓
causal feature engineering
      ↓
leakage-safe benchmark
      ↓
operational anomaly model
      ↓
historical stream replay
      ↓
production inference
      ↓
alert policy
      ↓
monitoring
      ↓
tool-grounded RCA
      ↓
measured OpenVINO optimization
```

---

# 43. What the Recruiter Should Be Able to Ask

The repository should create strong interview discussion points.

## Data

- Why MetroPT?
- How large is the dataset?
- What does one row mean?
- How were gaps handled?
- Why Parquet?
- How did you avoid future leakage?

## ML

- Why anomaly detection instead of supervised failure classification?
- Why Isolation Forest?
- Why Autoencoder?
- What was the simple baseline?
- How did you choose threshold?
- Which model actually performed best?
- What are the failure-event limitations?

## Streaming

- Why Kafka?
- Why Spark?
- What is event time?
- What happens during replay?
- What happens with invalid messages?
- Why does replay speed not alter source timestamps?

## Backend

- How is model serving versioned?
- How are alerts persisted?
- What does the API return?
- What happens when a dependency fails?

## MLOps

- How can an experiment be reproduced?
- How is a model promoted?
- How do data/model versions connect?

## Agent

- What can the LLM access?
- How do you prevent hallucinated metrics?
- What does “root cause” mean in this system?
- What happens if the provider is offline?

## Performance

- What did OpenVINO improve?
- How was latency measured?
- Was accuracy affected by quantization?

---

# 44. Desired Demo

A compelling final demo sequence:

1. Start the platform.
2. Select a historical MetroPT period containing an interesting event.
3. Replay at accelerated speed.
4. Show telemetry entering the system.
5. Show feature/anomaly score changing.
6. Show alert generated after persistence policy.
7. Open alert details.
8. Show top abnormal signals/evidence.
9. Ask RCA assistant:
   “Why was this alert generated?”
10. Agent queries tools and explains evidence.
11. Show MLflow experiment/model provenance.
12. Show Grafana operational/model dashboard.
13. Show PyTorch vs OpenVINO benchmark.

This demo tells one integrated engineering story.

---

# 45. Possible Future CV Description

Do not use exact numeric results until measured.

Possible final format:

**Industrial Reliability Intelligence Platform**

> Built a production-oriented anomaly-detection platform over 10M+ real industrial telemetry records, combining leakage-safe temporal evaluation, streaming feature processing, MLflow-managed scikit-learn/PyTorch models, FastAPI inference, operational alerting, and evidence-grounded RCA.

Second bullet:

> Benchmarked statistical, Isolation Forest, and temporal autoencoder approaches using event-level recall, lead time, false alarms/day and PR-AUC; optimized the selected PyTorch inference path with OpenVINO and measured latency/throughput trade-offs under concurrent load.

Every numeric claim in the eventual CV must come from measured project artifacts.

---

# 46. Current Decisions That Are Considered Chosen

Unless future evidence invalidates them, current decisions are:

1. **Flagship problem:** industrial anomaly detection / early warning.
2. **Primary dataset:** MetroPT 2022.
3. **Hardware acquisition:** out of scope.
4. **System boundary:** timestamped digital telemetry onward.
5. **ML approach:** unsupervised/semi-supervised anomaly detection first.
6. **Baseline:** robust statistical detector.
7. **Classical ML:** Isolation Forest.
8. **Deep ML:** PyTorch Autoencoder / temporal Autoencoder.
9. **Evaluation:** time-based split; no random row split.
10. **Primary metrics:** event recall, lead time, false alarms/day, PR-AUC, time-in-alert.
11. **Streaming:** historical replay → Kafka → Spark/window processing.
12. **Serving:** FastAPI.
13. **Experiment tracking:** MLflow.
14. **Orchestration:** Airflow after ML feasibility is proven.
15. **Monitoring:** Prometheus/Grafana plus data/model monitoring.
16. **LLM:** not required for anomaly detection.
17. **LLM role:** tool-grounded RCA/explanation.
18. **Initial LLM deployment:** one provider API is acceptable.
19. **Local LLM:** optional later.
20. **OpenVINO:** final optimization/benchmark layer.
21. **Second project:** not a priority until this flagship is complete.
22. **Reuse strategy:** reference methodologies and patterns; own the integration and decisions.

---

# 47. Open Questions for the Next Brainstorming Pass

These have intentionally **not** been frozen yet.

1. Exact MetroPT version/file used as the canonical primary dataset.
2. Exact sensor columns included in Phase 1.
3. Exact known event timestamps used for evaluation.
4. Exact train/calibration/test date boundaries.
5. Exact aggregation window size.
6. Whether first deep model is plain dense Autoencoder or TCN Autoencoder.
7. Exact threshold-calibration strategy.
8. Exact event early-warning window definition.
9. Exact alert persistence/cooldown policy.
10. PostgreSQL vs TimescaleDB choice for the first online store.
11. Whether Spark is required from the first streaming version or introduced after a simpler consumer.
12. Which LLM provider is used first.
13. Exact RCA tool contracts.
14. OpenVINO model/export format and target hardware.
15. Final project branding/name.

These should be resolved **before or during the implementation plan**, not guessed now.

---

# 48. Recommended Next Design Session

The next brainstorming/design step should focus only on **Phase 1: Offline ML Feasibility**.

The purpose is to turn:

```text
MetroPT dataset
    ↓
features
    ↓
models
    ↓
evaluation
```

into an exact executable design.

That session should decide:

1. which MetroPT columns matter,
2. what each sensor means at a beginner-friendly level,
3. how timestamps and events are represented,
4. exact train/calibration/test split,
5. exact causal features,
6. baseline model,
7. Isolation Forest configuration,
8. first PyTorch Autoencoder architecture,
9. threshold selection,
10. event-level metrics,
11. leakage tests,
12. acceptance criteria for proceeding to streaming.

Only after Phase 1 is approved should the project move into implementation planning.

---

# 49. Design Status

This specification consolidates the current brainstorming discussion.

It is a **design document**, not an implementation plan.

No production code should be treated as approved solely because it appears in this document.

The next formal Superpowers step after user review/approval of the design is to create a dedicated implementation plan.

