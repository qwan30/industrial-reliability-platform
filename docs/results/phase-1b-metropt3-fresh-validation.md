# Phase 1B MetroPT-3 Fresh Validation Results

- **Verdict:** `NOT FEASIBLE`
- **Selected Model:** `None`
- **Contract SHA-256:** `149e164748522fe6dfa844a8de70b29ee1259122962e036ff6a563c1120047d8`
- **Source Dataset SHA-256:** `aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a`

## Model Evaluation Comparison

| Model | Detected Events | False Episodes/Day | Time in Alert | PR-AUC | Feasible |
|---|---|---|---|---|---|
| `statistical` | 3/4 | 5.707 | 2.41% | 0.0503 | `False` |
| `isolation_forest` | 4/4 | 13.146 | 15.66% | 0.3833 | `False` |
| `autoencoder` | 4/4 | 30.670 | 31.68% | 0.2295 | `False` |

## Individual Event Detections

| Model | Event ID | Detected | Lead Time (seconds) |
|---|---|---|---|
| `statistical` | `metropt3-1` | `False` | N/A |
| `statistical` | `metropt3-2` | `True` | 600 |
| `statistical` | `metropt3-3` | `True` | 3000 |
| `statistical` | `metropt3-4` | `True` | 6000 |
| `isolation_forest` | `metropt3-1` | `True` | 52200 |
| `isolation_forest` | `metropt3-2` | `True` | 6900 |
| `isolation_forest` | `metropt3-3` | `True` | 3000 |
| `isolation_forest` | `metropt3-4` | `True` | 6600 |
| `autoencoder` | `metropt3-1` | `True` | 52500 |
| `autoencoder` | `metropt3-2` | `True` | 2400 |
| `autoencoder` | `metropt3-3` | `True` | 3000 |
| `autoencoder` | `metropt3-4` | `True` | 51600 |
