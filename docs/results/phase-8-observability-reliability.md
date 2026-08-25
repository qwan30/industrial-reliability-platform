# Phase 8 Observability & Reliability Drill Report

**Generated:** `2026-08-25T04:17:41.719667+00:00`  
**Overall Status:** `PASSED`  
**Report Self SHA-256:** `6e54049af2e7544c6c72de2229af228b2fa5705cd342aab4d12500864113027e`  

## Summary of Fault Isolation Drills

| Drill Type | Expected Fault | Actual Classification | Status | Evidence Summary |
| :--- | :--- | :--- | :--- | :--- |
| `scoring-outage` | `SERVICE` | `SERVICE` | ✅ PASS | Scoring unavailable (1 requests), 0 quarantined records, 0 anomalous decisions |
| `malformed-telemetry` | `DATA` | `DATA` | ✅ PASS | Telemetry quarantined (1 records) or segment broken (0), downstream scoring uncorrupted |
| `known-abnormal-replay` | `MACHINE` | `MACHINE` | ✅ PASS | Scoring succeeded (1 ok) and detected authentic anomalous degradation (1 anomalous decisions, 1 alert events) |

## Detailed Metric Signatures

### Drill: `scoring-outage`
- **Expected Classification:** `SERVICE`
- **Actual Classification:** `SERVICE`
- **Passed:** `True`
- **Metric Deltas:**
  - `telemetry_accepted_delta`: 0.0
  - `telemetry_quarantined_delta`: 0.0
  - `segment_breaks_delta`: 0.0
  - `score_ok_delta`: 0.0
  - `score_unavailable_delta`: 1.0
  - `anomaly_decisions_delta`: 0.0
  - `alert_events_delta`: 0.0
  - `kafka_lag_max`: 0.0
  - `feature_psi_max`: 0.0
- **Evidence:** Scoring unavailable (1 requests), 0 quarantined records, 0 anomalous decisions

### Drill: `malformed-telemetry`
- **Expected Classification:** `DATA`
- **Actual Classification:** `DATA`
- **Passed:** `True`
- **Metric Deltas:**
  - `telemetry_accepted_delta`: 0.0
  - `telemetry_quarantined_delta`: 1.0
  - `segment_breaks_delta`: 0.0
  - `score_ok_delta`: 0.0
  - `score_unavailable_delta`: 0.0
  - `anomaly_decisions_delta`: 0.0
  - `alert_events_delta`: 0.0
  - `kafka_lag_max`: 0.0
  - `feature_psi_max`: 0.0
- **Evidence:** Telemetry quarantined (1 records) or segment broken (0), downstream scoring uncorrupted

### Drill: `known-abnormal-replay`
- **Expected Classification:** `MACHINE`
- **Actual Classification:** `MACHINE`
- **Passed:** `True`
- **Metric Deltas:**
  - `telemetry_accepted_delta`: 0.0
  - `telemetry_quarantined_delta`: 0.0
  - `segment_breaks_delta`: 0.0
  - `score_ok_delta`: 1.0
  - `score_unavailable_delta`: 0.0
  - `anomaly_decisions_delta`: 1.0
  - `alert_events_delta`: 1.0
  - `kafka_lag_max`: 0.0
  - `feature_psi_max`: 0.0
- **Evidence:** Scoring succeeded (1 ok) and detected authentic anomalous degradation (1 anomalous decisions, 1 alert events)
