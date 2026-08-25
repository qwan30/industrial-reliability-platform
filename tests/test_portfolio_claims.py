from __future__ import annotations

from industrial_reliability.portfolio_claims import generate_portfolio_claims


def test_claims_strictly_derived_from_actual_metrics() -> None:
    metrics = {
        "dataset": "MetroPT-3",
        "detected_events": 3,
        "total_events": 4,
        "lead_time_seconds_p50": 1800,
        "false_episodes_per_day": 0.42,
        "pr_auc": 0.88,
    }
    claims = generate_portfolio_claims(metrics)
    assert claims["event_detection_rate"] == "75.0% (3/4 events)"
    assert "0.42" in claims["false_alarm_rate"]
    assert "1800" in claims["lead_time_summary"]
    assert claims["unsupported_claims"] == []
