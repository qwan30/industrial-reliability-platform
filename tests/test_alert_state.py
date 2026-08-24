from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from industrial_reliability.alert_policy import LockedAlertPolicyV1
from industrial_reliability.alert_state import (
    AlertState,
    OrderingViolationError,
    transition,
)
from industrial_reliability.runtime_messages import (
    EvidenceValueV1,
    ScoreDecisionV1,
)


def _make_policy(
    persistence: int = 2,
    cooldown: int = 2,
    merge_gap_seconds: int = 300,
) -> LockedAlertPolicyV1:
    return LockedAlertPolicyV1(
        schema_version="alert-policy-v1",
        source_split="calibration",
        source_scores_sha256="a" * 64,
        source_dataset_sha256="b" * 64,
        contract_sha256="c" * 64,
        model_id="statistical",
        model_version="champion-statistical-v1",
        threshold=1.0,
        stride_seconds=300,
        persistence_decisions=persistence,
        cooldown_decisions=cooldown,
        merge_gap_seconds=merge_gap_seconds,
        calibration_false_episodes_per_day=0.1,
        calibration_time_in_alert=0.01,
        policy_sha256="d" * 64,
    )


def _make_decision(
    session_id: UUID,
    seq: int,
    is_anomaly: bool,
    start_ts: datetime = datetime(2020, 4, 18, 0, 0),
) -> ScoreDecisionV1:
    decision_id = uuid4()
    window_id = uuid4()
    ts = start_ts + timedelta(minutes=5 * seq)
    return ScoreDecisionV1(
        message_id=uuid4(),
        replay_session_id=session_id,
        source_dataset_sha256="b" * 64,
        contract_sha256="c" * 64,
        source_timestamp=ts,
        emitted_at=datetime.now(UTC),
        decision_id=decision_id,
        window_id=window_id,
        model_version="champion-statistical-v1",
        score=1.5 if is_anomaly else 0.4,
        threshold=1.0,
        is_anomaly=is_anomaly,
        evidence_vector=(
            EvidenceValueV1(
                feature_name="tp2_mean",
                feature_value=1.5 if is_anomaly else 0.4,
                robust_deviation=0.5 if is_anomaly else 0.0,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("flags", "actions"),
    [
        ([True, True, False, False], [None, "OPENED", None, "RESOLVED"]),
        ([True, False, True, True], [None, None, None, "OPENED"]),
        ([True, True, True, False, False], [None, "OPENED", "UPDATED", None, "RESOLVED"]),
    ],
)
def test_transition_obeys_persistence_and_cooldown(
    flags: list[bool], actions: list[str | None]
) -> None:
    session_id = uuid4()
    state = AlertState.empty(session_id, "metropt3")
    policy = _make_policy(persistence=2, cooldown=2)

    actual = []
    for index, flag in enumerate(flags):
        decision = _make_decision(session_id, index, flag)
        res = transition(state, decision, policy)
        state = res.state
        actual.append(res.event.action if res.event else None)

    assert actual == actions


def test_replay_of_same_decision_is_a_noop() -> None:
    session_id = uuid4()
    state = AlertState.empty(session_id, "metropt3")
    policy = _make_policy(persistence=1, cooldown=1)
    decision = _make_decision(session_id, 1, True)

    first = transition(state, decision, policy)
    assert first.event is not None
    assert first.event.action == "OPENED"

    duplicate = transition(first.state, decision, policy)
    assert duplicate.event is None
    assert duplicate.evidence is None
    assert duplicate.state == first.state


def test_ordering_violation_raises_error() -> None:
    session_id = uuid4()
    state = AlertState.empty(session_id, "metropt3")
    policy = _make_policy(persistence=1, cooldown=1)

    dec1 = _make_decision(session_id, 5, True)
    dec2 = _make_decision(session_id, 3, True)  # Earlier timestamp!

    res1 = transition(state, dec1, policy)
    with pytest.raises(OrderingViolationError):
        transition(res1.state, dec2, policy)


def test_reopen_merged_alert() -> None:
    session_id = uuid4()
    state = AlertState.empty(session_id, "metropt3")
    # persistence=1, cooldown=1, merge_gap=600s (10 min)
    policy = _make_policy(persistence=1, cooldown=1, merge_gap_seconds=600)

    # 1. Open alert at t=0
    dec0 = _make_decision(session_id, 0, True)
    res0 = transition(state, dec0, policy)
    assert res0.event is not None and res0.event.action == "OPENED"
    initial_alert_id = res0.event.alert_id

    # 2. Resolve alert at t=5min
    dec1 = _make_decision(session_id, 1, False)
    res1 = transition(res0.state, dec1, policy)
    assert res1.event is not None and res1.event.action == "RESOLVED"

    # 3. New anomaly at t=10min (gap is 5 min <= 10 min merge gap)
    dec2 = _make_decision(session_id, 2, True)
    res2 = transition(res1.state, dec2, policy)
    assert res2.event is not None and res2.event.action == "REOPENED"
    assert res2.event.alert_id == initial_alert_id
