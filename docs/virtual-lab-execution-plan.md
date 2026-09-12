# Industrial Reliability Virtual Lab — Execution Specification & Architecture

## 1. Overview & Objective

The Industrial Reliability Virtual Lab is an interactive 3D engineering simulation environment enabling operators and reliability engineers to:
1. Construct and customize pneumatic networks with arbitrary multi-compressor, multi-tank, and valve topologies.
2. Execute real-time lumped-parameter physics simulations (`pneumatic-isothermal-v1`) with operational command dispatch.
3. Inject faults (leaks, stuck valves, sensor bias/dropout, compressor trips) and observe physical propagation.
4. Perform root cause analysis (RCA) backed by immutable evidence bundles.
5. Review historical MetroPT telemetry alongside synthetic simulation experiments.

---

## 2. Core Architecture & Bounded Contexts

The platform maintains two clean bounded contexts:

### 2.1 Replay Context (`/v1`)
- Services historical Portuguese railway MetroPT-3 compressor recordings.
- Pure playback controls (`START`, `PAUSE`, `RESUME`, `STOP`).
- Does not accept physical mutations or synthetic layout modifications.
- Small-multiples time series visualization with data gap indicators.

### 2.2 Virtual Lab Context (`/v2`)
- Free-form editable industrial pneumatic lab with arbitrary graph connectivity.
- Backend API service `lab-api` running on port 8010.
- Simulation worker `lab-worker` managing backward Euler numerical solving, outbox publishing to Kafka (`irp.lab.observations.v1`), and 1Hz durable history frames.

---

## 3. Physical Model: `pneumatic-isothermal-v1`

- **Constants**: $R = 287.05\text{ J/(kg}\cdot\text{K)}$, $T = 293.15\text{ K}$, $P_{\text{atm}} = 101325\text{ Pa}$, $\Delta t = 0.05\text{ s}$.
- **Storage Nodes**: Capacitance $C_i = V_i / (R \cdot T)$, mass $m_i = C_i \cdot p_i$.
- **Edges**: Conductance $K$, mass flow $q_{ij} = K \cdot (p_i - p_j)$.
- **Compressor Source**: $q_{\text{in}} = q_{\text{nom}} \cdot \text{load} \cdot \max(0, 1 - p / p_{\text{max}})$.
- **Demand / Leak Sink**: $q_{\text{out}} = K_{\text{sink}} \cdot \max(0, p - P_{\text{atm}})$.
- **Active Set Backward Euler**:
  $$(\text{diag}(C / \Delta t + b) + L) \cdot p_{\text{next}} = (C / \Delta t) \cdot p_{\text{prev}} + a$$
- **Conservation Gate**:
  $$|\sum(m_{\text{next}} - m_{\text{prev}}) - \Delta t \sum(q_{\text{src}} - q_{\text{sink}})| \le 10^{-9} + 10^{-8} \sum |m_{\text{prev}}|$$

---

## 4. REST & SSE Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/v2/healthz` | Liveness probe (200 OK) |
| GET | `/v2/readyz` | Readiness probe verifying DB, worker heartbeat, and Kafka |
| GET | `/v2/catalog` | Equipment catalog and 3D asset manifest |
| GET | `/v2/templates/reference` | Deterministic 4-train reference lab definition |
| GET | `/v2/labs` | Paginated lab definition list |
| POST | `/v2/labs` | Create blank or reference lab |
| GET | `/v2/labs/{id}` | Get lab definition |
| PUT | `/v2/labs/{id}` | Optimistic update with revision check (409 on conflict) |
| POST | `/v2/labs/{id}/validate` | Validate graph structure and run eligibility |
| POST | `/v2/runs` | Create and initialize a simulation run |
| GET | `/v2/runs/{id}` | Get latest committed snapshot |
| POST | `/v2/runs/{id}/commands` | Submit operational or lifecycle command |
| GET | `/v2/runs/{id}/stream` | SSE stream for real-time snapshots and durable events |
| GET | `/v2/runs/{id}/history` | Retrieve 1Hz sampled historical frames |

---

## 5. 3D Renderer & Digital Assets

- React 18 + React Three Fiber 8.17 + Drei 9.117 + Three.js 0.170.
- All models procedurally authored in Node.js ESM via `generate_lab_assets.mjs` and exported to GLB format with verified SHA256 signatures:
  - `compressor.glb` (47 KB)
  - `tank.glb` (116 KB)
  - `isolation-valve.glb` (31 KB)
  - `control-valve.glb` (42 KB)
  - `demand.glb` (19 KB)
  - `pressure-sensor.glb` (16 KB)
  - `flow-sensor.glb` (21 KB)
