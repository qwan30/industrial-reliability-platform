from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from industrial_reliability.ml_provenance import (
    canonical_dumps,
    canonical_sha256,
    verify_run_provenance,
)
from industrial_reliability.package_champion import ChampionManifest

if TYPE_CHECKING:
    from industrial_reliability.ml_lifecycle import (
        CandidateResult,
        ReproductionResult,
    )

THRESHOLD_TOLERANCE = 1e-9
SCORE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Phase7GateResult:
    schema_version: str
    source_git_sha: str
    timestamp: str
    verdict: Literal["PASS", "FAIL"]
    threshold_delta: float
    golden_scores_max_delta: float
    candidate_run_id: str
    reproduction_run_id: str
    verified_hashes: dict[str, str]
    package_manifest_sha256: str
    alert_policy_sha256: str
    reasons: list[str] = field(default_factory=list)
    self_sha256: str = ""

    def compute_hash(self) -> str:
        d = asdict(self)
        d.pop("self_sha256", None)
        return canonical_sha256(d)

    def with_computed_hash(self) -> Phase7GateResult:
        return replace(self, self_sha256=self.compute_hash())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Phase7GateResult:
        return cls(
            schema_version=str(data["schema_version"]),
            source_git_sha=str(data["source_git_sha"]),
            timestamp=str(data["timestamp"]),
            verdict=data["verdict"],
            threshold_delta=float(data["threshold_delta"]),
            golden_scores_max_delta=float(data["golden_scores_max_delta"]),
            candidate_run_id=str(data["candidate_run_id"]),
            reproduction_run_id=str(data["reproduction_run_id"]),
            verified_hashes=dict(data.get("verified_hashes", {})),
            package_manifest_sha256=str(data["package_manifest_sha256"]),
            alert_policy_sha256=str(data["alert_policy_sha256"]),
            reasons=list(data.get("reasons", [])),
            self_sha256=str(data.get("self_sha256", "")),
        )


def load_phase7_attestation(path: Path) -> Phase7GateResult:
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    result = Phase7GateResult.from_dict(data)
    expected = result.compute_hash()
    if result.self_sha256 != expected:
        raise ValueError(
            f"Phase 7 attestation hash mismatch: expected {expected}, got {result.self_sha256}"
        )
    return result


def evaluate_phase7_gate(
    *,
    candidate: CandidateResult,
    reproduction: ReproductionResult,
    expected_threshold: float,
    expected_golden_scores: tuple[float, ...] | list[float],
) -> Phase7GateResult:
    reasons: list[str] = []

    # 1. Verify provenance structure and self-hashes
    try:
        verify_run_provenance(candidate.provenance)
    except Exception as e:
        reasons.append(f"Candidate provenance self-hash verification failed: {e}")

    try:
        verify_run_provenance(reproduction.provenance)
    except Exception as e:
        reasons.append(f"Reproduction provenance self-hash verification failed: {e}")

    # 2. Check lifecycle states
    if candidate.provenance.lifecycle_state != "candidate":
        reasons.append(
            f"Candidate run lifecycle_state is {candidate.provenance.lifecycle_state!r}, expected 'candidate'"
        )
    if reproduction.provenance.lifecycle_state != "reproduction":
        reasons.append(
            f"Reproduction run lifecycle_state is {reproduction.provenance.lifecycle_state!r}, expected 'reproduction'"
        )

    # 3. Check hash consistency across candidate and reproduction
    hashes = {
        "dataset_sha256": candidate.provenance.dataset_sha256,
        "contract_sha256": candidate.provenance.contract_sha256,
        "feature_schema_sha256": candidate.provenance.feature_schema_sha256,
        "source_git_sha": candidate.provenance.source_git_sha,
        "champion_package_sha256": candidate.provenance.champion_package_sha256,
        "alert_policy_sha256": candidate.provenance.alert_policy_sha256,
    }

    if reproduction.provenance.dataset_sha256 != hashes["dataset_sha256"]:
        reasons.append("Dataset SHA-256 mismatch between candidate and reproduction")
    if reproduction.provenance.contract_sha256 != hashes["contract_sha256"]:
        reasons.append("Contract SHA-256 mismatch between candidate and reproduction")
    if reproduction.provenance.feature_schema_sha256 != hashes["feature_schema_sha256"]:
        reasons.append("Feature schema SHA-256 mismatch between candidate and reproduction")
    if reproduction.provenance.champion_package_sha256 != hashes["champion_package_sha256"]:
        reasons.append("Champion package SHA-256 mismatch between candidate and reproduction")
    if reproduction.provenance.source_git_sha != hashes["source_git_sha"]:
        reasons.append("Source Git SHA mismatch between candidate and reproduction")
    if reproduction.provenance.alert_policy_sha256 != hashes["alert_policy_sha256"]:
        reasons.append("Alert policy SHA-256 mismatch between candidate and reproduction")

    if candidate.package_manifest_sha256 != hashes["champion_package_sha256"]:
        reasons.append("Package manifest SHA-256 mismatch in candidate result")

    # 4. Check numerical reproducibility tolerances
    th_delta = abs(float(reproduction.threshold) - float(expected_threshold))
    if th_delta > THRESHOLD_TOLERANCE:
        reasons.append(
            f"Threshold delta {th_delta:.12e} exceeds tolerance {THRESHOLD_TOLERANCE:.12e}"
        )

    max_golden_delta = 0.0
    if len(reproduction.golden_scores) != len(expected_golden_scores):
        reasons.append(
            f"Golden score count mismatch: got {len(reproduction.golden_scores)}, expected {len(expected_golden_scores)}"
        )
    else:
        for actual, exp in zip(reproduction.golden_scores, expected_golden_scores, strict=True):
            delta = abs(float(actual) - float(exp))
            if delta > max_golden_delta:
                max_golden_delta = delta
        if max_golden_delta > SCORE_TOLERANCE:
            reasons.append(
                f"Golden scores max delta {max_golden_delta:.12e} exceeds tolerance {SCORE_TOLERANCE:.12e}"
            )

    verdict: Literal["PASS", "FAIL"] = "PASS" if len(reasons) == 0 else "FAIL"

    return Phase7GateResult(
        schema_version="phase7-gate-v1",
        source_git_sha=candidate.provenance.source_git_sha,
        timestamp=datetime.now(UTC).isoformat(),
        verdict=verdict,
        threshold_delta=th_delta,
        golden_scores_max_delta=max_golden_delta,
        candidate_run_id=candidate.run_id,
        reproduction_run_id=reproduction.run_id,
        verified_hashes=hashes,
        package_manifest_sha256=hashes["champion_package_sha256"],
        alert_policy_sha256=hashes["alert_policy_sha256"],
        reasons=reasons,
        self_sha256="",
    ).with_computed_hash()


def write_phase7_gate_report(path: Path, result: Phase7GateResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    res_with_hash = result.with_computed_hash()
    content = canonical_dumps(res_with_hash.to_dict())
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def run_phase7_gate(
    *,
    champion_package: Path,
    features_path: Path,
    phase1b_run_dir: Path,
    output_dir: Path | None = None,
    tracking_uri: str | None = None,
    expected_source_git_sha: str | None = None,
    alert_policy_path: Path | None = None,
    mlflow_client: Any = None,
) -> Phase7GateResult:
    from industrial_reliability.ml_lifecycle import (
        ImportCandidateRequest,
        ReproductionRequest,
        import_candidate,
        reproduce_candidate,
    )

    manifest_file = champion_package / "manifest.json"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Champion package manifest not found at {manifest_file}")

    manifest = ChampionManifest.model_validate_json(manifest_file.read_text(encoding="utf-8"))

    # Load golden cases
    golden_file = champion_package / "golden-cases.json"
    golden_data = json.loads(golden_file.read_text(encoding="utf-8"))
    expected_golden = [case["expected_score"] for case in golden_data.get("cases", [])]

    # Run import
    cand_res = import_candidate(
        ImportCandidateRequest(
            champion_package=champion_package,
            phase1b_run_dir=phase1b_run_dir,
            expected_source_git_sha=expected_source_git_sha,
            alert_policy_path=alert_policy_path,
            tracking_uri=tracking_uri,
        ),
        mlflow_client=mlflow_client,
    )

    # Run reproduction
    repro_res = reproduce_candidate(
        ReproductionRequest(
            features_path=features_path,
            phase1b_run_dir=phase1b_run_dir,
            champion_package=champion_package,
            expected_source_git_sha=expected_source_git_sha,
            alert_policy_path=alert_policy_path,
            tracking_uri=tracking_uri,
        ),
        mlflow_client=mlflow_client,
    )

    gate_result = evaluate_phase7_gate(
        candidate=cand_res,
        reproduction=repro_res,
        expected_threshold=float(manifest.threshold),
        expected_golden_scores=expected_golden,
    )

    if output_dir:
        report_file = output_dir / gate_result.source_git_sha / "phase7-gate.json"
        write_phase7_gate_report(report_file, gate_result)

    return gate_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 7 Reproducibility & Lineage Gate")
    parser.add_argument("--champion-package", type=Path, required=True)
    parser.add_argument("--features-path", type=Path, required=True)
    parser.add_argument("--phase1b-run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/phase7"))
    parser.add_argument("--tracking-uri", type=str, default=None)
    parser.add_argument("--expected-source-git-sha", type=str, default=None)
    parser.add_argument("--alert-policy", type=Path, default=None)

    args = parser.parse_args(argv)
    result = run_phase7_gate(
        champion_package=args.champion_package,
        features_path=args.features_path,
        phase1b_run_dir=args.phase1b_run_dir,
        output_dir=args.output_dir,
        tracking_uri=args.tracking_uri,
        expected_source_git_sha=args.expected_source_git_sha,
        alert_policy_path=args.alert_policy,
    )
    print(f"Phase 7 Gate Verdict: {result.verdict}")
    if result.reasons:
        for r in result.reasons:
            print(f" - {r}")
    return 0 if result.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
