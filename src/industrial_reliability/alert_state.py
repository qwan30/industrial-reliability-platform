"""Pure deterministic alert state machine for Phase 5."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from industrial_reliability.alert_policy import LockedAlertPolicyV1
from industrial_reliability.runtime_messages import (
    AlertAction,
    AlertEventV1,
    EvidenceSnapshotV1,
    FeatureDeviationV1,
    ScoreDecisionV1,
)

ALERT_NAMESPACE = NAMESPACE_URL


class OrderingViolationError(ValueError):
    """Raised when decisions arrive out of chronological order."""


@dataclass(frozen=True, slots=True)
class AlertState:
    replay_session_id: UUID
    machine_id: str
    active_alert_id: UUID | None
    previous_alert_id: UUID | None
    first_detection: datetime | None
    last_detection: datetime | None
    resolved_at: datetime | None
    anomaly_decision_ids: tuple[UUID, ...]
    anomaly_streak: int
    normal_streak: int
    last_decision_id: UUID | None
    last_source_timestamp: datetime | None

    @classmethod
    def empty(cls, replay_session_id: UUID, machine_id: str = "metropt3") -> AlertState:
        return cls(
            replay_session_id=replay_session_id,
            machine_id=machine_id,
            active_alert_id=None,
            previous_alert_id=None,
            first_detection=None,
            last_detection=None,
            resolved_at=None,
            anomaly_decision_ids=(),
            anomaly_streak=0,
            normal_streak=0,
            last_decision_id=None,
            last_source_timestamp=None,
        )


@dataclass(frozen=True, slots=True)
class TransitionResult:
    state: AlertState
    event: AlertEventV1 | None
    evidence: EvidenceSnapshotV1 | None


def alert_id_for(replay_session_id: UUID, first_decision_id: UUID) -> UUID:
    return uuid5(ALERT_NAMESPACE, f"alert:{replay_session_id}:{first_decision_id}")


def evidence_id_for(alert_id: UUID, decision_id: UUID) -> UUID:
    return uuid5(ALERT_NAMESPACE, f"evidence:{alert_id}:{decision_id}")


def _build_evidence_snapshot(
    alert_id: UUID,
    decision: ScoreDecisionV1,
) -> EvidenceSnapshotV1:
    evidence_id = evidence_id_for(alert_id, decision.decision_id)
    deviations = [
        FeatureDeviationV1(
            feature_name=ev.feature_name,
            observed_value=ev.feature_value,
            baseline_value=ev.feature_value - ev.robust_deviation,
            absolute_deviation=abs(ev.robust_deviation),
        )
        for ev in decision.evidence_vector
    ]
    return EvidenceSnapshotV1(
        schema_version="evidence-snapshot-v1",
        message_id=uuid4(),
        replay_session_id=decision.replay_session_id,
        source_dataset_sha256=decision.source_dataset_sha256,
        contract_sha256=decision.contract_sha256,
        source_timestamp=decision.source_timestamp,
        emitted_at=datetime.now(UTC),
        evidence_id=evidence_id,
        alert_id=alert_id,
        decision_id=decision.decision_id,
        window_id=decision.window_id,
        model_version=decision.model_version,
        feature_deviations=tuple(deviations),
        data_quality={"status": "ok"},
        model={"score": decision.score, "threshold": decision.threshold},
        system_health={"is_anomaly": decision.is_anomaly},
    )


def _emit_anomaly_result(
    state: AlertState,
    decision: ScoreDecisionV1,
    policy: LockedAlertPolicyV1,
    action: AlertAction,
    alert_id: UUID,
    first_det: datetime,
    new_anomaly_streak: int,
    new_anomaly_decision_ids: tuple[UUID, ...],
) -> TransitionResult:
    last_det = decision.source_timestamp
    event = AlertEventV1(
        schema_version="alert-event-v1",
        message_id=uuid4(),
        replay_session_id=decision.replay_session_id,
        source_dataset_sha256=decision.source_dataset_sha256,
        contract_sha256=decision.contract_sha256,
        source_timestamp=decision.source_timestamp,
        emitted_at=datetime.now(UTC),
        alert_id=alert_id,
        machine_id=state.machine_id,
        action=action,
        first_detection=first_det,
        last_detection=last_det,
        decision_ids=new_anomaly_decision_ids,
        policy_sha256=policy.policy_sha256,
    )
    evidence = _build_evidence_snapshot(alert_id, decision)
    new_state = AlertState(
        replay_session_id=state.replay_session_id,
        machine_id=state.machine_id,
        active_alert_id=alert_id,
        previous_alert_id=state.previous_alert_id,
        first_detection=first_det,
        last_detection=last_det,
        resolved_at=None,
        anomaly_decision_ids=new_anomaly_decision_ids,
        anomaly_streak=new_anomaly_streak,
        normal_streak=0,
        last_decision_id=decision.decision_id,
        last_source_timestamp=decision.source_timestamp,
    )
    return TransitionResult(state=new_state, event=event, evidence=evidence)


def _handle_anomaly_trigger(
    state: AlertState,
    decision: ScoreDecisionV1,
    policy: LockedAlertPolicyV1,
    new_anomaly_streak: int,
    new_anomaly_decision_ids: tuple[UUID, ...],
) -> TransitionResult:
    if new_anomaly_streak < policy.persistence_decisions:
        new_state = AlertState(
            replay_session_id=state.replay_session_id,
            machine_id=state.machine_id,
            active_alert_id=None,
            previous_alert_id=state.previous_alert_id,
            first_detection=state.first_detection,
            last_detection=state.last_detection,
            resolved_at=state.resolved_at,
            anomaly_decision_ids=new_anomaly_decision_ids,
            anomaly_streak=new_anomaly_streak,
            normal_streak=0,
            last_decision_id=decision.decision_id,
            last_source_timestamp=decision.source_timestamp,
        )
        return TransitionResult(state=new_state, event=None, evidence=None)

    is_reopen = (
        state.previous_alert_id is not None
        and state.resolved_at is not None
        and policy.merge_gap_seconds > 0
        and (decision.source_timestamp - state.resolved_at).total_seconds()
        <= policy.merge_gap_seconds
    )
    action: AlertAction = "REOPENED" if is_reopen else "OPENED"
    alert_id = (
        state.previous_alert_id
        if is_reopen and state.previous_alert_id is not None
        else alert_id_for(decision.replay_session_id, new_anomaly_decision_ids[0])
    )
    first_det = (
        state.first_detection or decision.source_timestamp
        if is_reopen
        else decision.source_timestamp
    )
    return _emit_anomaly_result(
        state,
        decision,
        policy,
        action,
        alert_id,
        first_det,
        new_anomaly_streak,
        new_anomaly_decision_ids,
    )


def _handle_anomaly_update(
    state: AlertState,
    decision: ScoreDecisionV1,
    policy: LockedAlertPolicyV1,
    new_anomaly_streak: int,
    new_anomaly_decision_ids: tuple[UUID, ...],
) -> TransitionResult:
    alert_id = state.active_alert_id
    assert alert_id is not None
    first_det = state.first_detection or decision.source_timestamp
    return _emit_anomaly_result(
        state,
        decision,
        policy,
        "UPDATED",
        alert_id,
        first_det,
        new_anomaly_streak,
        new_anomaly_decision_ids,
    )


def _handle_normal(
    state: AlertState,
    decision: ScoreDecisionV1,
    policy: LockedAlertPolicyV1,
) -> TransitionResult:
    new_normal_streak = state.normal_streak + 1

    if state.active_alert_id is not None:
        if new_normal_streak >= policy.cooldown_decisions:
            alert_id = state.active_alert_id
            first_det = state.first_detection or decision.source_timestamp
            last_det = state.last_detection or decision.source_timestamp

            event = AlertEventV1(
                schema_version="alert-event-v1",
                message_id=uuid4(),
                replay_session_id=decision.replay_session_id,
                source_dataset_sha256=decision.source_dataset_sha256,
                contract_sha256=decision.contract_sha256,
                source_timestamp=decision.source_timestamp,
                emitted_at=datetime.now(UTC),
                alert_id=alert_id,
                machine_id=state.machine_id,
                action="RESOLVED",
                first_detection=first_det,
                last_detection=last_det,
                decision_ids=state.anomaly_decision_ids,
                policy_sha256=policy.policy_sha256,
            )

            new_state = AlertState(
                replay_session_id=state.replay_session_id,
                machine_id=state.machine_id,
                active_alert_id=None,
                previous_alert_id=alert_id,
                first_detection=first_det,
                last_detection=last_det,
                resolved_at=decision.source_timestamp,
                anomaly_decision_ids=(),
                anomaly_streak=0,
                normal_streak=new_normal_streak,
                last_decision_id=decision.decision_id,
                last_source_timestamp=decision.source_timestamp,
            )
            return TransitionResult(state=new_state, event=event, evidence=None)
        else:
            new_state = AlertState(
                replay_session_id=state.replay_session_id,
                machine_id=state.machine_id,
                active_alert_id=state.active_alert_id,
                previous_alert_id=state.previous_alert_id,
                first_detection=state.first_detection,
                last_detection=state.last_detection,
                resolved_at=state.resolved_at,
                anomaly_decision_ids=state.anomaly_decision_ids,
                anomaly_streak=0,
                normal_streak=new_normal_streak,
                last_decision_id=decision.decision_id,
                last_source_timestamp=decision.source_timestamp,
            )
            return TransitionResult(state=new_state, event=None, evidence=None)

    new_state = AlertState(
        replay_session_id=state.replay_session_id,
        machine_id=state.machine_id,
        active_alert_id=None,
        previous_alert_id=state.previous_alert_id,
        first_detection=state.first_detection,
        last_detection=state.last_detection,
        resolved_at=state.resolved_at,
        anomaly_decision_ids=(),
        anomaly_streak=0,
        normal_streak=new_normal_streak,
        last_decision_id=decision.decision_id,
        last_source_timestamp=decision.source_timestamp,
    )
    return TransitionResult(state=new_state, event=None, evidence=None)


def transition(
    state: AlertState,
    decision: ScoreDecisionV1,
    policy: LockedAlertPolicyV1,
) -> TransitionResult:
    if decision.decision_id == state.last_decision_id:
        return TransitionResult(state=state, event=None, evidence=None)

    if (
        state.last_source_timestamp is not None
        and decision.source_timestamp <= state.last_source_timestamp
    ):
        raise OrderingViolationError(
            f"Decision timestamp {decision.source_timestamp} is not strictly greater than {state.last_source_timestamp}"
        )

    if decision.is_anomaly:
        new_anomaly_streak = state.anomaly_streak + 1
        new_anomaly_decision_ids = (*state.anomaly_decision_ids, decision.decision_id)
        if state.active_alert_id is None:
            return _handle_anomaly_trigger(
                state, decision, policy, new_anomaly_streak, new_anomaly_decision_ids
            )
        return _handle_anomaly_update(
            state, decision, policy, new_anomaly_streak, new_anomaly_decision_ids
        )

    return _handle_normal(state, decision, policy)
