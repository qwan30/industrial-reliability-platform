# Phase 1 Offline ML Feasibility

Verdict: **NOT FEASIBLE**
Selected model: `none`

| Model | Feasible | Events | False episodes/day | Time in alert | PR-AUC |
|---|---:|---:|---:|---:|---:|
| statistical | False | 1/3 | 2.8391471139263094 | 0.009791235334713596 | 0.034866718973693055 |
| isolation_forest | False | 1/3 | 0.0 | 0.0001725327812284334 | 0.12095097962149592 |
| autoencoder | False | 1/3 | 0.0 | 0.0006901311249137336 | 0.17192497392011236 |

Neither added-complexity model changed the feasibility outcome or improved event coverage over the statistical baseline: all three detected only one of three events. Isolation Forest and the autoencoder avoided false normal-exposure episodes, and the autoencoder had the highest window PR-AUC, but neither met the predeclared requirement to detect at least two events.

## Limitations

- authoritative license unknown
- local dataset and checksum are unofficial; official-release equivalence is unknown
- The source covers one APU only.
- Only three uncertain, minute-precision failure intervals are available for holdout evaluation.
- The local source has 152 timestamp gaps, and its timezone is unspecified.
- The paper and local file row counts disagree.
- Failure 2's paper interval contradicts local LPS evidence: no `LPS=1` occurs inside the closed local interval.
- Failure 3's paper count is inconsistent with its stated interval, and local coverage has 43,197 absent seconds.
- Train and calibration contain no documented failures, but they are not independently proven healthy.
- Anomaly scores are correlation evidence and do not establish physical root cause.
- This is offline feasibility evidence, not a production alerting system.
