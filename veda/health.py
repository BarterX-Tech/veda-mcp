from __future__ import annotations

import threading
from dataclasses import dataclass, field


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
    for metrics in tools.values():
        total_calls += metrics["calls"]
        total_successes += metrics["successes"]
        total_errors += metrics["errors"]
        for route, count in metrics["routes"].items():
            route_totals[route] = route_totals.get(route, 0) + count

    return {
        "tools": tools,
        "routes": dict(sorted(route_totals.items())),
        "totals": {
            "calls": total_calls,
            "successes": total_successes,
            "errors": total_errors,
        },
    }
