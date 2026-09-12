# Industrial Reliability Platform — UI Vision & Architecture Upgrade Audit

## 1. Executive Summary

This document captures the audit findings, architectural assessments, and UI vision for upgrading the Industrial Reliability Platform into a professional 3D Industrial Reliability Virtual Lab.

- **Baseline Commit**: `b53555777aa8ae7118432c28ce36fda1a11205b4`
- **Audit Scope**: Full stack assessment covering domain boundaries, simulation feasibility, 3D interaction models, persistence durability, and UI art direction.
- **Strategic Direction**: Rather than coercing single-train MetroPT replay data into a simulated multi-machine factory, the system establishes an independent, bounded Virtual Lab domain (`src/industrial_reliability/lab/`) powered by a verified lumped-parameter isothermal pneumatic network solver (`pneumatic-isothermal-v1`) and custom-authored PBR 3D digital assets.

---

## 2. Historical Context & Audit Findings

### 2.1 Feasibility & ML Hard Realities
Historical evaluations across PRs #7–#20 established that production ML anomaly detection on MetroPT-3 is currently **NOT FEASIBLE**:
- Statistical detector: 3/4 detected events with 5.707 false episodes/day.
- Isolation Forest: 4/4 detected events with 16.784 false episodes/day.
- Autoencoder: 4/4 detected events with 26.158 false episodes/day.

**Architectural Decision**: The 3D Virtual Lab does not attempt to disguise historical ML unfeasibility as production-ready. Instead:
- Replay mode preserves raw MetroPT datasets with small-multiples time series visualization and honest data gap indicators.
- Simulation mode introduces an experimental synthetic baseline calibrated via rigorous multi-split simulations (3 train, 2 calibration, 2 test runs) with quantile-calibrated thresholding and documented limitations.

### 2.2 Replay Domain vs. Simulation Domain
- `TelemetryEventV1` and `ScoreDecisionV1` in the legacy runtime are bound strictly to MetroPT dataset schema (TP2, TP3, H1, DV_pressure, Motor_current, Oil_temperature).
- Attempting to duplicate or fabricate multiple compressor instances on this schema produces silent data corruption and invalid attribution.
- **Solution**: The Virtual Lab bounded context (`lab-definition-v1`) introduces independent typed contracts for arbitrary networked topologies: `COMPRESSOR`, `TANK`, `ISOLATION_VALVE`, `CONTROL_VALVE`, and `DEMAND`.

---

## 3. Art Direction & Industrial Training Floor

### 3.1 Visual Philosophy
The virtual lab adopts an **Industrial Training Floor** aesthetic:
- Clean, realistic technical workshop with controlled lighting and subtle signs of operational use.
- Avoids sci-fi, dark-neon, or "cyberpunk" tropes that detract from industrial engineering fidelity.
- PBR palette:
  - Machine Enamel: `#315B70` (roughness 0.35, metalness 0.3)
  - Industrial Metal: `#89949F` (roughness 0.25, metalness 0.8)
  - Gasket Rubber: `#20262D` (roughness 0.85, metalness 0.1)
  - Concrete Floor: `#B8BEC4` (roughness 0.95, metalness 0.05)
  - Safety Yellow: `#D4A017` (roughness 0.45, metalness 0.2)

### 3.2 100% Original Deterministic 3D Assets
All 3D assets are procedurally generated in-repo via `generate_lab_assets.mjs` using Three.js and exported to binary GLB format (`/lab-assets/`):
1. `compressor.glb`: Rotary air compressor enclosure (1.6×1.0×1.4m) with animated fan rotor, pressure gauge, and `port_OUT` flange.
2. `tank.glb`: Vertical air receiver (0.5 m³) with dished heads, support legs, weld reinforcement rings, and dual `port_A`/`port_B` flanges.
3. `isolation-valve.glb`: Quarter-turn block valve with 90° rotatable handle.
4. `control-valve.glb`: Modulating throttle valve with diaphragm pneumatic actuator dome and position indicator.
5. `demand.glb`: Industrial pneumatic consumer cabinet with ventilation louvers and `port_IN` intake flange.
6. `pressure-sensor.glb`: Dial gauge with mounting stem and needle.
7. `flow-sensor.glb`: Inline pipe collar with digital transmitter enclosure.

---

## 4. Bounded Context Architecture

```text
3D Builder / Operator Console (React 18 + R3F)
      │                     │
      ▼ /v2/labs            ▼ /v2/runs/{id}/commands
 lab-api (:8010)       lab_commands
      │                     ▲
      ▼ lab_revisions       │
 PostgreSQL (irp)           │
      ▲                     │
      │ lease/fence         │ (claim)
 lab-worker (SimulationEngine)
      │
      ├─► Numerical Solver (dt=0.05s)
      ├─► lab_outbox (observations) ──► Kafka (irp.lab.observations.v1)
      └─► lab_history (1Hz snapshots)
```

---

## 5. Verification & Acceptance Criteria
- **Mass Conservation**: Closed-loop mass error `< 1e-12 kg` across 200 physics ticks.
- **Analytical Refinement**: Exponential receiver discharge achieves first-order convergence ratio `h/2 < 0.6 * h`.
- **Identity & Idempotency**: Duplicate command IDs return original receipts without mutating simulation sequence or state.
- **Zero Placeholder Geometries**: Production builds use complete PBR GLB assets with exact anchor alignment.
