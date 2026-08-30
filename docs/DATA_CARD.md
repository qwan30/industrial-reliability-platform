# Data Card — MetroPT-3 Compressor Telemetry Dataset

## 1. Dataset Summary & Identity

- **Name:** UCI MetroPT-3 dataset (Urban Railway Train Air Production Unit)
- **DOI:** `10.24432/C5VW3R`
- **Download URL:** `https://archive.ics.uci.edu/static/public/791/metropt%2B3%2Bdataset.zip`
- **Archive Checksum (SHA-256):** `aab991a970e58210de853bb8078ce0e63abb4d9412fdc5c79792dae3d8e1721a`
- **Normalized Observations:** `1,516,948` rows
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)

---

## 2. Canonical Schema

The dataset contains 15 analog and digital sensor streams sampled at approximately 10-second intervals:

### Analog Signals:
- `tp2`: Pressure in the compressor output line (bar)
- `tp3`: Pressure in the main reservoir (bar)
- `h1`: Pressure in the separator filter (bar)
- `dv_pressure`: Pressure drop across air dryer (bar)
- `reservoirs`: Pressure in auxiliary reservoirs (bar)
- `oil_temperature`: Compressor lubricating oil temperature (°C)
- `motor_current`: Electrical motor current draw (A)

### Digital State Signals:
- `comp`: Compressor electrical contactor state (0/1)
- `dv_electric`: Air dryer electrical drain valve command (0/1)
- `towers`: Desiccant drying tower selector (0/1)
- `mpg`: Compressor emergency pressure governor switch (0/1)
- `lps`: Low pressure safety switch (*preserved strictly as evaluation evidence; excluded from all features*)
- `pressure_switch`: Main pressure regulation switch (0/1)
- `oil_level`: Lubricating oil reservoir level switch (0/1)
- `caudal_impulses`: Air flow impulse counter pulses

---

## 3. Partitions & Preprocessing Contract

### Temporal Partitioning (Zero Lookahead / Leakage):
- **Train Split:** `[2020-02-01 00:00:00, 2020-02-22 00:00:00)` (Normal baseline operation)
- **Calibration Split:** `[2020-02-22 00:00:00, 2020-03-01 00:00:00)` (Threshold selection & scaling)
- **Holdout Split:** `[2020-03-01 00:00:00, 2020-09-01 04:00:00)` (Locked evaluation set)

### Windowing & Aggregation:
- **Binning:** 5-minute right-closed bins requiring $\ge 24$ readings ($\ge 80\%$ window density).
- **Lookback:** 6 consecutive valid 5-minute bins (30-minute lookback window, 5-minute stride).
- **Segmentation:** Any timestamp regression, missing bin, or sequence gap closes the active segment and purges rolling state. No interpolation or synthetic backfill is performed.
- **Split Containment:** Every candidate 30-minute feature window must be wholly contained within a single split (`split.start <= window_start` and `window_end <= split.end`). Windows that cross partition boundaries (such as train-to-calibration or calibration-to-holdout transitions) are explicitly skipped and rejected to guarantee strict temporal isolation without cross-split feature leakage. Corrected full-data outputs are versioned instead of in-place replacing historical Phase 1B artifacts.

### Executable physical contract

The executable contract records each analog unit and a conservative hard ingestion
envelope. Values outside the envelope are rejected or quarantined, never clipped.
These bounds detect clear unit/sensor contract violations; they are not anomaly
thresholds. Source timestamps remain timezone-naive because the dataset supplies no
offset. Nominal cadence is 10 seconds. Contract-v2 full-data output is published as
Phase 1C and does not overwrite Phase 1B evidence.
