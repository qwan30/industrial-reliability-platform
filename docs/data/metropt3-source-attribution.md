# MetroPT-3 Source Attribution and Data Contract

- **Source Dataset:** MetroPT-3 Dataset (UCI Machine Learning Repository)
- **UCI Repository ID:** 791
- **DOI:** `10.24432/C5VW3R`
- **URL:** `https://archive.ics.uci.edu/static/public/791/metropt%2B3%2Bdataset.zip`
- **Candidate Archive SHA-256:** `aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a`
- **CSV Member Name:** `MetroPT3(AirCompressor).csv`
- **Expected Observations:** `1,516,948` rows
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Access / Verification Date:** 2026-08-24
- **Storage Policy:** Raw datasets, intermediate partitions, extracted features, and model binaries remain strictly local and git-ignored under `artifacts/` or `data/raw/`. Only source attributions, aggregate metrics, and contracts are committed.

## Incident Windows (Minute Precision)

| ID | Condition | Source Start (Minute) | Source End (Minute) | Normalized Interval $[T_{\text{start}}, T_{\text{end}})$ |
|---|---|---|---|---|
| `metropt3-1` | air leak / high stress | `2020-04-18 00:00` | `2020-04-18 23:59` | `[2020-04-18 00:00, 2020-04-19 00:00)` |
| `metropt3-2` | air leak / high stress | `2020-05-29 23:30` | `2020-05-30 06:00` | `[2020-05-29 23:30, 2020-05-30 06:01)` |
| `metropt3-3` | air leak / high stress | `2020-06-05 10:00` | `2020-06-07 14:30` | `[2020-06-05 10:00, 2020-06-07 14:31)` |
| `metropt3-4` | air leak / high stress | `2020-07-15 14:30` | `2020-07-15 19:00` | `[2020-07-15 14:30, 2020-07-15 19:01)` |
