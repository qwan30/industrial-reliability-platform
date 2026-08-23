# MetroPT Domain Knowledge for the Industrial Reliability Platform

## Evidence convention

- `[Supplied paper]` means the claim is explicit in one of the two PDFs supplied with this project.
- `[Project source]` means the claim is a chosen boundary or design decision in `2026-08-23-industrial-reliability-intelligence-platform-design.md`.
- `[Inference]` means the claim is a reasonable engineering interpretation of the supplied evidence, but the papers do not state it directly.
- `[Unknown/unsupported]` means the supplied material does not establish the claim, or contains an ambiguity that must not be silently resolved.
- `[Supplied paper]` Page-offset check: both PDFs begin at their visible printed page 1, and every PDF page label matches the printed page number. Citations below therefore use `PDF p. N / printed p. N`; there is no offset.

## Beginner glossary

| Term | Minimum useful meaning | Important boundary | Evidence |
|---|---|---|---|
| Sensor | A physical device that measures a property such as pressure, temperature, airflow, or electrical current. | The project receives the resulting data; it does not design or wire the sensor. | `[Project source]` Master design, sections 5-6. |
| Signal | A value or state produced by the monitored system and recorded over time. | A dataset column is a recorded representation of a signal, not the physical sensor itself. | `[Inference]` This distinction follows from the paper's separate descriptions of installed sensors and recorded variables. |
| Telemetry | Timestamped machine measurements or states automatically delivered to software. | MetroPT's acquisition system samples at 1 Hz and sends information to a remote server every five minutes over GSM; transmission cadence and measurement cadence are different. | `[Supplied paper]` `metropt-scientific-data-2022.pdf`, PDF/printed p. 2, Methods. `[Project source]` Master design, section 6. |
| Analog signal | In MetroPT, a magnitude-valued channel such as pressure, temperature, airflow, or current. | "Analog" here identifies the eight measured channels in the dataset; the project does not process raw electrical waveforms. | `[Supplied paper]` `metropt-scientific-data-2022.pdf`, PDF/printed p. 2, Methods - Analog sensors. `[Inference]` The software-boundary clarification is not stated by the paper. |
| Digital signal | In MetroPT, a binary channel: 0 when inactive and 1 when a specific event activates it. | A 0 is an inactive state, not automatically a missing value or a healthy state. | `[Supplied paper]` `metropt-scientific-data-2022.pdf`, PDF/printed pp. 2-3, Methods - Digital sensors. |
| Time series | Values ordered by their observation time. | Order is part of the information; random row splitting can leak nearby event behavior across train and test sets. | `[Project source]` Master design, sections 6 and 13-14. |
| Anomaly | A point or sequence that differs significantly from the behavior used as a reference for normality. | An anomaly is evidence of unusual behavior, not proof of failure or physical cause. | `[Supplied paper]` `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 3, section 3. `[Project source]` Master design, section 6. |
| Failure | For MetroPT evaluation, a maintenance-reported equipment malfunction represented as a start-end interval. | The three intervals are sparse post-hoc ground truth, not dense per-second diagnoses of every component. | `[Supplied paper]` `metropt-scientific-data-2022.pdf`, PDF/printed pp. 5-6, Technical Validation and Table 2. |
| Alert | An operational notification created when anomalous model output satisfies an alert policy. | A score above a threshold and an alert are different: persistence, merging, cooldown, and severity may sit between them. LPS is a separate built-in train warning signal. | `[Project source]` Master design, sections 10 and 16. `[Supplied paper]` `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 3, section 2. |
| Predictive maintenance | Use monitored condition data to predict developing failures and support maintenance before unplanned stoppage. | It can include failure prediction, component identification, RUL, and RCA, but this project selects anomaly detection and early warning as its flagship task. | `[Supplied paper]` `metropt-scientific-data-2022.pdf`, PDF/printed p. 1, Background & Summary; pp. 6-7, Evaluation Protocol. `[Project source]` Master design, sections 7 and 46. |
| Early-warning detection | Detect an abnormal/failure episode early enough to act before the train becomes non-operational or before its built-in warning. | The 2022 paper states an operational need for at least two hours before non-operation; the 2026 study frames its target as ideally two hours before LPS activates. These are related but not identical target definitions. | `[Supplied paper]` `metropt-scientific-data-2022.pdf`, PDF/printed p. 6, Evaluation Protocol; `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 2-3, section 2. |
| Root cause | The actual underlying physical reason an incident occurred. | A high anomaly score, a correlated sensor, or an interpretable rule does not by itself prove root cause. | `[Project source]` Master design, section 6. `[Supplied paper]` `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 11, section 6 limitations. |
| RCA | Root Cause Analysis: investigation of why an incident occurred. | The planned LLM performs evidence-grounded RCA assistance/anomaly explanation after an alert; it must not claim mechanical proof. | `[Project source]` Master design, sections 6 and 28-29. |
| RUL | Remaining Useful Life: an estimate of how long a component can continue operating before failure. | RUL is a separate prediction problem and is not the first-version flagship. The 2022 paper presents it as useful for deciding when to remove the train. | `[Supplied paper]` `metropt-scientific-data-2022.pdf`, PDF/printed pp. 6-7, Evaluation Protocol. `[Project source]` Master design, sections 6-7 and 40. |

## System overview

### What MetroPT monitors

- `[Supplied paper]` MetroPT monitors the Air Production Unit (APU) installed on the roof of an operating Metro do Porto train. The acquisition system records eight analog channels, eight binary digital signals, and four GPS variables. Source: `metropt-scientific-data-2022.pdf`, PDF/printed pp. 1-3, Background & Summary, Methods, and Data Records.
- `[Supplied paper]` The published MetroPT file covers January through June 2022, contains 10,979,547 points at 1 Hz, and describes 20 sensor/GPS variables with no missing values after no preprocessing. The train made an average of 26 trips per day. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 3, Data Records.
- `[Supplied paper]` The acquisition hardware sent information to a remote server every five minutes using GSM. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 2, Methods.
- `[Inference]` MetroPT therefore describes one instrumented APU over time, not a labeled fleet-wide population of independent machines. A model evaluation must respect this longitudinal structure.

### What the APU does

- `[Supplied paper]` In this dataset, APU means **Air Production Unit**, not a computer processor or a conventional auxiliary electrical power unit. It is the train's main unit for air-related tasks. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 1, Background & Summary; `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 2, section 2.
- `[Supplied paper]` The APU supplies pneumatic consumers. Explicit examples are the secondary suspension that maintains vehicle height despite passenger load, opening and closing doors, and raising or lowering the train at a station platform. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 1, Background & Summary; `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 2, section 2.
- `[Supplied paper]` The train has no backup APU; an APU failure can make the train unable to continue operation and require removal for repair. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 1, Background & Summary; `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 2, section 2.
- `[Inference]` Conceptually, the monitored machine converts electrical power into compressed air, conditions that air, stores it in reservoirs, and supplies it to pneumatic consumers. The papers support the components and signals behind this description, but do not provide a complete pneumatic schematic.

### Where this software project starts

- `[Project source]` The project starts at timestamped digital telemetry. Physical sensing, signal conditioning, PLCs, SCADA, wiring, and control actuation remain upstream and out of scope. Source: master design, section 5.
- `[Project source]` The software path is ingestion -> validation -> storage -> causal feature engineering -> ML scoring -> alert policy -> monitoring -> evidence-grounded explanation. Source: master design, sections 5, 10, 33, and 46.

## Sensor/signal table

`[Supplied paper]` The canonical meanings below come from `metropt-scientific-data-2022.pdf`, PDF/printed pp. 2-3, Methods - Analog sensors, Digital sensors, and GPS Information. The 2026 paper repeats the analog definitions and the COMP/LPS definitions on PDF/printed pp. 2-3, section 2.

| Group | Recorded name | Documented physical meaning | Minimum software interpretation | Evidence status |
|---|---|---|---|---|
| Analog | `TP2` | Pressure on the compressor, in bar. | Compare compressor-side pressure with other pressure and state channels; do not assign an unprovided healthy range. | Meaning `[Supplied paper]`; software use `[Inference]`. |
| Analog | `TP3` | Pressure generated at the pneumatic panel, in bar. | Represents pressure downstream at the pneumatic panel; its relationship to TP2 can be useful, but direction and expected differential are not documented. | Meaning `[Supplied paper]`; relationship `[Inference]` and `[Unknown/unsupported]`. |
| Analog | `H1` | Listed as a valve activated when the command pressure switch reads above the 10.2 bar operating pressure; the paper also lists the unit as bar. | Preserve this field as supplied, but do not decide whether it is a pressure measurement, valve-associated measurement, or state without schema/data validation. | Meaning `[Supplied paper]`; exact semantics `[Unknown/unsupported]`. |
| Analog | `DV_pressure` | Pressure associated with the drop produced when air-dryer towers discharge water; when it is zero, the compressor is working under load, in bar. | Zero has an operating-state meaning and must not be treated automatically as missing or invalid. | Meaning `[Supplied paper]`; feature caution `[Inference]`. |
| Analog | `Reservoirs` | Pressure inside the train's air tanks, in bar. | Tracks stored air available to pneumatic consumers; level and recovery behavior may be more useful than one fixed threshold. | Meaning `[Supplied paper]`; feature use `[Inference]`. |
| Analog | `Oil_Temperature` | Compressor oil temperature, in degrees C. | Use level, trend, extrema, and regime context; unusual temperature is evidence, not automatic proof of an oil leak. | Meaning `[Supplied paper]`; feature use and causal limit `[Inference]`. |
| Analog | `Flowmeter` | Airflow measured on the pneumatic control panel, in m^3/h. | Changes may reflect demand, compressor activity, or leakage; the supplied material does not uniquely identify which cause from flow alone. | Meaning `[Supplied paper]`; interpretation `[Inference]` and `[Unknown/unsupported]`. |
| Analog | `Motor_Current` | Compressor motor current: near 0 A when off, near 4 A when offloaded, and near 7 A under load. | This is a strong operating-state proxy; deviations should be interpreted relative to commanded state and compressor cycle. | Meaning `[Supplied paper]`; feature use `[Inference]`. |
| Digital | `COMP` | Electrical signal of the compressor air-intake valve; described as active when there is no air admission, meaning off or offloaded. | Treat it as a compressor-state signal, but resolve the contradiction with the MPG description before encoding 0/1 as loaded/offloaded. | Meaning `[Supplied paper]`; final polarity `[Unknown/unsupported]`. |
| Digital | `DV_electric` | Command to the compressor outlet valve; active means working under load, inactive means off or offloaded. | Can segment loaded versus non-loaded windows and cross-check `Motor_Current`. | Meaning `[Supplied paper]`; feature use `[Inference]`. |
| Digital | `TOWERS` | Selects the air-dryer tower: 0 means tower one working; 1 means tower two working while the other tower drains removed humidity. | Alternation is normal process context; a transition is not automatically an anomaly. | Meaning `[Supplied paper]`; anomaly caution `[Inference]`. |
| Digital | `MPG` | Activates the intake valve to start the compressor under load when APU pressure is below 8.2 bar; the paper says it consequently activates COMP and behaves like COMP. | Use as a pressure-demand/load-command signal only after resolving its documented conflict with the COMP polarity. | Meaning `[Supplied paper]`; polarity `[Unknown/unsupported]`. |
| Digital | `LPS` | Low-pressure signal activated below 7 bar. | It is a built-in driver warning and an evaluation landmark; for early-warning modeling it should not be an input that gives away the target. | Meaning and warning role `[Supplied paper]`; leakage policy `[Inference]`. |
| Digital | `Pressure_switch` | Activated when pressure is detected on the pilot control valve. | A pilot-control state that can contextualize valve/pressure behavior; exact expected sequencing is not documented. | Meaning `[Supplied paper]`; sequencing `[Unknown/unsupported]`. |
| Digital | `Oil_Level` | Active (1) when compressor oil is below expected values. | A low-oil flag, not a continuous oil measurement; 0 means the low-level condition is not active, not proof of no oil-system problem. | Meaning `[Supplied paper]`; caution `[Inference]`. |
| Digital | `Caudal_impulses` | Flowmeter pulse indicating the existence of airflow per second. | A binary flow-presence companion to the continuous `Flowmeter`; disagreement may be useful for data-quality checks, but expected agreement is not specified. | Meaning `[Supplied paper]`; cross-check `[Inference]` and `[Unknown/unsupported]`. |
| GPS | `gpsLong` | Longitude in degrees. | Provides operating/location context, not direct mechanical health. | Meaning `[Supplied paper]`; use `[Inference]`. |
| GPS | `gpsLat` | Latitude in degrees. | Provides operating/location context, including paper-defined parking polygons. | Meaning and parking use `[Supplied paper]`, PDF/printed pp. 3-4, Data Records and Table 1. |
| GPS | `gpsSpeed` | Train speed in km/h. | Separates stationary and moving regimes; a stationary APU pattern may differ from an in-service pattern. | Meaning `[Supplied paper]`; regime use `[Inference]`. |
| GPS | `gpsQuality` | GPS signal quality. | Use it to distinguish valid position from loss of satellite data; exact scale/encoding is not documented. | Meaning `[Supplied paper]`; exact encoding `[Unknown/unsupported]`. |

- `[Supplied paper]` When satellite information is lost in a tunnel, the acquisition system sets GPS information to 0. A zero GPS value is therefore an explicit loss-of-signal encoding, not a null. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 3, GPS Information and Data Records; Figure 5 caption on p. 5.
- `[Inference]` A timestamp is essential to each time-series record, but it is not one of the paper's 20 sensor/GPS variables. Treat it as event metadata rather than a sensor.
- `[Supplied paper]` Signal casing differs across the papers, for example `Oil_Temperature` in the 2022 paper and `Oil_temperature` in the 2026 paper. Source: the sensor lists cited above.
- `[Inference]` Normalize names in the software schema while retaining a source-to-canonical mapping so evidence remains traceable.

## Normal-operation explanation

### Explicitly supported facts

1. `[Supplied paper]` The APU is highly demanded throughout the day and supplies pneumatic consumers including suspension, doors, and vehicle-height functions. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 1, Background & Summary; `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 2, section 2.
2. `[Supplied paper]` A pressure-demand condition below 8.2 bar is associated with MPG commanding loaded compressor operation; `DV_electric` active also denotes loaded operation. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 3, Digital sensors.
3. `[Supplied paper]` Compressor current has three documented regimes: about 0 A off, 4 A offloaded, and 7 A loaded. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 2, Analog sensors.
4. `[Supplied paper]` The two dryer towers alternate drying and draining humidity; their discharge creates the pressure behavior measured by `DV_pressure`. Source: `metropt-scientific-data-2022.pdf`, PDF/printed pp. 2-3, Analog and Digital sensors.
5. `[Supplied paper]` `H1` is tied to pressure above 10.2 bar, and LPS activates below 7 bar. Source: `metropt-scientific-data-2022.pdf`, PDF/printed pp. 2-3, sensor lists.
6. `[Supplied paper]` Prior MetroPT work treated roughly 30 minutes as one entire APU cycle. The 2026 study therefore used overlapping 30-minute windows with a five-minute stride. Source: `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 6-7, sections 5.1 and discussion of the second air leak.

### Reasonable conceptual model

`[Inference]` The following is a defensible conceptual cycle, not a complete control diagram:

```text
pneumatic consumers use stored air
        -> reservoir/system pressure falls
        -> a demand/control condition calls for loaded compression
        -> loaded state appears in valve signals and about-7-A motor current
        -> compressor replenishes system/reservoir pressure
        -> compressor unloads or turns off at sufficient pressure
        -> dryer towers alternate drying and draining moisture
        -> cycle repeats as demand changes
```

- `[Inference]` "Normal" is therefore a recurring, state-dependent sequence, not one constant value per channel. A high or low value can be normal in one compressor phase and suspicious in another.
- `[Inference]` Useful interpretation compares coupled signals: command/state (`MPG`, `DV_electric`, `COMP`), response (`Motor_Current`, TP2/TP3, `Reservoirs`, `Flowmeter`), conditioning (`TOWERS`, `DV_pressure`), and context (GPS/speed).
- `[Unknown/unsupported]` The supplied sources do not provide a full piping schematic, controller truth table, exact valve timing, expected pressure gradients, or healthy range for every channel.

## Failure-event explanation

### Maintenance-reported MetroPT events

| Event | Maintenance interval | What the documented failure means | Documented observable behavior | Evidence |
|---|---|---|---|---|
| Failure 1 - Air leak on clients | 2022-02-28 21:53 to 2022-03-01 02:00; 14,820 samples. LPS activated at 22:50. | A pipe feeding pneumatic clients was blown/broken. The paper names examples as "breaks, suspension, etc." | Catastrophic air-pressure drop near 23:00; severe malfunction; train removed from operation. | `[Supplied paper]` `metropt-scientific-data-2022.pdf`, PDF/printed p. 5, Technical Validation, Figure 6, Table 2; LPS time from `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 3-4, Table 1. |
| Failure 2 - Air leak on air dryer | 2022-03-23 14:54 to 15:24; 1,800 samples. The 2026 Table 1 records no LPS activation, while the 2022 narrative says the pressure drops provoked an LPS driver warning. | Malfunction of the pneumatic pilot valve that opens drain pipes during compressor operation. | Large pressure drops between 12:00 and 14:00, compressor attempts to compensate, train continues operating, and behavior stabilizes after 15:00 when the pilot-valve pattern returns to normal. | Event and mechanism `[Supplied paper]`: `metropt-scientific-data-2022.pdf`, PDF/printed p. 5, Technical Validation, Figure 7, Table 2. LPS conflict `[Unknown/unsupported]`: compare that narrative with `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 3-4, section 2 and Table 1. |
| Failure 3 - Oil leak on compressor | 2022-05-30 12:00 to 2022-06-02 06:18; 281,800 samples. LPS activated at 06:18 on June 2. | Oil leakage severely damaged the compressor's engine; after the compressor became inoperable, air pressure dropped and the train was removed. The train had no driver-warning signal specifically related to oil. | Irregular oil-temperature patterns from the reported start and unusual air-system patterns. The authors suggest oil entering the air system or reduced compressor efficiency as possibilities, not confirmed causes. | `[Supplied paper]` `metropt-scientific-data-2022.pdf`, PDF/printed p. 5, Technical Validation, Figure 8, Table 2; LPS time from `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 4, Table 1. |

### Interpretation limits and lessons

- `[Supplied paper]` Ground truth comes from company maintenance reports. The failure labels are intervals used for validation. Source: `metropt-scientific-data-2022.pdf`, PDF/printed pp. 1, 5-6, Background & Summary and Technical Validation.
- `[Inference]` The maintenance interval should not automatically be treated as the exact first instant of physical degradation. Reported start, first observable anomaly, first model warning, LPS activation, loss of operation, and repair time can be different timestamps.
- `[Supplied paper]` In the 2026 experiment's chosen configuration, the model detected only the first of the three MetroPT failures and produced no false-positive failure intervals; it did not meet the two-hour objective for that event. Source: `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 6-7, section 5.1 and Table 2.
- `[Supplied paper]` The same study suggests the second failure's 30-minute duration conflicted with its 30-minute input window and notes the absence of an LPS signal. This is the authors' hypothesis, not a proven mechanical explanation. Source: `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 7, section 5.1.
- `[Supplied paper]` For the detected first air leak, a rule using `Oil_Temperature_max > 93.29` over a 30-minute window covered 99.9% of the failure interval in that study. The authors observed high temperature deviations during the error. Source: `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 7-8 and 10, sections 5.2-5.3, Table 4, Figure 5.
- `[Inference]` That rule is a discriminative correlation for a particular data split and method. It does not establish that high oil temperature caused the air leak, nor that 93.29 degrees C is a universal physical failure limit.
- `[Supplied paper]` The 2026 paper explicitly says multiple thresholds could fit the data and that its rules cannot confidently identify physical breaking points. Source: `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 11, section 6.

## Domain facts essential for feature engineering and anomaly interpretation

1. `[Supplied paper]` **Keep event time causal.** Samples arrive at 1 Hz, while the installed system transmits every five minutes. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 2, Methods.
2. `[Project source]` **Split by time, not random rows.** Fit scalers, baselines, and models on past training data; calibrate thresholds later; preserve the final future period for holdout evaluation. Source: master design, sections 13-14.
3. `[Inference]` **Model operating regimes.** Motor current, load commands, dryer-tower state, pressure, flow, and reservoir behavior are coupled. A regime-conditioned deviation is more defensible than a global per-column threshold.
4. `[Supplied paper]` **Use temporal windows.** A published MetroPT pipeline used 30-minute windows, five-minute stride, and train-only channel normalization; its explanation layer aggregated mean, minimum, maximum, and variance. Source: `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 5-6, sections 4.2 and 5.1.
5. `[Inference]` **Treat 30 minutes as a precedent, not a fixed requirement.** The short air-dryer event shows that a window as long as an event can blur or delay detection. Evaluate multiple causal window lengths and report latency effects.
6. `[Supplied paper]` **Preserve units and named operating landmarks.** Pressure is in bar, oil temperature in degrees C, flow in m^3/h, motor current in A, speed in km/h; documented landmarks include 8.2 bar for MPG, 10.2 bar for H1, below 7 bar for LPS, and current regimes near 0/4/7 A. Source: `metropt-scientific-data-2022.pdf`, PDF/printed pp. 2-3, sensor lists.
7. `[Inference]` **Do not convert documented landmarks into universal anomaly thresholds.** They describe controls/warnings or expected modes; the supplied sources do not certify them as model thresholds or safe operating limits.
8. `[Supplied paper]` **Treat binary transitions as behavior.** MetroPT's digital channels are 0/1 event states, and tower switching is a normal alternating function. Source: `metropt-scientific-data-2022.pdf`, PDF/printed pp. 2-3, Digital sensors.
9. `[Inference]` **Feature digital signals differently from analog signals.** Useful digital-window summaries include active ratio, transition count, last state, and time since transition; analog windows can use level, extrema, dispersion, slope, and cross-signal differences. These are project candidates, not paper-certified best features.
10. `[Supplied paper]` **Handle GPS zeros as a sentinel.** Satellite loss in tunnels is encoded as 0, despite the dataset reporting no missing values. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 3, GPS Information and Data Records; Figure 5 caption on p. 5.
11. `[Inference]` **Separate operating context from machine health.** Speed, parking location, and GPS quality can explain regime changes. Loss of GPS should be classified as telemetry context, not an APU fault.
12. `[Supplied paper]` **Protect against target leakage from LPS.** LPS is the train's built-in low-pressure warning; the 2026 study excluded it from both training and testing and evaluated whether failures could be detected before it. Source: `interpretable-online-failure-prediction-2026.pdf`, PDF/printed p. 3, section 2.
13. `[Inference]` **Keep LPS as evaluation evidence, not an early-warning feature.** Feeding it into a model whose goal is to warn before LPS would make the task circular.
14. `[Supplied paper]` **Ground truth is event-level and scarce.** The six-month MetroPT dataset has three maintenance-reported catastrophic failures: two air leaks and one oil leak. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 5, Technical Validation and Table 2.
15. `[Project source]` **Evaluate operationally.** Report detected events, lead time, false alarms per day, PR-AUC, and time in alert; do not hide three events behind row-level accuracy. Source: master design, section 15.
16. `[Supplied paper]` **Demand persistence before declaring failure.** The 2026 method smoothed binary anomaly decisions and declared failure only when prolonged anomalous output crossed a second threshold. Source: `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 4-5, section 4.1.
17. `[Project source]` **Separate score from alert policy.** A model score, anomaly decision, alert episode, and maintenance failure are different objects with different timestamps and provenance. Source: master design, sections 10 and 16.
18. `[Supplied paper]` **Use explanations as correlations.** The 2026 study found time-aggregated rules more interpretable and better supported than per-second rules, but also documented non-unique thresholds and limited cross-setting validation. Source: `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 10-11, sections 5.3-6.
19. `[Inference]` **Cross-check commands and responses.** Examples include `DV_electric` versus `Motor_Current`, `MPG` versus pressure, and `Caudal_impulses` versus `Flowmeter`. Persistent disagreement can represent process anomaly, sensor fault, bad telemetry, or misunderstood semantics; the supplied papers do not disambiguate those cases.
20. `[Project source]` **Keep machine anomaly separate from data-quality anomaly.** Invalid schema, missing sensors, duplicate timestamps, gaps, and malformed records need their own validation path. Source: master design, section 18.

## What I need to know for interviews

### A defensible 30-second explanation

`[Project source]` "MetroPT is longitudinal 1 Hz telemetry from a roof-mounted Air Production Unit on a Metro do Porto train. The APU supplies compressed air to critical pneumatic functions and has no backup. My project starts after acquisition: it validates timestamped telemetry, builds causal window features, learns normal operating behavior, scores anomalies, applies an alert policy, and lets an RCA assistant explain only the structured evidence behind an alert." Source: master design, sections 1, 5, 10, 26, and 28. `[Supplied paper]` Physical-system facts: `metropt-scientific-data-2022.pdf`, PDF/printed pp. 1-3.

### Questions I should answer cleanly

- `[Supplied paper]` **What is being monitored?** One train's APU, with eight analog channels, eight binary digital signals, and GPS context at 1 Hz. Source: `metropt-scientific-data-2022.pdf`, PDF/printed pp. 2-3.
- `[Supplied paper]` **Why does it matter?** The APU serves critical air-related functions and has no redundant unit, so failure can remove the train from operation. Source: both supplied papers, PDF/printed pp. 1-2.
- `[Project source]` **Why anomaly detection instead of supervised failure classification?** Only three real MetroPT failure episodes exist, and neighboring one-second rows from one episode are not independent labels; learning normal behavior supports a more defensible leakage-safe evaluation. Source: master design, sections 12-14.
- `[Supplied paper]` **What is the most important domain modeling idea?** Normal behavior is cyclic and state-dependent: compressor load state, current, pressures, flow, reservoirs, dryer tower, and train context must be interpreted together. The component/state facts come from `metropt-scientific-data-2022.pdf`, PDF/printed pp. 2-3. The combined modeling statement is `[Inference]`.
- `[Project source]` **Anomaly, failure, and alert - are they the same?** No. An anomaly is model evidence, a failure is a maintenance-reported malfunction interval, and an alert is an operational policy outcome. Source: master design, sections 6 and 16.
- `[Supplied paper]` **What are the known failures?** A broken client-air pipe, an air-dryer pilot-valve/drain malfunction, and a compressor oil leak with subsequent compressor damage and pressure loss. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 5, Technical Validation and Table 2.
- `[Supplied paper]` **What is the early-warning target?** The operator requested detection at least two hours before non-operation; later work operationalized this as ideally before LPS by about two hours. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 6; `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 2-3.
- `[Inference]` **Why can I not call a top signal the root cause?** A signal can correlate with an event because it is a cause, an effect, a control response, operating context, or a sensor artifact. Establishing physical causality requires evidence beyond the supplied telemetry and model explanation.
- `[Project source]` **What does the LLM do?** It investigates an existing alert through deterministic tools and summarizes measurements, model provenance, contributions, state transitions, and nearby known events. It does not make the primary anomaly decision. Source: master design, sections 26 and 28-29.
- `[Project source]` **How is success measured?** With temporal holdout evidence and event-oriented measures such as detected-event count, lead time, false alarms/day, PR-AUC, and time in alert. Source: master design, sections 14-15.
- `[Supplied paper]` **What limitation should I volunteer?** The dataset has only three documented MetroPT failures, a 2026 method detected only one under its selected configuration, and interpretable thresholds were not unique physical breaking points. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 5; `interpretable-online-failure-prediction-2026.pdf`, PDF/printed pp. 7 and 11.

## What I do NOT need to learn

- `[Project source]` Detailed sensor electronics, transducer selection, calibration circuitry, wiring, PLC programming, SCADA configuration, and signal-conditioning design are outside the software boundary. Source: master design, sections 5 and 40.
- `[Project source]` Compressor repair procedures, pneumatic-component design, full railway maintenance certification, and control-system actuation are not required to build the first software platform. Source: master design, section 40.
- `[Project source]` The detailed requirements of every railway EN/IEC standard listed by the 2022 paper are not required for this non-safety-critical portfolio implementation. The project explicitly excludes safety-critical deployment and automatic stopping of machinery. Source: master design, section 40.
- `[Project source]` A complete physical digital twin, fluid-dynamics simulation, or first-principles thermodynamic model is not part of the chosen anomaly-detection scope. Source: master design, sections 7 and 40.
- `[Project source]` RUL regression and its degradation-physics literature are not required for the flagship version. RUL may be revisited only as a separate later task. Source: master design, sections 7, 9, 40, and 46.
- `[Project source]` A full mechanical RCA knowledge base is not required. The assistant's honest role is evidence-grounded anomaly explanation and investigation support. Source: master design, sections 28-29 and 40-41.
- `[Inference]` I do need enough domain vocabulary to avoid obvious category errors: do not call GPS loss an APU failure, do not call an inactive binary state missing data, do not treat all zeros alike, and do not claim a correlated temperature threshold proves an air leak.

## Open questions / uncertainties

1. `[Unknown/unsupported]` **Canonical raw schema:** The master design has not frozen the exact MetroPT file/version or exact Phase 1 column set. Confirm the downloaded artifact, checksum, column names, types, timestamp timezone, and ordering before feature design. Source of uncertainty: master design, section 47, questions 1-3.
2. `[Unknown/unsupported]` **`H1` semantics:** The 2022 paper classifies it as analog, describes a valve activated above 10.2 bar, and gives the unit bar. The supplied sources do not resolve whether the column is pressure, valve-associated pressure, or another measurement. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 2, Analog sensors.
3. `[Unknown/unsupported]` **`COMP` versus `MPG` polarity:** `COMP` is described as active with no intake air/offloaded operation, while `MPG` is described as starting loaded operation below 8.2 bar and consequently activating COMP with the same behavior. These statements appear inconsistent. Source: `metropt-scientific-data-2022.pdf`, PDF/printed p. 3, Digital sensors.
4. `[Unknown/unsupported]` **Exact pneumatic topology:** The papers name components and signals but do not provide a complete, readable piping/control schematic or exact upstream/downstream relationships for TP2, TP3, H1, `DV_pressure`, and `Reservoirs`.
5. `[Unknown/unsupported]` **Healthy ranges:** Apart from the documented control/warning landmarks and motor-current modes, no validated healthy range by operating regime is supplied. These ranges must be learned from training data or supplied by a domain expert, not invented.
6. `[Unknown/unsupported]` **Failure interval semantics:** The papers do not fully define whether each start time is first physical degradation, first visible telemetry anomaly, operator observation, report timestamp, or retrospective annotation boundary.
7. `[Unknown/unsupported]` **Early-warning anchor:** The 2022 paper says two hours before non-operation, while the 2026 paper evaluates relative to LPS. Phase 1 must freeze one event/lead-time contract and report both timestamps when available.
8. `[Unknown/unsupported]` **Failure 2 LPS record:** The 2022 failure narrative says the large pressure drops provoked an LPS driver warning, but the 2026 paper says no LPS signal was present and Table 1 shows a dash. Preserve both source statements until the raw signal is checked.
9. `[Unknown/unsupported]` **"Clients" wording:** The failure description says the leaking pipe fed "breaks, suspension, etc." The supplied PDF does not clarify whether "breaks" is a typographical reference to train brakes. Do not silently rewrite the maintenance diagnosis.
10. `[Unknown/unsupported]` **GPS quality encoding:** The existence of `gpsQuality` and zeroing on satellite loss is documented, but its numeric scale and exact relationship to each zeroed GPS field are not.
11. `[Unknown/unsupported]` **Oil leak onset and causal chain:** Irregular oil temperature and air-system patterns are documented, but the suggestions that oil entered the air system or efficiency fell are not confirmed physical RCA.
12. `[Unknown/unsupported]` **Generalization:** The supplied data concerns one MetroPT recording context with three events. Performance, thresholds, and explanations are not established for other trains, APUs, seasons, or industrial assets.
13. `[Unknown/unsupported]` **Maintenance validation:** The supplied materials do not include work orders, inspection photos, replaced-part records, or technician confirmation needed to validate model-generated RCA claims beyond the three paper narratives.

## Source boundary

- `[Supplied paper]` `metropt-scientific-data-2022.pdf` was used for the physical system, sensor definitions, dataset record, documented failures, and evaluation protocol.
- `[Supplied paper]` `interpretable-online-failure-prediction-2026.pdf` was used for the later failure-prediction framing, windowing precedent, experimental findings, explanation rules, and limitations.
- `[Project source]` `2026-08-23-industrial-reliability-intelligence-platform-design.md` was used only for this project's scope, architecture, terminology boundaries, evaluation choices, and non-goals.
- `[Unknown/unsupported]` No web sources, external domain references, raw dataset inspection, or mechanical expert testimony were used in this report.
