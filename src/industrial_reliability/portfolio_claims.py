from __future__ import annotations

from collections.abc import Mapping
from statistics import median
from typing import Any


def generate_portfolio_claims(
    metrics: Mapping[str, Any], model_id: str
) -> dict[str, str | list[str]]:
    models = metrics.get("models")
    if not isinstance(models, Mapping) or model_id not in models:
        raise KeyError(f"unknown model_id: {model_id}")
    model = models[model_id]
    leads = [
        row["lead_seconds_to_source_start"]
        for row in model["event_results"]
        if row["detected"] and row["lead_seconds_to_source_start"] is not None
    ]
    return {
        "event_detection_rate": (
            f"{100 * model['detected_events'] / model['total_events']:.1f}% "
            f"({model['detected_events']}/{model['total_events']} events)"
        ),
        "false_alarm_rate": f"{model['false_episodes_per_day']:.3f} false episodes/day",
        "lead_time_summary": f"{median(leads):.0f}s median lead time",
        "pr_auc": f"{model['pr_auc']:.4f}",
        "operational_verdict": str(metrics["verdict"]),
        "unsupported_claims": [],
    }
