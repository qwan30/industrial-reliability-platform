# Phase 1B MetroPT-3 Fresh Validation Results

- **Verdict:** `NOT FEASIBLE`
- **Selected Model:** `None`
- **Contract SHA-256:** `31f8689256951067e28c9cbb48a930c1617d8eea8c7133ba1a315f632842e1ad`
- **Source Dataset SHA-256:** `aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a`

## Model Evaluation Comparison

| Model | Detected Events | False Episodes/Day | Time in Alert | PR-AUC | Feasible |
|---|---|---|---|---|---|
| `statistical` | 3/4 | 5.707 | 2.41% | 0.0503 | `False` |
| `isolation_forest` | 4/4 | 16.784 | 17.39% | 0.4332 | `False` |
| `autoencoder` | 4/4 | 26.158 | 29.00% | 0.2300 | `False` |

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
| `isolation_forest` | `metropt3-4` | `True` | 600 |
| `autoencoder` | `metropt3-1` | `True` | 52500 |
| `autoencoder` | `metropt3-2` | `True` | 2100 |
| `autoencoder` | `metropt3-3` | `True` | 3000 |
| `autoencoder` | `metropt3-4` | `True` | 51600 |
