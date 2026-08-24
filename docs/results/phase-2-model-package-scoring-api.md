# Phase 2 Model Package & Stateless Scoring API Certification Report

## Executive Summary

Phase 2 (**Champion Model Package and Stateless Scoring API**) establishes a deterministic, tamper-evident scoring runtime. The model package bundles one verified champion detector, one train-only evidence baseline, and three calibration golden cases anchored by an external manifest SHA-256 trust anchor.

Stateless scoring is exposed via FastAPI `POST /v1/score` with strict Pydantic v2 schemas (`extra="forbid"`, `frozen=True`), ensuring zero runtime feature construction, zero multi-model branching, and fail-closed integrity verification before deserialization.

---

## 1. Package Architecture & Provenance

- **Schema Version:** `champion-package-v1`
- **Source Champion Schema:** `phase1b-champion-v1`
- **Artifact Composition:**
  - `manifest.json`: Metadata, active feature names, threshold, provenance, and child SHA-256 hashes.
  - `detector.joblib`: Serialized fitted detector (`scikit-learn` / `RobustStatisticalDetector` / `DenseAutoencoder`).
  - `evidence-baseline.npz`: Train-only median and MAD vectors for robust deviation calculation.
  - `golden-cases.json`: Top-level `champion-golden-cases-v1` containing 3 calibration cases (earliest valid, highest normal, earliest anomalous).
- **Trust Anchor:** The runtime requires external environment injection of `CHAMPION_MANIFEST_SHA256`. The loader strictly verifies manifest SHA-256 and child artifact hashes before calling `joblib.load()`.

---

## 2. API Contract & Endpoints

| Endpoint | Method | Purpose | Response Format |
|---|---|---|---|
| `/healthz` | `GET` | Liveness probe (no model details) | `{"success": true, "data": {"status": "ok"}, "error": null}` |
| `/readyz` | `GET` | Readiness probe (verified load) | `{"success": true, "data": {"status": "ready"}, "error": null}` |
| `/v1/score` | `POST` | Stateless synchronous scoring | `ScoreResponseV1` with `ScoreDecisionV1` |

### Error Envelopes & HTTP Status Codes

- **409 Conflict (`SCORING_CONTRACT_MISMATCH`)**: Raised on contract SHA mismatch, dataset SHA mismatch, model version mismatch, or feature order/name mismatch.
- **422 Unprocessable Entity (`INVALID_REQUEST`)**: Raised on schema validation error, non-finite feature values, or extra fields.

---

## 3. Parity & Verification Evidence

1. **Golden Parity Test**:
   - Every golden case in `golden-cases.json` produces exact expected score within `1e-9` tolerance via `POST /v1/score`.
   - Robust evidence deviation vector matches baseline calculation:
     $$\text{deviation}_i = \frac{|x_i - \text{median}_i|}{1.4826 \times \text{MAD}_i}$$
2. **Container Image**:
   - Built on `python:3.12.10-slim-bookworm` with non-root execution (`USER 65532:65532`).
   - Package mounted read-only at runtime; no model binaries baked into the base image.
   - Bound to localhost in local deployment topologies.
