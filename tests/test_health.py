from __future__ import annotations

from veda import health


def test_health_records_success_error_routes_and_latency() -> None:
    health.reset()

    health.record("fetch_thread", route="html", outcome="success", latency_ms=12.5)
    health.record("fetch_thread", route="json", outcome="success", latency_ms=7.5)
    health.record("fetch_url", route="tier2", outcome="error", latency_ms=2.0, error_code="blocked")

    snapshot = health.snapshot()

    assert snapshot["totals"]["successes"] == 2
    assert snapshot["totals"]["errors"] == 1
    assert snapshot["routes"]["html"] == 1
    assert snapshot["routes"]["json"] == 1
    assert snapshot["routes"]["tier2"] == 1
    assert snapshot["json_vs_html"] == {"json": 1, "html": 1, "html_ratio": 0.5}
    assert snapshot["tools"]["fetch_thread"]["avg_latency_ms"] == 10.0
    assert snapshot["tools"]["fetch_url"]["error_codes"]["blocked"] == 1
