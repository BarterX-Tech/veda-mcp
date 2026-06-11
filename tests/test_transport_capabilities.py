from __future__ import annotations

from veda import _transport, health


def test_tier_capabilities_reports_each_tier() -> None:
    caps = _transport.tier_capabilities(refresh=True)

    assert set(caps) == {"tier1", "tier2", "tier3"}
    for tier, info in caps.items():
        assert isinstance(info["available"], bool), tier
        assert "detail" in info, tier
    # tier1 is plain requests and must always be available.
    assert caps["tier1"]["available"] is True


def test_tier_capabilities_detects_missing_stealth_dependency(monkeypatch) -> None:
    def broken_probe() -> None:
        raise ModuleNotFoundError("No module named 'curl_cffi'")

    monkeypatch.setattr(_transport, "_probe_tier2", broken_probe)
    monkeypatch.setattr(_transport, "_probe_tier3", broken_probe)

    caps = _transport.tier_capabilities(refresh=True)

    assert caps["tier2"]["available"] is False
    assert "curl_cffi" in caps["tier2"]["detail"]
    assert caps["tier3"]["available"] is False


def test_server_warns_about_unavailable_tiers(monkeypatch, capsys) -> None:
    from veda.mcp import server

    def fake_caps(*, refresh: bool = False):
        return {
            "tier1": {"available": True, "detail": "ok"},
            "tier2": {"available": False, "detail": "ModuleNotFoundError: curl_cffi"},
            "tier3": {"available": True, "detail": "ok"},
        }

    monkeypatch.setattr(server, "tier_capabilities", fake_caps)

    warnings = server.warn_unavailable_tiers()

    assert warnings == ["tier2 unavailable: ModuleNotFoundError: curl_cffi"]
    assert "tier2 unavailable" in capsys.readouterr().err


def test_stealth_fetch_dependencies_are_installed() -> None:
    """Regression guard: scrapling must be installed with its [fetchers] extra.

    Bare `scrapling` leaves StealthyFetcher/DynamicFetcher unimportable and every
    tier2/tier3 fetch silently fails (the 2026-06 external-fetch outage).
    """
    caps = _transport.tier_capabilities(refresh=True)

    assert caps["tier2"]["available"] is True, caps["tier2"]["detail"]
    assert caps["tier3"]["available"] is True, caps["tier3"]["detail"]


def test_server_refuses_non_loopback_bind_without_token(monkeypatch) -> None:
    from veda.mcp import server

    monkeypatch.setenv("VEDA_HOST", "0.0.0.0")
    monkeypatch.delenv("VEDA_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("VEDA_TOKEN_FILE", "/nonexistent/token")

    import pytest

    with pytest.raises(SystemExit):
        server.ensure_safe_bind("0.0.0.0", server._auth_token())


def test_server_allows_loopback_bind_without_token() -> None:
    from veda.mcp import server

    server.ensure_safe_bind("127.0.0.1", None)
    server.ensure_safe_bind("::1", None)


def test_server_allows_non_loopback_bind_with_token() -> None:
    from veda.mcp import server

    server.ensure_safe_bind("0.0.0.0", "some-token")


def test_health_snapshot_includes_tiers_available() -> None:
    health.reset()

    snapshot = health.snapshot()

    assert "tiers_available" in snapshot
    assert set(snapshot["tiers_available"]) == {"tier1", "tier2", "tier3"}
