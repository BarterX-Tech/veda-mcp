from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HealthSnapshot:
    counters: dict[str, int] = field(default_factory=dict)


def snapshot() -> HealthSnapshot:
    return HealthSnapshot()
