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
    assert snapshot["scraping_config"]["reddit_json_enabled"] is False
    assert snapshot["tools"]["fetch_thread"]["avg_latency_ms"] == 10.0
    assert snapshot["tools"]["fetch_url"]["error_codes"]["blocked"] == 1


def test_health_verdict_is_idle_with_no_calls() -> None:
    health.reset()
    snapshot = health.snapshot()
    assert snapshot["status"] == "idle"
    assert snapshot["totals"]["blocked"] == 0
    assert snapshot["totals"]["error_ratio"] == 0.0


def test_health_verdict_flags_reddit_blocking() -> None:
    # Process up but reddit refusing reads: liveness is green, verdict is not.
    health.reset()
    health.record("fetch_thread", route="error", outcome="error", latency_ms=1.0, error_code="blocked")
    health.record("fetch_thread", route="error", outcome="error", latency_ms=1.0, error_code="blocked")
    health.record("fetch_thread", route="html", outcome="success", latency_ms=1.0)

    snapshot = health.snapshot()

    assert snapshot["totals"]["blocked"] == 2
    assert snapshot["status"] == "blocked"


def test_health_verdict_ok_when_mostly_succeeding() -> None:
    health.reset()
    for _ in range(9):
        health.record("fetch_thread", route="html", outcome="success", latency_ms=1.0)
    health.record("fetch_thread", route="error", outcome="error", latency_ms=1.0, error_code="exception")

    assert health.snapshot()["status"] == "ok"
