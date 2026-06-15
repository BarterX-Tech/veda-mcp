from __future__ import annotations

import threading
from dataclasses import dataclass, field

from veda._transport import tier_capabilities
from veda.config import get_scraping_config


@dataclass
class ToolMetrics:
    calls: int = 0
    successes: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    routes: dict[str, int] = field(default_factory=dict)
    error_codes: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        avg = self.total_latency_ms / self.calls if self.calls else 0.0
        return {
            "calls": self.calls,
            "successes": self.successes,
            "errors": self.errors,
            "avg_latency_ms": round(avg, 3),
            "routes": dict(sorted(self.routes.items())),
            "error_codes": dict(sorted(self.error_codes.items())),
        }


_lock = threading.Lock()
_tools: dict[str, ToolMetrics] = {}


def reset() -> None:
    with _lock:
        _tools.clear()


def record(
    tool: str,
    *,
    route: str,
    outcome: str,
    latency_ms: float,
    error_code: str | None = None,
) -> None:
    with _lock:
        metrics = _tools.setdefault(tool, ToolMetrics())
        metrics.calls += 1
        metrics.total_latency_ms += latency_ms
        metrics.routes[route] = metrics.routes.get(route, 0) + 1
        if outcome == "success":
            metrics.successes += 1
        else:
            metrics.errors += 1
            if error_code:
                metrics.error_codes[error_code] = metrics.error_codes.get(error_code, 0) + 1


def snapshot() -> dict:
    with _lock:
        tools = {name: metrics.as_dict() for name, metrics in sorted(_tools.items())}

    route_totals: dict[str, int] = {}
    total_calls = 0
    total_successes = 0
    total_errors = 0
    blocked = 0
    for metrics in tools.values():
        total_calls += metrics["calls"]
        total_successes += metrics["successes"]
        total_errors += metrics["errors"]
        blocked += metrics["error_codes"].get("blocked", 0)
        for route, count in metrics["routes"].items():
            route_totals[route] = route_totals.get(route, 0) + count

    error_ratio = round(total_errors / max(total_calls, 1), 3)
    status = _verdict(total_calls=total_calls, blocked=blocked, error_ratio=error_ratio)

    return {
        "status": status,
        "tools": tools,
        "routes": dict(sorted(route_totals.items())),
        "json_vs_html": {
            "json": route_totals.get("json", 0),
            "html": route_totals.get("html", 0),
            "html_ratio": round(
                route_totals.get("html", 0)
                / max(route_totals.get("json", 0) + route_totals.get("html", 0), 1),
                3,
            ),
        },
        "totals": {
            "calls": total_calls,
            "successes": total_successes,
            "errors": total_errors,
            "blocked": blocked,
            "error_ratio": error_ratio,
        },
        "scraping_config": get_scraping_config().as_dict(),
        "tiers_available": tier_capabilities(),
    }


def _verdict(*, total_calls: int, blocked: int, error_ratio: float) -> str:
    """Derive a health verdict so callers can threshold on it.

    A liveness check (the server answering at all) only proves the process is up
    — it stays green during a reddit-wide 403/Cloudflare block while every read
    fails. Surface that here so a preflight can distinguish "up" from "actually
    fetching". Counters are cumulative since process start / last reset(), so a
    long-lived process should reset() periodically for a recent signal.

    - ``idle``: no calls recorded yet (nothing to judge).
    - ``blocked``: ``blocked`` errors dominate — reddit is refusing reads.
    - ``degraded``: high overall error ratio (not predominantly blocking).
    - ``ok``: healthy.
    """
    if total_calls == 0:
        return "idle"
    if blocked and blocked / total_calls >= 0.5:
        return "blocked"
    if error_ratio >= 0.5:
        return "degraded"
    return "ok"
