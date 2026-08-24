"""Contract-driven threshold calibration and holdout event evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Literal, Protocol, cast

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike, NDArray
from sklearn.metrics import average_precision_score

from industrial_reliability.contracts import Event


class EvaluationPolicy(Protocol):
    @property
    def stride_seconds(self) -> int: ...

    @property
    def event_horizon_seconds(self) -> int: ...

    @property
    def threshold_quantile(self) -> float: ...

    @property
    def threshold_method(self) -> str: ...

    @property
    def anomaly_inclusive(self) -> bool: ...

    @property
    def min_detected_events(self) -> int: ...

    @property
    def max_false_episodes_per_day(self) -> float: ...

    @property
    def max_time_in_alert(self) -> float: ...


type QuantileMethod = Literal[
    "inverted_cdf",
    "averaged_inverted_cdf",
    "closest_observation",
    "interpolated_inverted_cdf",
    "hazen",
    "weibull",
    "linear",
    "median_unbiased",
    "normal_unbiased",
    "lower",
    "higher",
    "midpoint",
    "nearest",
]


@dataclass(frozen=True)
class Episode:
    detection_time: datetime
    last_detection_time: datetime
    decision_count: int


@dataclass(frozen=True)
class EventResult:
    event_id: str
    evaluable: bool
    matching_horizon_valid_decisions: int
    source_interval_valid_decisions: int
    source_interval_coverage_seconds: int
    detected: bool
    first_detection_time: datetime | None
    lead_seconds_to_source_start: float | None
    lead_seconds_to_local_lps: float | None


@dataclass(frozen=True)
class EvaluationResult:
    threshold: float
    valid_holdout_decisions: int
    positive_decisions: int
    anomalous_decisions: int
    normal_valid_decisions: int
    normal_exposure_days: float
    time_in_alert: float
    pr_auc: float
    detected_events: int
    total_events: int
    false_episodes: int
    false_episodes_per_day: float
    event_results: tuple[EventResult, ...]
    feasible: bool


def _validate_contract(contract: EvaluationPolicy) -> None:
    if contract.stride_seconds <= 0:
        raise ValueError("stride_seconds must be positive")
    if contract.event_horizon_seconds < 0:
        raise ValueError("event_horizon_seconds must be non-negative")


def _validate_threshold(threshold: float) -> float:
    value = float(threshold)
    if not np.isfinite(value):
        raise ValueError("threshold must be finite")
    return value


def _as_naive_datetime(value: object, field: str) -> datetime:
    try:
        timestamp = pd.Timestamp(cast("str | datetime | np.datetime64", value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must contain valid datetimes") from error
    if pd.isna(timestamp) or timestamp.tzinfo is not None:
        raise ValueError(f"{field} must contain naive valid datetimes")
    return timestamp.to_pydatetime()


def _validated_scores(
    scores: pd.DataFrame,
) -> tuple[tuple[datetime, ...], NDArray[np.float64]]:
    if scores.empty:
        raise ValueError("score frame must not be empty")
    missing = {"window_start", "window_end", "score"}.difference(scores.columns)
    if missing:
        raise ValueError(f"score frame is missing columns: {sorted(missing)}")

    try:
        values = np.asarray(scores["score"], dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("scores must be numeric") from error
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("scores must be a finite one-dimensional sequence")

    ends = tuple(_as_naive_datetime(value, "window_end") for value in scores["window_end"])
    if any(current <= previous for previous, current in pairwise(ends)):
        raise ValueError("window_end must be strictly increasing")

    starts = tuple(_as_naive_datetime(value, "window_start") for value in scores["window_start"])
    if any(current <= previous for previous, current in pairwise(starts)):
        raise ValueError("window_start must be strictly increasing")
    if any(start > end for start, end in zip(starts, ends, strict=True)):
        raise ValueError("window_start must not follow window_end")
    return ends, values


def _anomalies(
    scores: NDArray[np.float64], threshold: float, contract: EvaluationPolicy
) -> NDArray[np.bool_]:
    if contract.anomaly_inclusive:
        return scores >= threshold
    return scores > threshold


def calibrate_threshold(calibration_scores: ArrayLike, contract: EvaluationPolicy) -> float:
    """Select the frozen quantile using calibration scores only."""
    values = np.asarray(calibration_scores, dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("calibration_scores must be a non-empty one-dimensional sequence")
    if not np.isfinite(values).all():
        raise ValueError("calibration_scores must be finite")
    if not 0.0 <= contract.threshold_quantile <= 1.0:
        raise ValueError("threshold_quantile must be between zero and one")
    try:
        return float(
            np.quantile(
                values,
                contract.threshold_quantile,
                method=cast(QuantileMethod, contract.threshold_method),
            )
        )
    except ValueError as error:
        raise ValueError(f"invalid threshold_method: {contract.threshold_method}") from error


def build_episodes(
    scores: pd.DataFrame,
    threshold: float,
    contract: EvaluationPolicy,
) -> tuple[Episode, ...]:
    """Merge adjacent anomalous decisions into immutable evaluation episodes."""
    _validate_contract(contract)
    threshold_value = _validate_threshold(threshold)
    ends, values = _validated_scores(scores)
    anomalous_ends = tuple(
        end
        for end, anomalous in zip(
            ends,
            _anomalies(values, threshold_value, contract),
            strict=True,
        )
        if anomalous
    )
    if not anomalous_ends:
        return ()

    episodes: list[Episode] = []
    first = anomalous_ends[0]
    last = first
    count = 1
    for current in anomalous_ends[1:]:
        if (current - last).total_seconds() <= contract.stride_seconds:
            last = current
            count += 1
            continue
        episodes.append(Episode(first, last, count))
        first = current
        last = current
        count = 1
    episodes.append(Episode(first, last, count))
    return tuple(episodes)


def _episode_matches_event(
    episode: Episode,
    event: Event,
    contract: EvaluationPolicy,
) -> bool:
    horizon_start = event.source_start - timedelta(seconds=contract.event_horizon_seconds)
    detected_in_horizon = horizon_start <= episode.detection_time < event.source_end
    episode_end = episode.last_detection_time + timedelta(seconds=contract.stride_seconds)
    overlaps_source = episode.detection_time < event.source_end and episode_end > event.source_start
    return detected_in_horizon or overlaps_source


def _validated_events(events: Sequence[Event]) -> tuple[Event, ...]:
    result = tuple(events)
    if not result:
        raise ValueError("events must not be empty")
    for event in result:
        if event.source_start.tzinfo is not None or event.source_end.tzinfo is not None:
            raise ValueError("event times must be naive")
        if event.source_start >= event.source_end:
            raise ValueError("event source interval must be non-empty")
    return result


def _validated_episodes(episodes: Sequence[Episode]) -> tuple[Episode, ...]:
    result = tuple(episodes)
    for index, episode in enumerate(result):
        if episode.decision_count <= 0 or episode.detection_time > episode.last_detection_time:
            raise ValueError("episode fields are inconsistent")
        if (
            episode.detection_time.tzinfo is not None
            or episode.last_detection_time.tzinfo is not None
        ):
            raise ValueError("episode times must be naive")
        if index and episode.detection_time <= result[index - 1].last_detection_time:
            raise ValueError("episodes must be strictly ordered and non-overlapping")
    return result


def evaluate(
    holdout_scores: pd.DataFrame,
    episodes: Sequence[Episode],
    threshold: float,
    events: Sequence[Event],
    contract: EvaluationPolicy,
) -> EvaluationResult:
    """Evaluate one untouched holdout score sequence against frozen event semantics."""
    _validate_contract(contract)
    threshold_value = _validate_threshold(threshold)
    ends, score_values = _validated_scores(holdout_scores)
    event_values = _validated_events(events)
    episode_values = _validated_episodes(episodes)

    positive = np.zeros(len(ends), dtype=np.bool_)
    event_results: list[EventResult] = []
    for event in event_values:
        horizon_start = event.source_start - timedelta(seconds=contract.event_horizon_seconds)
        matching = tuple(horizon_start <= end < event.source_end for end in ends)
        source = tuple(event.source_start <= end < event.source_end for end in ends)
        matching_count = sum(matching)
        if matching_count == 0:
            raise ValueError(f"event {event.event_id!r} is not evaluable")
        positive |= np.asarray(matching, dtype=np.bool_)

        matched_episodes = tuple(
            episode
            for episode in episode_values
            if _episode_matches_event(episode, event, contract)
        )
        first_detection = (
            min(episode.detection_time for episode in matched_episodes)
            if matched_episodes
            else None
        )
        source_lead = (
            (event.source_start - first_detection).total_seconds()
            if first_detection is not None
            else None
        )
        lps_lead = (
            (event.local_lps_transition - first_detection).total_seconds()
            if first_detection is not None and event.local_lps_transition is not None
            else None
        )
        source_count = sum(source)
        event_results.append(
            EventResult(
                event_id=event.event_id,
                evaluable=True,
                matching_horizon_valid_decisions=matching_count,
                source_interval_valid_decisions=source_count,
                source_interval_coverage_seconds=source_count * contract.stride_seconds,
                detected=first_detection is not None,
                first_detection_time=first_detection,
                lead_seconds_to_source_start=source_lead,
                lead_seconds_to_local_lps=lps_lead,
            )
        )

    valid_decisions = len(ends)
    positive_decisions = int(positive.sum())
    normal_decisions = valid_decisions - positive_decisions
    if normal_decisions == 0:
        raise ValueError("normal exposure must be greater than zero")

    anomalous_decisions = int(_anomalies(score_values, threshold_value, contract).sum())
    normal_exposure_days = normal_decisions * contract.stride_seconds / 86_400
    false_episodes = sum(
        not any(_episode_matches_event(episode, event, contract) for event in event_values)
        for episode in episode_values
    )
    false_episodes_per_day = false_episodes / normal_exposure_days
    time_in_alert = anomalous_decisions / valid_decisions
    detected_events = sum(result.detected for result in event_results)
    feasible = (
        detected_events >= contract.min_detected_events
        and false_episodes_per_day <= contract.max_false_episodes_per_day
        and time_in_alert <= contract.max_time_in_alert
    )

    return EvaluationResult(
        threshold=threshold_value,
        valid_holdout_decisions=valid_decisions,
        positive_decisions=positive_decisions,
        anomalous_decisions=anomalous_decisions,
        normal_valid_decisions=normal_decisions,
        normal_exposure_days=normal_exposure_days,
        time_in_alert=time_in_alert,
        pr_auc=float(average_precision_score(positive, score_values)),
        detected_events=detected_events,
        total_events=len(event_values),
        false_episodes=false_episodes,
        false_episodes_per_day=false_episodes_per_day,
        event_results=tuple(event_results),
        feasible=feasible,
    )
