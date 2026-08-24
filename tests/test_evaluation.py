from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from industrial_reliability.contracts import Event
from industrial_reliability.evaluation import (
    Episode,
    build_episodes,
    calibrate_threshold,
    evaluate,
)
from tests.helpers import sample_policy
from tests.helpers import score_frame as _score_frame

BASE_TIME = datetime(2022, 1, 1, 6)


def score_frame(offsets: list[int], scores: list[float]) -> pd.DataFrame:
    """Return schema-valid synthetic score frames."""
    frame = _score_frame(offsets, scores)
    return frame.assign(window_start=[end - timedelta(seconds=1) for end in frame["window_end"]])


def event(
    event_id: str,
    start_offset: int,
    end_offset: int,
    *,
    lps_offset: int | None = None,
) -> Event:
    return Event(
        event_id=event_id,
        failure_type="synthetic",
        source_start=BASE_TIME + timedelta(seconds=start_offset),
        source_end=BASE_TIME + timedelta(seconds=end_offset),
        source_precision="minute",
        paper_count=end_offset - start_offset,
        local_lps_transition=(
            BASE_TIME + timedelta(seconds=lps_offset) if lps_offset is not None else None
        ),
        disagreement=None,
    )


@pytest.mark.parametrize(
    ("method", "expected"),
    [("higher", 2.0), ("lower", 1.0)],
)
def test_threshold_uses_contract_quantile_and_method(method: str, expected: float) -> None:
    calibration = np.array([0.0, 1.0, 2.0, 3.0])
    contract = sample_policy(threshold_quantile=0.5, threshold_method=method)

    assert calibrate_threshold(calibration, contract) == expected


def test_threshold_uses_higher_calibration_quantile() -> None:
    calibration = np.array([0.0, 1.0, 2.0, 3.0])

    assert calibrate_threshold(calibration, sample_policy()) == 3.0


@pytest.mark.parametrize("calibration", [np.array([]), np.array([1.0, np.nan])])
def test_threshold_rejects_empty_or_nonfinite_calibration(calibration: np.ndarray) -> None:
    policy = sample_policy()
    with pytest.raises(ValueError):
        calibrate_threshold(calibration, policy)


def test_adjacent_anomalies_form_one_episode_from_first_window_end() -> None:
    contract = sample_policy(stride_seconds=300)
    scores = score_frame([0, 300, 600], [2.0, 3.0, 0.0])

    episodes = build_episodes(scores, 1.0, contract)

    assert episodes == (
        Episode(
            detection_time=scores.iloc[0]["window_end"],
            last_detection_time=scores.iloc[1]["window_end"],
            decision_count=2,
        ),
    )


def test_episode_comparison_honors_inclusive_contract_flag() -> None:
    scores = score_frame([0, 10], [1.0, 2.0])

    inclusive = build_episodes(scores, 1.0, sample_policy(anomaly_inclusive=True))
    exclusive = build_episodes(scores, 1.0, sample_policy(anomaly_inclusive=False))

    assert inclusive[0].detection_time == BASE_TIME
    assert inclusive[0].decision_count == 2
    assert exclusive[0].detection_time == BASE_TIME + timedelta(seconds=10)
    assert exclusive[0].decision_count == 1


def test_anomalies_more_than_one_stride_apart_form_separate_episodes() -> None:
    episodes = build_episodes(
        score_frame([0, 10, 21], [2.0, 2.0, 2.0]),
        1.0,
        sample_policy(stride_seconds=10),
    )

    assert [episode.decision_count for episode in episodes] == [2, 1]


def test_score_frame_requires_window_start_for_both_public_evaluators() -> None:
    scores = _score_frame([0, 60], [0.0, 0.0])
    policy = sample_policy()
    events = (event("event-1", 0, 60),)

    with pytest.raises(ValueError, match="window_start"):
        build_episodes(scores, 1.0, policy)
    with pytest.raises(ValueError, match="window_start"):
        evaluate(
            scores,
            (),
            1.0,
            events,
            policy,
        )


@pytest.mark.parametrize("starts", [[0, 0], [60, 0]])
def test_score_frame_rejects_nonincreasing_window_starts_with_increasing_ends(
    starts: list[int],
) -> None:
    scores = score_frame([60, 120], [0.0, 0.0]).assign(
        window_start=[BASE_TIME + timedelta(seconds=start) for start in starts]
    )
    policy = sample_policy()

    assert scores["window_end"].is_monotonic_increasing
    with pytest.raises(ValueError, match=r"window_start.*strictly increasing"):
        build_episodes(scores, 1.0, policy)


@pytest.mark.parametrize(
    "scores",
    [
        score_frame([], []),
        score_frame([0, 10], [1.0, np.inf]),
        score_frame([10, 0], [1.0, 2.0]),
        score_frame([0, 0], [1.0, 2.0]),
    ],
)
def test_episode_builder_rejects_empty_nonfinite_or_nonmonotonic_scores(
    scores: pd.DataFrame,
) -> None:
    policy = sample_policy()
    with pytest.raises(ValueError):
        build_episodes(scores, 1.0, policy)


def test_evaluation_reports_event_window_and_exposure_arithmetic() -> None:
    contract = sample_policy(
        stride_seconds=60,
        event_horizon_seconds=120,
        min_detected_events=2,
        max_false_episodes_per_day=360.0,
        max_time_in_alert=4 / 11,
    )
    events = (
        event("event-1", 600, 720, lps_offset=660),
        event("event-2", 1_200, 1_320),
        event("event-3", 1_800, 1_920),
    )
    scores = score_frame(
        [300, 480, 540, 600, 900, 1_080, 1_260, 1_500, 1_680, 1_800, 2_100],
        [0.0, 2.0, 2.0, 0.0, 0.0, 0.0, 2.0, 2.0, 0.0, 0.0, 0.0],
    )
    episodes = build_episodes(scores, 1.0, contract)

    result = evaluate(scores, episodes, 1.0, events, contract)

    assert result.threshold == 1.0
    assert result.valid_holdout_decisions == 11
    assert result.positive_decisions == 7
    assert result.anomalous_decisions == 4
    assert result.normal_valid_decisions == 4
    assert result.normal_exposure_days == pytest.approx(1 / 360)
    assert result.time_in_alert == pytest.approx(4 / 11)
    assert result.pr_auc == pytest.approx(211 / 308)
    assert result.detected_events == 2
    assert result.total_events == 3
    assert result.false_episodes == 1
    assert result.false_episodes_per_day == pytest.approx(360.0)
    assert result.feasible is True

    first, second, third = result.event_results
    assert first.evaluable is True
    assert first.matching_horizon_valid_decisions == 3
    assert first.source_interval_valid_decisions == 1
    assert first.source_interval_coverage_seconds == 60
    assert first.detected is True
    assert first.first_detection_time == BASE_TIME + timedelta(seconds=480)
    assert first.lead_seconds_to_source_start == 120.0
    assert first.lead_seconds_to_local_lps == 180.0

    assert second.detected is True
    assert second.first_detection_time == BASE_TIME + timedelta(seconds=1_260)
    assert second.lead_seconds_to_source_start == -60.0
    assert second.lead_seconds_to_local_lps is None

    assert third.evaluable is True
    assert third.detected is False
    assert third.first_detection_time is None
    assert third.lead_seconds_to_source_start is None
    assert third.lead_seconds_to_local_lps is None


def test_default_two_hour_horizon_includes_its_start_and_excludes_event_end() -> None:
    contract = sample_policy(stride_seconds=60, event_horizon_seconds=7_200)
    events = (event("event-1", 7_200, 7_260),)
    scores = score_frame([-60, 0, 7_260, 7_320], [0.0, 2.0, 0.0, 0.0])

    result = evaluate(scores, build_episodes(scores, 1.0, contract), 1.0, events, contract)

    assert result.positive_decisions == 1
    assert result.event_results[0].matching_horizon_valid_decisions == 1
    assert result.event_results[0].first_detection_time == BASE_TIME
    assert result.event_results[0].lead_seconds_to_source_start == 7_200.0


def test_episode_interval_can_match_source_after_detection_before_horizon() -> None:
    contract = sample_policy(stride_seconds=60, event_horizon_seconds=120)
    events = (event("event-1", 600, 720),)
    scores = score_frame([300, 420, 480, 540, 600, 900], [0.0, 2.0, 2.0, 2.0, 2.0, 0.0])

    result = evaluate(scores, build_episodes(scores, 1.0, contract), 1.0, events, contract)

    assert result.event_results[0].detected is True
    assert result.event_results[0].first_detection_time == BASE_TIME + timedelta(seconds=420)
    assert result.event_results[0].lead_seconds_to_source_start == 180.0
    assert result.false_episodes == 0


def test_event_matching_excludes_touching_episode_boundaries() -> None:
    contract = sample_policy(stride_seconds=60, event_horizon_seconds=0)
    events = (event("event-1", 600, 720),)
    scores = score_frame([540, 600, 720, 780], [2.0, 0.0, 2.0, 0.0])

    result = evaluate(scores, build_episodes(scores, 1.0, contract), 1.0, events, contract)

    assert result.event_results[0].detected is False
    assert result.false_episodes == 2


def test_overlapping_event_horizons_count_positive_decisions_once() -> None:
    contract = sample_policy(stride_seconds=60, event_horizon_seconds=120)
    events = (event("event-1", 600, 720), event("event-2", 660, 780))
    scores = score_frame(
        [300, 480, 540, 600, 660, 720, 780, 900],
        [0.0] * 8,
    )

    result = evaluate(scores, (), 1.0, events, contract)

    assert [item.matching_horizon_valid_decisions for item in result.event_results] == [4, 4]
    assert result.positive_decisions == 5
    assert result.normal_valid_decisions == 3


def test_feasibility_gate_requires_every_predeclared_limit() -> None:
    events = (event("event-1", 600, 720), event("event-2", 1_200, 1_320))
    scores = score_frame([300, 480, 900, 1_080, 1_500], [0.0, 2.0, 0.0, 2.0, 0.0])
    episodes = build_episodes(scores, 1.0, sample_policy(stride_seconds=60))

    result = evaluate(
        scores,
        episodes,
        1.0,
        events,
        sample_policy(
            stride_seconds=60,
            min_detected_events=2,
            max_false_episodes_per_day=0.0,
            max_time_in_alert=0.39,
        ),
    )

    assert result.detected_events == 2
    assert result.false_episodes == 0
    assert result.time_in_alert == pytest.approx(0.4)
    assert result.feasible is False


def test_evaluation_rejects_an_event_without_a_valid_matching_decision() -> None:
    scores = score_frame([0], [0.0])
    events = (event("event-1", 600, 720),)
    policy = sample_policy(event_horizon_seconds=120)

    with pytest.raises(ValueError, match="evaluable"):
        evaluate(
            scores,
            (),
            1.0,
            events,
            policy,
        )


def test_evaluation_rejects_zero_normal_exposure() -> None:
    contract = sample_policy(stride_seconds=60, event_horizon_seconds=120)
    scores = score_frame([480, 540, 600], [0.0, 2.0, 0.0])
    episodes = build_episodes(scores, 1.0, contract)
    events = (event("event-1", 600, 720),)

    with pytest.raises(ValueError, match="normal exposure"):
        evaluate(
            scores,
            episodes,
            1.0,
            events,
            contract,
        )


@pytest.mark.parametrize(
    "scores",
    [score_frame([], []), score_frame([0], [np.nan]), score_frame([10, 0], [0.0, 0.0])],
)
def test_evaluation_rejects_empty_nonfinite_or_nonmonotonic_holdout(
    scores: pd.DataFrame,
) -> None:
    events = (event("event-1", 0, 60),)
    policy = sample_policy()
    with pytest.raises(ValueError):
        evaluate(
            scores,
            (),
            1.0,
            events,
            policy,
        )
