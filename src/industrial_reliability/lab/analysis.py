"""Process limit and data quality rules analysis engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from industrial_reliability.lab.contracts import (
    AlertKind,
    LabAlert,
    LabEvent,
    Observation,
    PortRef,
    Sensor,
)


@dataclass(slots=True)
class SensorAnalysisState:
    sensor_id: UUID
    high_violations: int = 0
    low_violations: int = 0
    normal_streak: int = 0
    bad_quality_streak: int = 0
    good_quality_streak: int = 0
    active_process_alert: LabAlert | None = None
    active_quality_alert: LabAlert | None = None
    recent_observations: list[Observation] = field(default_factory=list)


def evaluate_sensor_observation(
    obs: Observation,
    sensor: Sensor,
    state: SensorAnalysisState,
) -> tuple[list[LabAlert], list[LabEvent]]:
    """Evaluate observation against process limit boundaries and data quality rules."""
    emitted_alerts: list[LabAlert] = []
    emitted_events: list[LabEvent] = []

    # Maintain sliding window of up to 20 recent observations
    state.recent_observations.append(obs)
    if len(state.recent_observations) > 20:
        state.recent_observations.pop(0)

    # 1. Evaluate Data Quality
    if obs.quality in ("MISSING", "INVALID"):
        state.bad_quality_streak += 1
        state.good_quality_streak = 0

        # Freeze process normal streak during bad data
        state.normal_streak = 0

        if state.bad_quality_streak >= 2 and state.active_quality_alert is None:
            alert_kind: AlertKind = "MISSING" if obs.quality == "MISSING" else "INVALID"
            target_asset = (
                sensor.target.asset_id if isinstance(sensor.target, PortRef) else sensor.target
            )
            alert = LabAlert(
                alert_id=uuid4(),
                run_id=obs.run_id,
                asset_id=target_asset,
                sensor_id=sensor.sensor_id,
                origin="DATA_QUALITY",
                kind=alert_kind,
                state="OPEN",
                first_tick=obs.tick - 20,  # 2 samples window
                last_tick=obs.tick,
                resolved_tick=None,
                evidence_ids=(),
            )
            state.active_quality_alert = alert
            emitted_alerts.append(alert)
            emitted_events.append(
                LabEvent(
                    event_id=uuid4(),
                    run_id=obs.run_id,
                    sequence=0,
                    kind="ALERT",
                    tick=obs.tick,
                    payload=alert.model_dump(mode="json"),
                )
            )

        return emitted_alerts, emitted_events

    # If quality is GOOD:
    state.good_quality_streak += 1

    # Check resolution of active quality alert (3 consecutive GOOD)
    if state.active_quality_alert and state.good_quality_streak >= 3:
        resolved_alert = state.active_quality_alert.model_copy(
            update={
                "state": "RESOLVED",
                "last_tick": obs.tick,
                "resolved_tick": obs.tick,
            }
        )
        state.active_quality_alert = None
        state.bad_quality_streak = 0
        emitted_alerts.append(resolved_alert)
        emitted_events.append(
            LabEvent(
                event_id=uuid4(),
                run_id=obs.run_id,
                sequence=0,
                kind="ALERT",
                tick=obs.tick,
                payload=resolved_alert.model_dump(mode="json"),
            )
        )

    # 2. Evaluate Process Limits
    if obs.value is None:
        return emitted_alerts, emitted_events

    hysteresis = 10000.0 if sensor.kind == "PRESSURE" else 0.001

    is_above = sensor.alarm_high is not None and obs.value > sensor.alarm_high
    is_below = sensor.alarm_low is not None and obs.value < sensor.alarm_low

    if is_above:
        state.high_violations += 1
        state.low_violations = 0
        state.normal_streak = 0

        if state.high_violations >= 3 and state.active_process_alert is None:
            target_asset = (
                sensor.target.asset_id if isinstance(sensor.target, PortRef) else sensor.target
            )
            alert = LabAlert(
                alert_id=uuid4(),
                run_id=obs.run_id,
                asset_id=target_asset,
                sensor_id=sensor.sensor_id,
                origin="PROCESS_LIMIT",
                kind="ABOVE_LIMIT",
                state="OPEN",
                first_tick=obs.tick - 40,  # 3 consecutive samples
                last_tick=obs.tick,
                resolved_tick=None,
                evidence_ids=(),
            )
            state.active_process_alert = alert
            emitted_alerts.append(alert)
            emitted_events.append(
                LabEvent(
                    event_id=uuid4(),
                    run_id=obs.run_id,
                    sequence=0,
                    kind="ALERT",
                    tick=obs.tick,
                    payload=alert.model_dump(mode="json"),
                )
            )

    elif is_below:
        state.low_violations += 1
        state.high_violations = 0
        state.normal_streak = 0

        if state.low_violations >= 3 and state.active_process_alert is None:
            target_asset = (
                sensor.target.asset_id if isinstance(sensor.target, PortRef) else sensor.target
            )
            alert = LabAlert(
                alert_id=uuid4(),
                run_id=obs.run_id,
                asset_id=target_asset,
                sensor_id=sensor.sensor_id,
                origin="PROCESS_LIMIT",
                kind="BELOW_LIMIT",
                state="OPEN",
                first_tick=obs.tick - 40,
                last_tick=obs.tick,
                resolved_tick=None,
                evidence_ids=(),
            )
            state.active_process_alert = alert
            emitted_alerts.append(alert)
            emitted_events.append(
                LabEvent(
                    event_id=uuid4(),
                    run_id=obs.run_id,
                    sequence=0,
                    kind="ALERT",
                    tick=obs.tick,
                    payload=alert.model_dump(mode="json"),
                )
            )

    else:
        # Inside limits - check if comfortably inside hysteresis boundary
        is_safely_inside = True
        if sensor.alarm_high is not None and obs.value >= (sensor.alarm_high - hysteresis):
            is_safely_inside = False
        if sensor.alarm_low is not None and obs.value <= (sensor.alarm_low + hysteresis):
            is_safely_inside = False

        if is_safely_inside:
            state.normal_streak += 1
            state.high_violations = 0
            state.low_violations = 0

            # 5 consecutive normal samples resolve active process alert
            if state.active_process_alert and state.normal_streak >= 5:
                resolved_alert = state.active_process_alert.model_copy(
                    update={
                        "state": "RESOLVED",
                        "last_tick": obs.tick,
                        "resolved_tick": obs.tick,
                    }
                )
                state.active_process_alert = None
                emitted_alerts.append(resolved_alert)
                emitted_events.append(
                    LabEvent(
                        event_id=uuid4(),
                        run_id=obs.run_id,
                        sequence=0,
                        kind="ALERT",
                        tick=obs.tick,
                        payload=resolved_alert.model_dump(mode="json"),
                    )
                )

    return emitted_alerts, emitted_events
