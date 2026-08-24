"""Frozen, extra-forbid Pydantic v2 schemas for runtime scoring messages."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageEvidenceV1(FrozenMessage):
    observations_by_bin: tuple[int, int, int, int, int, int]
    bin_ends: tuple[datetime, datetime, datetime, datetime, datetime, datetime]

    @model_validator(mode="after")
    def validate_coverage(self) -> CoverageEvidenceV1:
        if len(self.observations_by_bin) != 6:
            raise ValueError("observations_by_bin must contain exactly 6 elements")
        if len(self.bin_ends) != 6:
            raise ValueError("bin_ends must contain exactly 6 elements")

        for cnt in self.observations_by_bin:
            if cnt < 24:
                raise ValueError(f"Observation count {cnt} is less than min 24 observations/bin")

        for i in range(len(self.bin_ends) - 1):
            if self.bin_ends[i] >= self.bin_ends[i + 1]:
                raise ValueError("bin_ends must be strictly increasing")
            if self.bin_ends[i].tzinfo is not None:
                raise ValueError("bin_ends must be timezone-naive")

        if self.bin_ends[-1].tzinfo is not None:
            raise ValueError("bin_ends must be timezone-naive")

        return self


class FeatureVectorV1(FrozenMessage):
    schema_version: Literal["feature-vector-v1"] = "feature-vector-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_timestamp: datetime
    emitted_at: datetime
    window_id: UUID
    machine_id: str = Field(min_length=1, max_length=128)
    window_start: datetime
    window_end: datetime
    feature_names: tuple[str, ...] = Field(min_length=1)
    feature_values: tuple[float, ...] = Field(min_length=1)
    coverage: CoverageEvidenceV1

    @model_validator(mode="after")
    def validate_feature_vector(self) -> FeatureVectorV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError("source_timestamp must be timezone-naive")
        if self.window_start.tzinfo is not None or self.window_end.tzinfo is not None:
            raise ValueError("window_start and window_end must be timezone-naive")
        if self.emitted_at.tzinfo is None:
            raise ValueError("emitted_at must be timezone-aware UTC")

        if not (self.window_start < self.window_end == self.source_timestamp):
            raise ValueError(
                "window_start must be < window_end and window_end must equal source_timestamp"
            )

        if len(self.feature_names) != len(self.feature_values):
            raise ValueError("feature_names and feature_values must have the same length")

        if len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature_names must contain unique elements")

        for val in self.feature_values:
            if not math.isfinite(val):
                raise ValueError("feature_values must contain only finite numbers")

        return self


class ScoreRequestV1(FrozenMessage):
    model_version: str = Field(min_length=1, max_length=200)
    feature_vector: FeatureVectorV1


class EvidenceValueV1(FrozenMessage):
    feature_name: str
    feature_value: float
    robust_deviation: float

    @model_validator(mode="after")
    def validate_evidence(self) -> EvidenceValueV1:
        if not math.isfinite(self.feature_value) or not math.isfinite(self.robust_deviation):
            raise ValueError("feature_value and robust_deviation must be finite numbers")
        return self


class ScoreDecisionV1(FrozenMessage):
    schema_version: Literal["score-decision-v1"] = "score-decision-v1"
    message_id: UUID
    replay_session_id: UUID
    source_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_timestamp: datetime
    emitted_at: datetime
    decision_id: UUID
    window_id: UUID
    model_version: str = Field(min_length=1, max_length=200)
    score: float
    threshold: float
    is_anomaly: bool
    evidence_vector: tuple[EvidenceValueV1, ...]

    @model_validator(mode="after")
    def validate_decision(self) -> ScoreDecisionV1:
        if self.source_timestamp.tzinfo is not None:
            raise ValueError("source_timestamp must be timezone-naive")
        if self.emitted_at.tzinfo is None:
            raise ValueError("emitted_at must be timezone-aware UTC")
        if not math.isfinite(self.score) or not math.isfinite(self.threshold):
            raise ValueError("score and threshold must be finite numbers")
        return self


class ApiErrorV1(FrozenMessage):
    code: str
    message: str


class ScoreResponseV1(FrozenMessage):
    success: Literal[True] = True
    data: ScoreDecisionV1
    error: None = None


class ErrorResponseV1(FrozenMessage):
    success: Literal[False] = False
    data: None = None
    error: ApiErrorV1
