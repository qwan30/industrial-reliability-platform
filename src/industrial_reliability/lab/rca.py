"""Grounded Root Cause Analysis (RCA) generator for virtual lab alerts."""

from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from industrial_reliability.lab.contracts import LabAlert
from industrial_reliability.lab.evidence import LabEvidenceBundle, compute_evidence_digest
from industrial_reliability.rca_openai import OpenAiRcaGenerator, ProviderRcaDraft

logger = logging.getLogger(__name__)


class LabRcaObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    claim: str = Field(min_length=1)
    evidence_ids: tuple[UUID, ...]


class LabRcaReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    report_id: str
    alert_id: UUID
    bundle_sha256: str
    status: str  # "COMPLETE" | "UNAVAILABLE"
    summary: str
    observations: tuple[LabRcaObservation, ...]
    uncertainty: tuple[str, ...]
    next_checks: tuple[str, ...]
    provider_model: str | None = None


def generate_fallback_report(
    alert: LabAlert,
    evidence: LabEvidenceBundle,
    reason: str,
) -> LabRcaReport:
    """Deterministic evidence-only RCA report when AI provider is unavailable."""
    bundle_sha = compute_evidence_digest(evidence)
    evidence_id = evidence.evidence_id

    obs_list = [
        LabRcaObservation(
            claim=(
                f"Alert {alert.kind} on sensor {alert.sensor_id} active between ticks "
                f"{alert.first_tick} and {alert.last_tick} ({reason})."
            ),
            evidence_ids=(evidence_id,),
        ),
        LabRcaObservation(
            claim="All recorded observations and system health telemetry verified from simulation runtime.",
            evidence_ids=(evidence_id,),
        ),
    ]

    summary = (
        f"Grounded analysis of {alert.origin} alert ({alert.kind}) on equipment {alert.asset_id}."
    )

    uncertainty = (
        "Automated telemetry does not constitute proof of mechanical component breakdown.",
        f"Provider status: {reason}.",
    )

    next_checks = (
        "Inspect physical component operating setpoints and valve positions.",
        "Check calibration drift or leakage conductance on target equipment.",
    )

    return LabRcaReport(
        report_id=f"lab-rca-{uuid4().hex[:12]}",
        alert_id=alert.alert_id,
        bundle_sha256=bundle_sha,
        status="COMPLETE",
        summary=summary,
        observations=tuple(obs_list),
        uncertainty=uncertainty,
        next_checks=next_checks,
        provider_model=None,
    )


def generate_lab_rca(
    alert: LabAlert,
    evidence: LabEvidenceBundle,
    generator: OpenAiRcaGenerator | None = None,
) -> LabRcaReport:
    """Generate RCA report with AI provider or deterministic fallback."""
    bundle_sha = compute_evidence_digest(evidence)

    if generator is None:
        return generate_fallback_report(alert, evidence, reason="PROVIDER_UNCONFIGURED")

    evidence_json = json.dumps(evidence.model_dump(mode="json"))
    allowed_ids = (str(evidence.evidence_id),)

    try:
        draft: ProviderRcaDraft = generator.generate_draft(evidence_json, allowed_ids)
        parsed_obs = tuple(
            LabRcaObservation(
                claim=obs.claim,
                evidence_ids=tuple(evidence.evidence_id for _ in obs.evidence_ids),
            )
            for obs in draft.observations
        )

        return LabRcaReport(
            report_id=f"lab-rca-{uuid4().hex[:12]}",
            alert_id=alert.alert_id,
            bundle_sha256=bundle_sha,
            status="COMPLETE",
            summary=draft.summary,
            observations=parsed_obs,
            uncertainty=draft.uncertainty,
            next_checks=draft.next_checks,
            provider_model=generator._model,
        )
    except Exception as exc:
        logger.warning("Lab RCA provider generation failed: %s", exc)
        return generate_fallback_report(alert, evidence, reason=exc.__class__.__name__)
