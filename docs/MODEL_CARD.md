# Model Card — Industrial Anomaly Detection Candidate Ladder

## 1. Model Details & Intended Use

- **Model Families Evaluated:**
  1. `statistical`: Robust Mahalanobis-like deviation detector using median and interquartile range (IQR) baselines.
  2. `isolation_forest`: Ensemble of 200 isolation trees fitted on train partition (`max_samples="auto"`, `seed=42`).
  3. `autoencoder`: Dense PyTorch reconstruction autoencoder (`[input, 64, 16, 64, input]`, ReLU activations, MSE loss, Adam optimizer, 20 CPU epochs).
- **Intended Use:** Detection of abnormal compressor pressure/temperature operational patterns prior to component breakdown.
- **Out-of-Scope:** Autonomous mechanical failure diagnosis or automatic shutdown actuation without human engineer verification.

---

## 2. Evaluation Evidence & Feasibility Limits

### Predeclared Acceptance Criteria:
- Detect $\ge 3$ of 4 UCI annotated incident intervals (`metropt3-1` through `metropt3-4`);
- False alarm rate $\le 1.0$ false episodes per normal-exposure operating day;
- Cumulative time in alert state $\le 5.0\%$.

### Offline Evaluation Findings (Phase 1 / 1B):
- **Statistical Model:** Detected 3/4 events with 2.41% time in alert, but exhibited 5.71 false episodes/day (exceeding the false alarm ceiling).
- **Isolation Forest:** Detected 4/4 events, but exhibited 15.66% time in alert and 13.15 false episodes/day.
- **Autoencoder:** Detected 4/4 events, but exhibited 31.68% time in alert and 30.670 false episodes/day.
- **Result:** **`NOT FEASIBLE`** — No candidate model met the strict operational false-alarm ceiling under zero-leakage holdout evaluation.


---

## 3. Grounded Root-Cause Analysis (RCA) Integration

- **Generator:** OpenAI structured outputs (`responses.parse` with Pydantic JSON schema).
- **Closed-World Grounding:** Every generated claim must cite $\ge 1$ allowlisted evidence items (`get_alert`, `get_score_evidence`, `get_model_provenance`, `get_system_health`).
- **Uncertainty Notice:** Every report explicitly caveats that anomaly scores and statistical deviations do not constitute proof of physical mechanical root cause.

---

## 4. Operational Gating & Research Candidate Status

- **Package Role:** `RESEARCH_CANDIDATE` (Operational Status: `RESEARCH_ONLY`).
- **Gating Enforced:** The runtime API and streaming worker reject candidate loading unless `ALLOW_RESEARCH_CANDIDATE=true` is explicitly configured.
- **Scientific Integrity:** The NOT FEASIBLE evaluation verdict is preserved permanently; the platform never falsely promotes candidate models to production champions without true feasibility evidence.
