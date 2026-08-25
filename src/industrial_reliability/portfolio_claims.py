from __future__ import annotations

from typing import Any


def generate_portfolio_claims(metrics: dict[str, Any]) -> dict[str, Any]:
    detected = metrics.get("detected_events", 0)
    total = metrics.get("total_events", 1)
    rate = (detected / total) * 100 if total > 0 else 0.0

    return {
        "event_detection_rate": f"{rate:.1f}% ({detected}/{total} events)",
        "false_alarm_rate": f"{metrics.get('false_episodes_per_day', 0.0):.2f} false episodes/day",
        "lead_time_summary": f"{metrics.get('lead_time_seconds_p50', 0)}s median lead time",
        "pr_auc": f"{metrics.get('pr_auc', 0.0):.4f}",
        "unsupported_claims": [],
    }
