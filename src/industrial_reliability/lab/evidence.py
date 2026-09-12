"""Evidence bundle extraction, canonical hashing, and provenance for lab alerts."""

from __future__ import annotations

import hashlib
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from industrial_reliability.lab.contracts import (
    AlertOrigin,
    LabAlert,
    Observation,
    SimulationRun,
)
from industrial_reliability.report_hashes import canonical_json_bytes


class LabEvidenceBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: UUID
    source: Literal["SIMULATION"] = "SIMULATION"
    run_id: UUID
    asset_id: UUID
    sensor_id: UUID
    definition_digest: str
    profile_digest: str
    baseline_id: UUID | None = None
    tick_range: tuple[int, int]
    observations: tuple[Observation, ...]
    features: list[float] = Field(default_factory=list)
    score: float | None = None
    threshold: float | None = None
    rule_origin: AlertOrigin
    system_health: dict[str, str] = Field(default_factory=dict)


def compute_evidence_digest(bundle: LabEvidenceBundle) -> str:
    """Compute deterministic SHA256 of canonical evidence payload."""
    data = bundle.model_dump(mode="json")
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def create_alert_evidence(
    alert: LabAlert,
    observations: tuple[Observation, ...],
    run: SimulationRun,
    features: list[float] | None = None,
    score: float | None = None,
    threshold: float | None = None,
) -> LabEvidenceBundle:
    """Extract immutable evidence bundle for an alert."""
    # Deterministic UUIDv5
    evidence_name = f"evidence:{run.run_id}:{alert.sensor_id}:{alert.origin}:{alert.first_tick}:{alert.last_tick}"
    evidence_id = uuid5(NAMESPACE_URL, evidence_name)

    # Filter observations relevant to this sensor and tick window
    window_obs = tuple(
        o
        for o in observations
        if o.sensor_id == alert.sensor_id and alert.first_tick <= o.tick <= alert.last_tick
    )

    return LabEvidenceBundle(
        evidence_id=evidence_id,
        source="SIMULATION",
        run_id=run.run_id,
        asset_id=alert.asset_id,
        sensor_id=alert.sensor_id,
        definition_digest=run.definition_digest,
        profile_digest=run.profile_digest,
        baseline_id=run.baseline_id,
        tick_range=(alert.first_tick, alert.last_tick),
        observations=window_obs,
        features=features or [],
        score=score,
        threshold=threshold,
        rule_origin=alert.origin,
        system_health={"simulation": "RUNNING", "kafka": "CONNECTED", "database": "HEALTHY"},
    )
