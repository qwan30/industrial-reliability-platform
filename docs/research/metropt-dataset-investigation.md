# MetroPT dataset investigation

## Scope, pre-flight, and method

[Raw dataset directory metadata] Initial pre-flight found `dataset_train.csv` (1,646,201,046 bytes), `dataset_train.csv.crdownload` (368,560,536 bytes), and `dataset_train.csv.aria2` (395 bytes). The target file was initially being written by `aria2c`; analysis began only after that process exited and the target's size and modification time were unchanged for three checks over 30 seconds. The `.aria2` control file then no longer existed. Neither incomplete-transfer artifact was opened, hashed, parsed, renamed, deleted, or otherwise analyzed.

[Raw dataset] Only `data/raw/metropt/dataset_train.csv` was hashed and parsed. The pass used Python's standard CSV reader, one row at a time, constant-size accumulators, timestamp-group-local duplicate comparison, the 20 largest gaps, and a bounded deterministic sample of 84,168 rows for approximate quantiles. Exact counts, extrema, means, population standard deviations, missingness, duplicates, gaps, and event comparisons came from the full stream. Quantiles alone are approximate. A targeted filtered read then checked LPS transitions within documented event minutes. Total profiling time, including SHA-256, was 664.28 seconds.

[Inference] This method avoids loading the approximately 1.6 GB file into RAM. Full-row duplicate counting is exact because the full pass first established nondecreasing timestamps; equal timestamps would therefore be contiguous, and the timestamp is part of every full row.

## File identity and provenance

[Raw dataset] The analyzed file identity is:

| Property | Value |
|---|---|
| Filename | `dataset_train.csv` |
| Bytes | 1,646,201,046 |
| Modified time (UTC) | 2026-08-23T17:23:53.582441+00:00 |
| SHA-256 | `3fd0788c1b8fb7753ac0a2047f487c87f59b8b36af2f5553e4990354ed86d168` |
| Checksum status | Locally computed only |

[Unknown/unsupported] No official checksum appears in either supplied PDF or the project specification. The locally computed SHA-256 must not be called an official checksum.

[Supplied paper] The source papers are `metropt-scientific-data-2022.pdf`, *The MetroPT dataset for predictive maintenance* (DOI 10.1038/s41597-022-01877-3), and `interpretable-online-failure-prediction-2026.pdf`, *Interpretable rules for online failure prediction: a case study on metro do porto datasets* (DOI 10.1007/s41060-026-01039-3).

[Project source] The project context is `docs/superpowers/specs/2026-08-23-industrial-reliability-intelligence-platform-design.md`. It selects MetroPT for leakage-safe, time-ordered anomaly-detection feasibility work but intentionally leaves final columns, event dates, and split boundaries open.

## Exact schema and type distinctions

[Raw dataset] The header has 21 columns in this exact order:

```text
timestamp, TP2, TP3, H1, DV_pressure, Reservoirs, Oil_temperature,
Flowmeter, Motor_current, COMP, DV_eletric, Towers, MPG, LPS,
Pressure_switch, Oil_level, Caudal_impulses, gpsLong, gpsLat,
gpsSpeed, gpsQuality
```

[Raw dataset] CSV itself stores text tokens and has no intrinsic data types. All 10,773,588 timestamp tokens matched `YYYY-MM-DD HH:MM:SS` and parsed at one-second resolution. All analog and coordinate tokens were decimal numeric lexemes and parsed as finite binary64-compatible numbers. `gpsSpeed`, all eight digital signals, and `gpsQuality` were integer lexemes and integer-compatible. No scientific-notation tokens occurred. This is observed/parser type evidence, not semantic typing.

[Supplied paper] Signal semantics and units come from the papers, not from numeric ranges. The CSV spellings `DV_eletric`, `Motor_current`, and `Oil_temperature` differ in capitalization/spelling from paper forms such as `DV_electric`, `Motor_Current`, and `Oil_Temperature`.

| Column | Semantic group | Observed token / parser type | Paper meaning | Unit |
|---|---|---|---|---|
| `timestamp` | Timestamp | Fixed text; validated second-resolution timestamp | Observation time | Not supplied |
| `TP2` | Analog continuous | Decimal; floating-point-compatible | Compressor pressure | bar |
| `TP3` | Analog continuous | Decimal; floating-point-compatible | Pneumatic-panel pressure | bar |
| `H1` | Analog continuous | Decimal; floating-point-compatible | Pressure associated with the command pressure switch | bar |
| `DV_pressure` | Analog continuous | Decimal; floating-point-compatible | Pressure drop associated with air-dryer discharge | bar |
| `Reservoirs` | Analog continuous | Decimal; floating-point-compatible | Train air-tank pressure | bar |
| `Oil_temperature` | Analog continuous | Decimal; floating-point-compatible | Compressor oil temperature | degrees Celsius |
| `Flowmeter` | Analog continuous | Decimal; floating-point-compatible | Pneumatic-panel airflow | m^3/h |
| `Motor_current` | Analog continuous | Decimal; floating-point-compatible | Compressor motor current | A |
| `COMP` | Digital binary | Integer; values 0/1 | Compressor air-intake valve electrical signal | None supplied |
| `DV_eletric` | Digital binary | Integer; values 0/1 | Compressor outlet-valve command | None supplied |
| `Towers` | Digital binary | Integer; values 0/1 | Active air-dryer tower selector | None supplied |
| `MPG` | Digital binary | Integer; values 0/1 | Command to start the compressor under load | None supplied |
| `LPS` | Digital binary | Integer; values 0/1 | Low-pressure warning signal | None supplied |
| `Pressure_switch` | Digital binary | Integer; observed only 0 | Pilot control-valve pressure signal | None supplied |
| `Oil_level` | Digital binary | Integer; values 0/1 | Low compressor-oil-level signal | None supplied |
| `Caudal_impulses` | Digital binary | Integer; values 0/1 | Flowmeter pulse indicating airflow | None supplied |
| `gpsLong` | Metadata/GPS continuous | Decimal; floating-point-compatible | Longitude | degree |
| `gpsLat` | Metadata/GPS continuous | Decimal; floating-point-compatible | Latitude | degree |
| `gpsSpeed` | Metadata/GPS continuous | Integer-compatible storage; semantically continuous | Train speed | km/h |
| `gpsQuality` | Metadata/GPS categorical | Integer; values 0/1 | GPS signal quality | None supplied |

## Rows, time order, cadence, gaps, and duplicates

[Raw dataset] Core facts are:

| Fact | Result |
|---|---:|
| Data rows | 10,773,588 |
| Well-formed 21-field rows | 10,773,588 |
| Malformed rows | 0 |
| Valid timestamps | 10,773,588 |
| Missing/unparseable timestamps | 0 / 0 |
| First and minimum timestamp | 2022-01-01 06:00:00 |
| Last and maximum timestamp | 2022-06-02 15:49:53 |
| Order | Strictly increasing |
| Duplicate timestamp groups / extra rows | 0 / 0 |
| Duplicate full-row groups / extra rows | 0 / 0 |
| Inclusive min-to-max time span | 13,168,194 seconds |

[Unknown/unsupported] The CSV and supplied papers provide no timezone or UTC offset. All comparisons therefore use naive timestamps exactly as locally stored, without claiming UTC or local civil time.

[Supplied paper] The 2022 paper reports 10,979,547 data points and a nominal acquisition rate of 1 Hz.

[Raw dataset] This file contains 205,959 fewer rows than the paper's reported count. Its observed modal consecutive delta is exactly 1 second for 10,773,435 of 10,773,587 deltas (99.998589%). There are 152 deltas greater than one second, implying 2,394,606 absent seconds across the observed min-to-max span.

[Unknown/unsupported] Local evidence does not establish why the row count differs from the paper. Possible source-version, export, or snapshot differences are hypotheses, not facts; the stable transfer and local checksum do not resolve provenance equivalence.

[Raw dataset] Gap distribution:

| Delta | Occurrences |
|---:|---:|
| 1 second | 10,773,435 |
| 1,055 seconds | 1 |
| 14,400 seconds (4 hours) | 147 |
| 19,839 seconds | 1 |
| 56,695 seconds | 1 |
| 63,369 seconds | 1 |
| 137,000 seconds | 1 |

[Raw dataset] The five largest non-routine gaps were 137,000 seconds (2022-03-04 01:32:01 to 2022-03-05 15:35:21), 63,369 seconds (2022-03-13 21:42:47 to 2022-03-14 15:18:56), 56,695 seconds (2022-03-23 19:30:25 to 2022-03-24 11:15:20), 19,839 seconds (2022-03-26 00:43:29 to 2022-03-26 06:14:08), and 1,055 seconds. The repeated 14,400-second pattern occurs 147 times.

[Inference] A 1 Hz modal cadence does not justify treating this as a complete regular grid. Windowing and resampling must explicitly reject, segment, or flag windows that cross gaps; silently interpolating four-hour and multi-hour gaps would manufacture telemetry.

## Missingness and obvious validity checks

[Raw dataset] Using empty fields plus case-insensitive `NA`, `N/A`, `NaN`, `null`, and `none`, there are zero missing cells. There are also zero numeric parse errors, zero non-finite numeric cells, zero binary values outside `{0,1}`, zero longitude values outside [-180, 180], zero latitude values outside [-90, 90], and zero negative `gpsSpeed` values.

[Supplied paper] The 2022 paper states that GPS coordinates are set to zero when satellite information is lost, such as in tunnels.

[Raw dataset] Both `gpsLong` and `gpsLat` equal zero in 5,304,018 rows, and neither coordinate is zero alone. `gpsQuality` also has 5,304,018 zero values as an aggregate count. These zeros are convention-defined unavailability, not ordinary numeric longitude/latitude and not empty CSV fields.

[Inference] Identical aggregate counts do not by themselves prove row-wise equivalence between zero coordinates and `gpsQuality=0`; that relationship should be verified before encoding a single shared missingness rule.

[Raw dataset] Negative analog readings are common: `TP2` 9,350,886; `TP3` 0; `H1` 1,353,281; `DV_pressure` 10,750,415; `Reservoirs` 0; `Oil_temperature` 0; `Flowmeter` 0; `Motor_current` 426,515. `gpsSpeed` reaches 323 km/h, while its approximate 99th percentile is 47 km/h.

[Unknown/unsupported] No authoritative sensor calibration ranges, clipping rules, or valid speed envelope are supplied. Negative analog values and the 323 km/h maximum are suspicious or convention-dependent observations, not proven invalid values. They require domain/calibration investigation rather than automatic deletion.

## Per-sensor statistics

[Raw dataset] Every continuous statistic below uses all 10,773,588 finite values for count, minimum, maximum, mean, population standard deviation, zero count, and negative count. Percentiles are approximate from the bounded deterministic 84,168-row sample.

| Sensor | Min | P01 | P25 | P50 | P75 | P99 | Max | Mean | Pop. SD | Zeros | Negative |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `TP2` | -0.030 | -0.020 | -0.008 | -0.008 | -0.006 | 10.436 | 10.876 | 1.152184 | 3.075296 | 10,203 | 9,350,886 |
| `TP3` | 0.006 | 7.994 | 8.484 | 8.986 | 9.492 | 10.114 | 10.408 | 8.974608 | 0.700696 | 0 | 0 |
| `H1` | -0.034 | -0.022 | 8.236 | 8.748 | 9.292 | 10.072 | 10.414 | 7.751421 | 3.051447 | 5,977 | 1,353,281 |
| `DV_pressure` | -0.038 | -0.034 | -0.032 | -0.028 | -0.026 | -0.016 | 8.326 | -0.024541 | 0.148657 | 207 | 10,750,415 |
| `Reservoirs` | 1.350 | 1.462 | 1.470 | 1.590 | 1.638 | 1.746 | 2.054 | 1.565051 | 0.090163 | 0 | 0 |
| `Oil_temperature` | 13.875 | 52.650 | 63.650 | 68.300 | 71.050 | 76.900 | 97.900 | 67.307205 | 5.383851 | 0 | 0 |
| `Flowmeter` | 18.834719 | 18.844063 | 19.012250 | 19.040281 | 19.255188 | 31.906625 | 43.072406 | 20.395153 | 3.743607 | 0 | 0 |
| `Motor_current` | -0.0125 | -0.0025 | 0.0025 | 3.7050 | 3.8375 | 6.0450 | 9.6850 | 2.383179 | 2.193381 | 1,080,894 | 426,515 |
| `gpsLong` | -9.13004 | -8.69212 | -8.65893 | -8.54266 | 0 | 0 | 0 | -4.384534 | 4.317794 | 5,304,018 | 5,469,570 |
| `gpsLat` | 0 | 0 | 0 | 41.1518 | 41.1882 | 41.2138 | 41.9490 | 20.911440 | 20.592542 | 5,304,018 | 0 |
| `gpsSpeed` | 0 | 0 | 0 | 0 | 0 | 47 | 323 | 4.913657 | 11.518219 | 8,505,390 | 0 |

[Raw dataset] Exact categorical/binary distributions are:

| Signal | Count 0 | Count 1 | Share 1 | Observation |
|---|---:|---:|---:|---|
| `COMP` | 1,401,723 | 9,371,865 | 86.989265% | Binary |
| `DV_eletric` | 9,371,797 | 1,401,791 | 13.011366% | Binary |
| `Towers` | 702,757 | 10,070,831 | 93.477038% | Binary |
| `MPG` | 1,401,729 | 9,371,859 | 86.989209% | Binary |
| `LPS` | 10,705,915 | 67,673 | 0.628138% | Rare positive warning state |
| `Pressure_switch` | 10,773,588 | 0 | 0% | Constant in this file |
| `Oil_level` | 10,773,585 | 3 | 0.00002785% | Extremely sparse positive state |
| `Caudal_impulses` | 10,757,547 | 16,041 | 0.148892% | Sparse pulse signal |
| `gpsQuality` | 5,304,018 | 5,469,570 | 50.768323% | Categorical metadata, not an APU digital sensor |

[Supplied paper] The papers describe eight analog sensors, eight binary APU signals, and four GPS fields. They also state that `COMP` and `MPG` have related behavior and that motor current is expected near distinct operating regimes, but those descriptions are semantic context rather than validated thresholds for this local file.

## Failure-window and timestamp cross-reference

[Supplied paper] The 2022 paper documents three maintenance-report failure intervals and example counts. The 2026 paper repeats their start/end minutes and adds LPS-warning minutes for Failures 1 and 3; it reports no LPS warning for Failure 2.

[Raw dataset + Supplied paper] Comparison method: paper times have minute precision. For exact equality, each documented minute was normalized to `:00` and compared with parsed second-resolution CSV timestamps. The full source minute (`:00` through `:59`) was also checked. Interval overlap and record counts were computed both closed `[start,end]` and half-open `[start,end)` after `:00` normalization. This distinguishes an exact second hit, a same-minute signal transition, and interval coverage.

| Failure | Paper interval | Dataset overlap | Exact `:00` start/end rows | Half-open rows | Closed rows | Missing second timestamps in closed interval | Paper `# Exs.` |
|---|---|---|---:|---:|---:|---:|---:|
| 1 - Air leak, clients | 2022-02-28 21:53 to 2022-03-01 02:00 | Yes | 1 / 1 | 14,820 | 14,821 | 0 | 14,820 |
| 2 - Air leak, air dryer | 2022-03-23 14:54 to 15:24 | Yes | 1 / 1 | 1,800 | 1,801 | 0 | 1,800 |
| 3 - Oil leak, compressor | 2022-05-30 12:00 to 2022-06-02 06:18 | Yes | 1 / 1 | 195,483 | 195,484 | 43,197 | 281,800 |

[Inference] Failures 1 and 2 reproduce the paper example counts exactly under a half-open endpoint convention. Failure 3 does not: its documented interval spans only 238,680 seconds before considering gaps, yet the table reports 281,800 examples; this exceeds the gap-free half-open duration by 43,120. The local file has a further 43,197 absent second timestamps in the normalized closed interval and 86,317 fewer half-open records than the paper count. The source evidence is internally inconsistent for Failure 3, so no corrected count or boundary is asserted.

[Raw dataset + Supplied paper] LPS minute checks:

| Documented point | Exact row at `:00` | LPS at `:00` | Rows in source minute | LPS 0 / 1 in minute | First LPS=1 in minute |
|---|---:|---:|---:|---:|---|
| Failure 1 LPS, 2022-02-28 22:50 | 1 | 0 | 60 | 43 / 17 | 2022-02-28 22:50:43 |
| Failure 3 LPS/end, 2022-06-02 06:18 | 1 | 0 | 60 | 33 / 27 | 2022-06-02 06:18:33 |

[Inference] The paper's minute-level LPS times agree with a transition somewhere in the named minute, but not with an exact `:00` activation. Treating them as exact second labels would introduce 43-second and 33-second boundary errors respectively.

[Raw dataset] Inside the normalized closed failure intervals, `LPS=1` occurs 11,358 times for Failure 1, zero times for Failure 2, and zero times for Failure 3 because the first Failure 3 LPS activation is at 06:18:33, after the normalized `06:18:00` endpoint.

[Supplied paper] The 2026 study explicitly excludes `LPS` from model training/testing, uses roughly one month of pre-failure data for training, constructs overlapping 30-minute windows with a 5-minute stride, and reports that its selected model detected only the first of the three MetroPT failures. These are study choices/results, not recommendations or reproduced model results from this investigation.

## ML and evaluation risks

[Raw dataset + Supplied paper] There are only three documented failure episodes: two air leaks and one oil leak. Converting their seconds into row labels would create many correlated positive rows without creating more independent events. Event/class scarcity therefore remains severe even though the file has over ten million rows.

[Inference] Random row splitting is invalid. Adjacent 1 Hz records, repeated machine cycles, and overlapping windows are strongly correlated; a random split would place near-identical observations and possibly the same failure episode in train and test. Time-ordered splits must also purge at least the full feature lookback across boundaries so overlapping windows cannot share raw observations.

[Inference] `LPS` is a built-in warning signal and should not be used as an ordinary predictor for a goal that is evaluated against or seeks to precede LPS activation. Doing so risks direct target leakage. Keep it as event/evaluation evidence until a different causal prediction question is explicitly defined.

[Inference] GPS fields can proxy route, tunnel, parking, time of operation, or maintenance location. They may improve a benchmark by learning operational context or event date/location rather than APU degradation. GPS zero sentinels also create semantic missingness despite zero syntactic nulls.

[Inference] The 152 sampling gaps make window availability nonuniform. Gap-crossing windows, implicit forward/back filling, or global interpolation can mix separate operating segments and leak future observations. Failure 3 is especially affected by repeated four-hour gaps.

[Inference] Thresholding or preprocessing from the whole file would leak future distributional information. Scaling, imputation rules, normal baselines, quantile thresholds, feature selection, and alert-policy tuning must be fit only on an earlier training/calibration period.

[Inference] `Pressure_switch` has no variance, `Oil_level` has only three positive samples, and `LPS` is rare. Standard scaling, correlation estimates, and supervised importance measures can be unstable or meaningless for these columns. Binary signals require state ratio, transition count, and time-since-transition features rather than analog summaries alone.

[Unknown/unsupported] Maintenance reports provide event intervals, not verified per-second causal labels or guaranteed physical root causes for every anomalous reading. Observed correlation near a failure cannot establish component causality.

## Initial retain, exclude, and investigate-further groups

[Inference] These are initial data-governance groups, not final feature selection and not date/split selection.

| Group | Columns | Rationale |
|---|---|---|
| Retain for initial signal analysis | `TP2`, `TP3`, `H1`, `DV_pressure`, `Reservoirs`, `Oil_temperature`, `Flowmeter`, `Motor_current`, `COMP`, `DV_eletric`, `Towers`, `MPG`, `Caudal_impulses` | Paper-supported APU measurements/states with observed variability; preserve analog vs digital treatment |
| Retain as time/index evidence, not a model feature by default | `timestamp` | Required for ordering, gap segmentation, causal windows, splits, and event evaluation |
| Exclude from initial predictive inputs but retain for evaluation | `LPS` | Built-in warning and documented evaluation reference; high leakage risk |
| Exclude from the first model matrix pending a reason to include | `Pressure_switch` | Constant zero in this file |
| Investigate before predictive use | `Oil_level` | Only three positive rows; verify acquisition semantics and event alignment |
| Investigate/fence as contextual metadata | `gpsLong`, `gpsLat`, `gpsSpeed`, `gpsQuality` | Route/location leakage risk, zero-sentinel semantics, and suspicious speed maximum |
| Investigate before filtering or clipping | Negative analog values and extreme tails in all analog/GPS columns | No authoritative valid ranges or calibration conventions supplied |

[Inference] All columns should remain preserved in the immutable raw layer even when excluded from an initial model matrix. Exclusion here means "do not feed directly into the first predictive model without resolving the stated risk," not deletion from source data.

## Limitations and unresolved items

[Unknown/unsupported] The official checksum, exact export/version relationship to the paper, timezone, authoritative sensor validity ranges, and reason for the 205,959-row paper/file difference are unavailable in supplied local evidence.

[Unknown/unsupported] The paper's Failure 3 example count cannot be reconciled with its own minute endpoints at 1 Hz or with this file. No alternative boundary is invented.

[Inference] Approximate quantiles are suitable for initial profiling but should not be reused as model thresholds. Any threshold, feature set, event labeling convention, or train/calibration/test dates require a separate leakage-safe design decision and measurement pass.

[Raw dataset] Machine-checkable provenance, exact counts, full-precision statistics, gap details, event checks, and uncertainty notes are in `docs/research/metropt-dataset-profile.json`; it contains no raw rows.
