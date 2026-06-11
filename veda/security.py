from __future__ import annotations

import ipaddress
import socket
from collections import deque
from threading import Lock
from time import monotonic
from urllib.parse import urlparse

from veda.errors import Blocked

_BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}
# Cloud-metadata endpoints are link-local (already non-global), but blocking
# them by name is defense-in-depth against an is_global regression.
_BLOCKED_IPS = {"169.254.169.254", "fd00:ec2::254", "100.100.100.200"}


def _is_internal_ip(value: str) -> bool:
    if value in _BLOCKED_IPS:
        return True
    ip = ipaddress.ip_address(value)
    return not ip.is_global


def validate_public_http_url(url: str, *, resolver=socket.getaddrinfo) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise Blocked(f"unsupported URL scheme for {url}")
    if not parsed.hostname:
        raise Blocked(f"missing URL host for {url}")

    host = parsed.hostname.rstrip(".").lower()
    if host in _BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".local"):
        raise Blocked(f"internal host is not allowed: {host}")

    try:
        if _is_internal_ip(host):
            raise Blocked(f"internal IP is not allowed: {host}")
        return
    except ValueError:
        pass

    try:
        addresses = resolver(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise Blocked(f"could not resolve URL host: {host}") from exc

    seen: set[str] = set()
    for address in addresses:
        ip = str(address[4][0])
        if ip in seen:
            continue
        seen.add(ip)
        if _is_internal_ip(ip):
            raise Blocked(f"internal resolved address is not allowed: {host} -> {ip}")


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._calls: deque[float] = deque()
        self._lock = Lock()

    def check(self) -> None:
        now = monotonic()
        with self._lock:
            while self._calls and now - self._calls[0] >= self.window_seconds:
                self._calls.popleft()
            if len(self._calls) >= self.limit:
                raise Blocked("tool rate limit exceeded", code="rate_limited")
            self._calls.append(now)

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()
