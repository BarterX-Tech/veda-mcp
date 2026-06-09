from __future__ import annotations

from veda import _transport


def test_transport_html_cache_avoids_repeated_fetch(monkeypatch) -> None:
    _transport.clear_cache()
    calls = {"count": 0}

    def fake_tier(url: str) -> str:
        calls["count"] += 1
        return "<html>ok</html>"

    monkeypatch.setattr(_transport, "_html_tier1", fake_tier)
    monkeypatch.setattr(_transport, "_html_tier2", lambda url: None)
    monkeypatch.setattr(_transport, "_html_tier3", lambda url: None)

    assert _transport.fetch_html("https://example.com") == "<html>ok</html>"
    assert _transport.fetch_html("https://example.com") == "<html>ok</html>"
    assert calls["count"] == 1
    assert _transport.cache_snapshot()["size"] == 1
