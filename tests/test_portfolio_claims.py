import json
from pathlib import Path

import pytest

from industrial_reliability.portfolio_claims import generate_portfolio_claims


def test_claims_match_committed_phase1b_metrics() -> None:
    metrics = json.loads(Path("docs/results/phase-1b-metrics.json").read_text(encoding="utf-8"))
    claims = generate_portfolio_claims(metrics, "autoencoder")
    assert claims["event_detection_rate"] == "100.0% (4/4 events)"
    assert claims["false_alarm_rate"] == "30.670 false episodes/day"
    assert claims["pr_auc"] == "0.2295"
    assert claims["operational_verdict"] == "NOT FEASIBLE"


def test_claim_generation_rejects_unknown_model() -> None:
    with pytest.raises(KeyError, match="unknown model_id"):
        generate_portfolio_claims({"models": {}}, "missing")

