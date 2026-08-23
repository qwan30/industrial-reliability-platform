# Research Readiness Review

## Review scope and evidence discipline

- [Project source] This review evaluates readiness to begin the dedicated **Phase 1 Offline ML Feasibility design**, not readiness to train models or implement production services. The governing design is `D:\projects\industrial-reliability-platform\docs\superpowers\specs\2026-08-23-industrial-reliability-intelligence-platform-design.md`, especially Sections 35 and 47-49 (lines 1735-1763 and 2298-2367).
- [Supplied paper] Both supplied PDFs were independently read page by page: `D:\projects\industrial-reliability-platform\docs\references\metropt-scientific-data-2022.pdf` (8 pages) and `D:\projects\industrial-reliability-platform\docs\references\interpretable-online-failure-prediction-2026.pdf` (13 pages).
- [Raw dataset] `D:\projects\industrial-reliability-platform\data\raw\metropt\dataset_train.csv` received a fresh SHA-256 pass followed by an independent, full, memory-bounded CSV pass using Python's standard library, one row at a time. The pass recomputed schema, types, row count, timestamps, cadence, gaps, nulls, numeric validity, extrema, binary counts, GPS sentinel relationships, and failure-window overlaps. It completed in 405.9 seconds and wrote no intermediate files.
- [Reference repository] The only repositories inspected were the three permitted local worktrees. Inspection used Git metadata and direct source reads; no dependencies, serialized artifacts, or workloads were executed.
- [Open/unknown] Poppler was unavailable, so PDF rendering and visual figure/layout inspection could not be performed. Complete page text and metadata were extracted with `pypdf`; figure captions, tables, and surrounding prose were checked, but graphical traces inside figures were not independently measured.
- [Open/unknown] No web source, official remote checksum, remote Git state, external dataset page, domain expert, or maintenance work order was consulted. Current upstream state and legal conclusions remain outside this review.

## Executive conclusion

[Inference] The evidence is sufficient to begin the exact design session required by master-spec Section 48. It is not sufficient to freeze the canonical dataset release, event contract, feature set, split dates, thresholds, or physical causal interpretations. The reports are generally careful and source-labeled; the main additions from independent review are an exact row-wise GPS-sentinel result and an explicit separation between a stable local file and an officially identified canonical release.

## 1. Source grounding

### Verified domain claims

| Claim | Review status | Primary local evidence |
|---|---|---|
| MetroPT records one train APU using eight analog channels, eight binary APU signals, and four GPS fields; acquisition is nominally 1 Hz and transmission is every five minutes. | [Supplied paper] **SUPPORTED.** The distinction between sampling and transmission cadence is correct. | `D:\projects\industrial-reliability-platform\docs\references\metropt-scientific-data-2022.pdf`, p. 2, Methods; p. 3, Data Records. Cross-report location: `docs\research\domain-knowledge-report.md`, lines 17-19 and 32-37. |
| The APU supports pneumatic functions and has no backup, so failure can remove the train from operation. | [Supplied paper] **SUPPORTED.** | `D:\projects\industrial-reliability-platform\docs\references\metropt-scientific-data-2022.pdf`, p. 1, Background & Summary; `D:\projects\industrial-reliability-platform\docs\references\interpretable-online-failure-prediction-2026.pdf`, p. 2, Section 2. |
| Analog/digital/GPS signal meanings and units used in the domain report. | [Supplied paper] **SUPPORTED WITH SOURCE AMBIGUITIES PRESERVED.** `H1` semantics and `COMP`/`MPG` polarity are not resolved by the paper; the report correctly labels them. | 2022 paper, pp. 2-3, Methods, Analog sensors, Digital sensors, GPS Information; `docs\research\domain-knowledge-report.md`, lines 51-81 and 186-200. |
| Three maintenance-reported failures exist: two air leaks and one oil leak. | [Supplied paper] **SUPPORTED.** The intervals are minute-precision annotations, not proven per-second degradation onsets. | 2022 paper, p. 5, Technical Validation, Figures 6-8 and Table 2; pp. 5-6 for narrative/evaluation context. |
| LPS is a built-in low-pressure warning and the 2026 study excludes it from training/testing. | [Supplied paper] **SUPPORTED.** Treating LPS as evaluation evidence rather than an early-warning predictor is a defensible project inference. | 2026 paper, pp. 2-4, Section 2 and Table 1; `docs\research\domain-knowledge-report.md`, lines 69 and 146-147. |
| The 2026 study uses overlapping 30-minute windows with five-minute stride, train-derived normalization, and detects only the first MetroPT failure under its selected configuration. | [Supplied paper] **SUPPORTED AS STUDY METHOD/RESULT, NOT PROJECT RESULT.** | 2026 paper, pp. 6-7, Section 5.1 and Table 2. |
| The first-failure rule `Oil_Temperature_max > 93.29` has 0.999 support in that study, but does not establish a universal physical threshold or cause. | [Supplied paper] **SUPPORTED WITH THE REPORT'S CAUSAL LIMIT.** | 2026 paper, pp. 7-8, Table 4; p. 10, Figure 5 and Section 5.3; p. 11, Section 6 limitations. |
| Event-level recall, lead time, false alarms, and persistence are more appropriate than random-row accuracy for this project. | [Project source] **ALIGNED.** This is a project design decision supported by sparse-event and temporal evidence, not a result reported by this review. | Master spec, Sections 13-16, lines 718-859; `docs\research\domain-knowledge-report.md`, lines 133-154. |

### Paper-to-paper and within-paper cautions

- [Cross-report comparison] The domain report's page and section citations are materially accurate. Both PDFs start on visible printed page 1, so no page offset was found.
- [Supplied paper] The 2022 Failure 2 narrative says large pressure drops provoked an LPS driver warning, while the 2026 paper says no LPS signal was present and Table 1 shows a dash. This is a genuine source contradiction, not a report error: 2022 paper p. 5, Failure 2 narrative, versus 2026 paper pp. 3-4, Section 2 and Table 1.
- [Supplied paper] The 2022 Failure 3 Table 2 count of 281,800 cannot fit the stated 2022-05-30 12:00 to 2022-06-02 06:18 interval at 1 Hz. The gap-free half-open duration is 238,680 seconds, 43,120 below the paper count. No corrected count or boundary is supported.
- [Supplied paper] The 2022 paper frames the operational need as detection at least two hours before non-operation (p. 6, Evaluation Protocol); the 2026 paper frames it as ideally two hours before LPS (pp. 2-3, Section 2). These related targets must not be silently treated as identical.
- [Supplied paper] The 2022 paper labels the dataset as having no missing values (p. 3, Data Records). [Raw dataset] The local CSV has no null/invalid cells but is not a complete 1 Hz grid. These statements can coexist only if "missing" means missing fields rather than missing timestamps.

## 2. Dataset correctness

### File identity, stability, and transfer-artifact exclusion

| Fact | Independent result |
|---|---|
| Stable analyzed path | [Raw dataset] `D:\projects\industrial-reliability-platform\data\raw\metropt\dataset_train.csv` |
| Size | [Raw dataset] 1,646,201,046 bytes |
| Local SHA-256 | [Raw dataset] `3fd0788c1b8fb7753ac0a2047f487c87f59b8b36af2f5553e4990354ed86d168` |
| Stability evidence | [Raw dataset] Size and nanosecond-resolution modification time were identical before hashing, after hashing, and after the complete CSV pass. |
| Transfer artifact | [Raw dataset] `D:\projects\industrial-reliability-platform\data\raw\metropt\dataset_train.csv.crdownload` exists separately at 368,560,536 bytes. Only its directory metadata was observed; it was not opened, hashed, or parsed. |
| Historical `.aria2` claim | [Open/unknown] `docs\research\metropt-dataset-investigation.md`, line 5 records an earlier `.aria2` control file and transfer-stability checks. That historical process state cannot be independently replayed now; the control file is no longer present. Current stability was independently established. |
| Official identity | [Open/unknown] The checksum is locally computed. Neither supplied PDF nor the master spec provides an official checksum that proves this file is the exact published artifact. |

[Cross-report comparison] The independent size and hash match `docs\research\metropt-dataset-investigation.md`, lines 11-23, and `docs\research\metropt-dataset-profile.json`, lines 16-18. The JSON parses successfully.

### Schema, storage types, and observed ranges

[Raw dataset] The full pass found exactly 21 columns in this order:

```text
timestamp, TP2, TP3, H1, DV_pressure, Reservoirs, Oil_temperature,
Flowmeter, Motor_current, COMP, DV_eletric, Towers, MPG, LPS,
Pressure_switch, Oil_level, Caudal_impulses, gpsLong, gpsLat,
gpsSpeed, gpsQuality
```

[Raw dataset] All timestamps match the 19-character second-resolution representation and parse successfully. All ten analog/coordinate columns parse as finite floats. The eight APU digital columns plus `gpsSpeed` and `gpsQuality` use integer lexemes; all eight APU digital columns contain only 0 or 1.

| Column/group | Independently recomputed range or distribution |
|---|---|
| `TP2` | [Raw dataset] -0.030 to 10.876; 9,350,886 negative values |
| `TP3` | [Raw dataset] 0.006 to 10.408 |
| `H1` | [Raw dataset] -0.034 to 10.414; 1,353,281 negative values |
| `DV_pressure` | [Raw dataset] -0.038 to 8.326; 10,750,415 negative values |
| `Reservoirs` | [Raw dataset] 1.350 to 2.054 |
| `Oil_temperature` | [Raw dataset] 13.875 to 97.900 |
| `Flowmeter` | [Raw dataset] 18.83471875 to 43.07240625 |
| `Motor_current` | [Raw dataset] -0.0125 to 9.685; 1,080,894 zeros and 426,515 negative values |
| Eight APU digital signals | [Raw dataset] Exact positive counts: `COMP` 9,371,865; `DV_eletric` 1,401,791; `Towers` 10,070,831; `MPG` 9,371,859; `LPS` 67,673; `Pressure_switch` 0; `Oil_level` 3; `Caudal_impulses` 16,041 |
| GPS | [Raw dataset] `gpsLong` -9.13004 to 0; `gpsLat` 0 to 41.949; `gpsSpeed` 0 to 323; `gpsQuality` 0/1 with 5,304,018 zeros and 5,469,570 ones |

[Cross-report comparison] All extrema and digital counts above match `docs\research\metropt-dataset-investigation.md`, lines 110-154, and the per-column objects in `docs\research\metropt-dataset-profile.json`. The independent pass did not recompute the report's means, population standard deviations, or sampled approximate quantiles; those values were checked for JSON/Markdown consistency only. This limitation does not affect the readiness verdict because no model threshold is being selected here.

### Rows, time coverage, cadence, nulls, and duplicates

| Check | Independent result |
|---|---|
| Data/well-formed rows | [Raw dataset] 10,773,588 / 10,773,588; malformed rows 0 |
| First/min timestamp | [Raw dataset] 2022-01-01 06:00:00 |
| Last/max timestamp | [Raw dataset] 2022-06-02 15:49:53 |
| Time zone | [Open/unknown] No time zone or UTC offset is present in the CSV or supplied papers. |
| Order and duplicates | [Raw dataset] Strictly increasing; 0 negative deltas and 0 zero deltas. Therefore timestamp duplicates are 0, and full-row duplicates are also 0 because timestamp is part of every row. |
| Inclusive endpoint span | [Raw dataset] 13,168,194 seconds |
| Modal cadence | [Raw dataset] Delta 1 second occurs 10,773,435 times out of 10,773,587 consecutive deltas (99.998589%). |
| Gaps | [Raw dataset] 152 deltas exceed one second: 147 x 14,400 seconds, and one each of 1,055, 19,839, 56,695, 63,369, and 137,000 seconds. These imply 2,394,606 absent timestamps. |
| Missing/invalid cells | [Raw dataset] 0 empty/NA-like cells, timestamp parse errors, numeric parse errors, non-finite values, or binary values outside `{0,1}`. |

[Cross-report comparison] These results match `docs\research\metropt-dataset-investigation.md`, lines 68-112, and JSON lines 859, 875-930, and 1043. The local file has 205,959 fewer rows than the paper's 10,979,547 count (2022 paper, p. 3, Data Records); the reason remains open.

### GPS sentinel relationship newly resolved

- [Cross-report comparison] `docs\research\metropt-dataset-investigation.md`, lines 116-118 correctly records equal aggregate zero counts but leaves row-wise equivalence open.
- [Raw dataset] The independent full pass explicitly checked every row and found **zero mismatches** among `gpsLong == 0`, `gpsLat == 0`, and `gpsQuality == 0`. In this file, those three conditions are row-wise equivalent.
- [Open/unknown] This observed equivalence does not establish that every future MetroPT release uses the same `gpsQuality` encoding, nor does it supply a semantic scale beyond the observed 0/1 values.

### Failure-window overlap and LPS timing

[Raw dataset] [Supplied paper] Paper times have minute precision. The independent comparison normalized each named minute to `:00`, counted both half-open `[start,end)` and closed `[start,end]` rows, and checked the full documented LPS minute.

| Failure | Paper interval/count | Half-open rows | Closed rows | Closed missing seconds | LPS evidence |
|---|---:|---:|---:|---:|---|
| 1, clients air leak | [Supplied paper] 2022-02-28 21:53 to 2022-03-01 02:00; 14,820 | [Raw dataset] 14,820 | [Raw dataset] 14,821 | [Raw dataset] 0 | [Raw dataset] First `LPS=1` at 22:50:43; the 22:50 minute contains 43 zeros and 17 ones. |
| 2, air-dryer leak | [Supplied paper] 2022-03-23 14:54 to 15:24; 1,800 | [Raw dataset] 1,800 | [Raw dataset] 1,801 | [Raw dataset] 0 | [Raw dataset] `LPS=1` count is 0 throughout the closed interval. This supports the 2026 table for the interval but cannot erase the contradictory 2022 narrative. |
| 3, compressor oil leak | [Supplied paper] 2022-05-30 12:00 to 2022-06-02 06:18; 281,800 | [Raw dataset] 195,483 | [Raw dataset] 195,484 | [Raw dataset] 43,197 | [Raw dataset] First `LPS=1` at 06:18:33, after the normalized `06:18:00` endpoint; the 06:18 minute contains 33 zeros and 27 ones. |

[Cross-report comparison] The independent results match `docs\research\metropt-dataset-investigation.md`, lines 158-183, and JSON lines 1090-1256. Failure 1 and 2 paper counts fit a half-open convention exactly. Failure 3 is internally inconsistent even before local gaps are considered; its paper count must not be used as a verified label count.

### Markdown/JSON reconciliation

- [Cross-report comparison] `docs\research\metropt-dataset-profile.json` parses as one JSON object and reconciles with the Markdown on file identity, schema, row counts, timestamps, ordering, gaps, hard-invalid counts, column extrema/counts, and all failure-window checks.
- [Cross-report comparison] The profile's approximate quantiles are explicitly sampled and the Markdown labels them approximate. No report presents them as model thresholds.
- [Cross-report comparison] No critical raw-data value independently recomputed in this review disagrees with the JSON or Markdown.
- [Cross-report comparison] The only material refinement is the row-wise GPS equivalence above, which the report deliberately left untested rather than stating incorrectly.

## 3. Reference repository accuracy and reuse risk

| Repository | Independently verified provenance and state | Local licensing evidence | Phase/classification and copied-code control |
|---|---|---|---|
| `D:\projects\industrial-reliability-platform\references\metroguard-ml` | [Reference repository] Origin `https://github.com/firathdr/metroguard-ml.git`; SHA `bd5e87fc3299f58e0125f399a938a0dea57c4874`; clean `main` tracking `origin/main`. | [Reference repository] `LICENSE:1-20` is MIT and requires the notice in copies/substantial portions; `pyproject.toml:11-12` identifies MIT. `DATA_CARD.md:3-13` and `data\README.md:1-23` state separate CC BY 4.0 data/replay licensing. | [Inference] **LEARN/ADAPT METHODOLOGY ONLY in Phase 1.** MIT permits reuse subject to its notice terms, but the master spec requires owned implementation. Do not copy its MetroPT-3 schema, dates, incidents, code, tests, artifacts, data extract, metrics, or prose. Never deserialize its committed `joblib` artifacts; `src\metroguard\artifacts.py:43-47` calls `joblib.load`. |
| `D:\projects\industrial-reliability-platform\references\iot-streaming-pipeline` | [Reference repository] Origin `https://github.com/krishna8399/iot-streaming-pipeline.git`; SHA `92271eb49c27c7938c02ec0333869e8ef0f6f715`; clean `main` tracking `origin/main`. | [Reference repository] No tracked `LICENSE`, `LICENCE`, `COPYING`, or `NOTICE`; `README.md:226-228` says all rights reserved. | [Inference] **IGNORE FOR PHASE 1; CONCEPT-ONLY LATER.** No copying of code/config/SQL/dashboard/diagram/prose. Source confirms synthetic/random anomaly injection (`producer\producer.py:101-152`), non-durable-looking `/tmp` checkpoints and `failOnDataLoss=false` (`spark\streaming_job.py:63,99-108,223-247`), and mutable `latest` images (`docker-compose.yml:169-223`). These are cautionary examples, not adopted design. |
| `D:\projects\industrial-reliability-platform\references\mlops-zoomcamp` | [Reference repository] Origin `https://github.com/DataTalksClub/mlops-zoomcamp.git`; SHA `3ba475fa5e2066ef566d6e452b5a76e1ecf7df41`; clean `main` tracking `origin/main`. | [Open/unknown] `git ls-files` found no tracked conventional license/notice file; the root README has no license section, and `06-best-practices\code\pyproject.toml:1-19` has no package license grant. No local explicit reuse permission was established. | [Inference] **CONCEPT-ONLY, MOSTLY LATER PHASES.** Do not copy notebooks, workflows, code, diagrams, prose, or infrastructure. The local tree itself documents tool drift (`02-experiment-tracking\README.md:52-53`; `05-monitoring\README.md:96-98`) and contains a misspelled CI working directory (`.github\workflows\ci-tests.yml:43-44`) plus auto-applied Terraform/mutable `latest` deployment (`.github\workflows\cd-deploy.yml:37-76`). |

[Cross-report comparison] Origins, SHAs, branch/worktree state, licensing evidence, classifications, and risks agree with `docs\research\github-reference-map.md`, lines 30-45, 84-102, 121-139, and 197-210. No copied reference code appears in any reviewed research deliverable.

## 4. Master-spec alignment and scope control

| Topic | Review finding |
|---|---|
| Dataset choice | [Project source] The reports use MetroPT 2022 as directed by Section 8.1 (lines 339-364) but correctly stop short of declaring the local file officially canonical because Section 47 items 1-3 remain open (lines 2298-2304). |
| Phase 1 question/model ladder | [Project source] Dataset inspection, temporal features, robust baseline, Isolation Forest, simple PyTorch autoencoder, and event-level evaluation match Sections 11-15 and Phase 1 (lines 600-859 and 1741-1763). [Cross-report comparison] No report claims a trained model or measured project metric. |
| Leakage | [Project source] Time-ordered train/calibration/holdout roles and train-only fitting match Section 14 (lines 759-805) and leakage tests in Section 37 (lines 1939-1949). [Inference] Exact dates and purge/window rules remain design decisions. |
| Data quality | [Project source] The dataset report's null, schema, duplicate, gap, type, and sentinel checks directly support Section 18 (lines 946-975) and Section 37 data tests (lines 1929-1937). |
| Reference use | [Project source] The reference map follows Sections 31-32 (lines 1490-1617): learn methodology, cite influence, and own contracts/implementation. The conservative no-copy control is compatible with, and safer than, the spec's license-conditional generic reuse language. |
| Later-phase systems | [Project source] Kafka/Spark are Phase 3, Airflow/MLflow are Phase 5, the LLM/RCA assistant is Phase 7, and OpenVINO is Phase 8 (lines 1783-1867). Section 22 also says Airflow is unnecessary in Phase 1 (lines 1134-1158). |
| Next step | [Project source] The reports provide the evidence needed for the dedicated Phase 1 design requested by Section 48 (lines 2322-2355); they do not replace that design or authorize implementation. |

### Conflicts or silent spec changes

- [Cross-report comparison] **No silent alteration of a chosen master-spec decision was found.** Recommendations are presented as inferences or open choices.
- [Cross-report comparison] The domain report proposes candidate feature interpretations, and the dataset report proposes retain/exclude/investigate groups, but both explicitly avoid freezing the final column set, dates, or thresholds. This is consistent with master-spec Section 47.
- [Open/unknown] The locally stable CSV is a strong Phase 1 candidate but does not yet satisfy the spec's still-open requirement for an exact canonical release/version and authoritative dataset license.
- [Inference] The raw Failure 2 LPS result can guide the design contract but cannot adjudicate which paper's narrative is historically correct outside the observed interval.

### Premature implementation check

- [Cross-report comparison] The three research reports introduce no Kafka, Spark, Airflow, MLflow infrastructure, OpenVINO path, LLM/RCA service, production API, or model training.
- [Cross-report comparison] `docs\research\github-reference-map.md`, line 26 explicitly prohibits those later-phase systems in Phase 1; lines 143-148 and 169-172 defer the relevant repository material.
- [Project source] Mentioning the statistical/Isolation Forest/autoencoder ladder as design scope is required by Phase 1; no workload was executed and no performance claim was made.

## 5. Contradiction and discrepancy register

| ID | Disagreement | Resolution/status |
|---|---|---|
| C1 | [Supplied paper] 10,979,547 data points (2022 paper p. 3) versus [Raw dataset] 10,773,588 rows. | [Open/unknown] The local file is 205,959 rows smaller. Use the verified local count for this artifact; do not claim publication-release equivalence until provenance is established. |
| C2 | [Supplied paper] Failure 3 has 281,800 examples, but its own minute endpoints allow only 238,680 gap-free half-open seconds. | [Open/unknown] The count is internally inconsistent by 43,120 even before local gaps. Preserve the published endpoints and count as separate source statements; freeze neither a correction nor label count. |
| C3 | [Supplied paper] Failure 2 narrative says LPS warned; the 2026 paper reports no LPS. | [Raw dataset] The local closed interval contains zero `LPS=1` rows, consistent with the 2026 table for that interval. [Open/unknown] The 2022 narrative may refer to activity outside the interval or another interpretation; historical truth is unresolved. |
| C4 | [Supplied paper] LPS times are minute-level `22:50` and `06:18`; treating them as exact `:00` seconds conflicts with raw transitions. | [Raw dataset] First activations are 22:50:43 and 06:18:33. [Inference] Preserve paper precision as minute buckets and use observed second timestamps only for this local file. |
| C5 | [Supplied paper] Nominal 1 Hz/no missing values versus [Raw dataset] 152 gaps and 2,394,606 absent timestamps. | [Inference] Reconcile "no missing values" as no empty cells, not complete regular coverage. Gap-crossing windows must be rejected, segmented, or explicitly represented. |
| C6 | [Supplied paper] `COMP` is active when off/offloaded, while `MPG` starts loaded compression and is said to activate `COMP` with the same behavior. | [Open/unknown] Polarity/control semantics are unresolved. Do not encode a mechanical state mapping from prose alone. |
| C7 | [Supplied paper] `H1` is classified analog, described as a valve condition above 10.2 bar, and assigned unit bar. | [Open/unknown] Treat as an observed analog column with paper-provided wording; do not freeze physical interpretation without authoritative schema/domain confirmation. |
| C8 | [Supplied paper] Early warning is anchored to non-operation in 2022 but to LPS in 2026. | [Open/unknown] Phase 1 must define event onset, warning horizon, accepted lead-time anchor, and reporting of both timestamps where present. |
| C9 | [Cross-report comparison] Dataset Markdown left row-wise GPS-sentinel equivalence unverified. | [Raw dataset] **RESOLVED FOR THIS FILE:** zero row-wise mismatches among zero longitude, zero latitude, and `gpsQuality=0`. Generalization remains open. |
| C10 | [Supplied paper] [Raw dataset] Source spellings/casing differ: for example `DV_electric`/`DV_eletric`, `Motor_Current`/`Motor_current`, and `Oil_Temperature`/`Oil_temperature`. | [Inference] Freeze a source-to-canonical mapping in the Phase 1 data contract; never rename without preserving provenance. |
| C11 | [Cross-report comparison] Domain report says the canonical file is not frozen; dataset report supplies a stable local identity. | [Inference] These statements are compatible: local identity is verified, official/canonical equivalence is not. |
| C12 | [Reference repository] MetroGuard is MIT with separate CC BY data; IoT says all rights reserved; Zoomcamp has no local explicit grant. | [Cross-report comparison] No licensing contradiction was found. Apply repository-specific controls; never infer one repository's license for another or for the MetroPT 2022 CSV. |

## 6. Evidence sufficiency and limitations

- [Inference] Sufficient now: local artifact identity, exact schema, full row/time quality profile, failure-window overlap facts, key domain semantics and uncertainties, leakage risks, reference provenance/licensing boundaries, and exact Phase 1 scope.
- [Open/unknown] Not supplied: official file checksum/release manifest, authoritative dataset license for this exact CSV, timezone, domain-approved signal truth table/ranges, corrected Failure 3 annotation, exact event-onset semantics, maintenance work orders, and cross-asset generalization evidence.
- [Open/unknown] Not independently recomputed: means, population standard deviations, and approximate quantiles. They reconcile between Markdown and JSON but should be recomputed within the eventual reproducible Phase 1 profiling command if used.
- [Open/unknown] PDF charts were not visually rendered because Poppler was unavailable; no claim in this review depends on estimating values from plotted graphics.
- [Inference] These limitations block freezing or implementation of several contracts, but they do not block the next dedicated design session whose purpose is to resolve those contracts.

## Readiness Verdict

READY WITH OPEN QUESTIONS

### Blockers

- [Inference] None block beginning the dedicated Phase 1 Offline ML Feasibility design.
- [Open/unknown] Model implementation/training must not begin as if the following were settled: canonical release/license, event/lead-time contract, temporal split, gap policy, feature schema, and holdout protocol.

### Important open questions

1. [Open/unknown] What official release/source manifest, license, and checksum make this exact local CSV canonical?
2. [Open/unknown] Which failure endpoints/counts are authoritative, especially Failure 3, and is lead time anchored to reported onset, LPS, or non-operation?
3. [Open/unknown] What are the authoritative meanings/polarities for `H1`, `COMP`, `MPG`, and the exact GPS-quality encoding?
4. [Open/unknown] Which columns, operating contexts, gap/coverage rules, causal windows, and train/calibration/holdout dates define Phase 1?
5. [Open/unknown] What event-matching, normal-exposure, threshold-calibration, uncertainty, and holdout-once rules will be locked before evaluation?

### Decisions now supported by evidence

- [Inference] Use the verified local CSV as the concrete candidate for the design session, identified by exact size and local SHA-256.
- [Inference] Preserve source timestamps as naive/unspecified time until authoritative timezone evidence exists; never label them UTC.
- [Inference] Require time-ordered, purged splitting; train-only preprocessing/model fitting; calibration-only threshold/policy selection; and untouched future holdout.
- [Inference] Make gaps/coverage and GPS sentinels explicit data-quality semantics; never silently interpolate gap-crossing windows.
- [Inference] Keep `LPS` out of initial predictive inputs and use it as evaluation evidence; keep GPS contextual and fenced until leakage value is justified.
- [Inference] Compare a robust statistical baseline, Isolation Forest, and the simplest justified PyTorch autoencoder with event-oriented metrics.
- [Inference] Use MetroGuard only as a methodological checklist; write independent requirements, code, tests, and documentation. Keep the IoT and Zoomcamp repositories out of Phase 1 implementation.

### Decisions that must NOT yet be frozen

- [Open/unknown] A corrected Failure 3 count/boundary, an exact second interpretation of paper minute timestamps, or a definitive Failure 2 LPS history.
- [Open/unknown] Physical healthy ranges, clipping rules, root cause, causal feature importance, or universal temperature/pressure thresholds.
- [Open/unknown] Exact sensor subset, window/stride, split dates, purge duration, feature formulas, threshold, persistence, cooldown, acceptance metric, or autoencoder architecture.
- [Project source] Kafka/Spark topology, online storage, API contract, Airflow/MLflow infrastructure, monitoring stack, LLM provider/RCA tools, and OpenVINO format remain later-phase decisions.

### Recommended next step

[Inference] Run the master-spec Section 48 Phase 1 design session. Start by freezing a versioned data/event contract that records the candidate CSV SHA-256, source-to-canonical column map, unspecified timezone, gap/coverage policy, minute-precision paper annotations plus observed LPS seconds, and unresolved Failure 3 count. Then define the causal features, purged train/calibration/holdout dates, baseline/Isolation Forest/simple-autoencoder comparison, calibration-only threshold, event metrics, leakage tests, and acceptance criteria. Produce the implementation plan only after that design is reviewed; do not train models or add later-phase infrastructure during this step.
