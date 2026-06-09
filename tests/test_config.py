from __future__ import annotations

from veda.config import get_scraping_config


def test_scraping_config_defaults_disable_reddit_json(monkeypatch) -> None:
    for name in (
        "VEDA_REDDIT_JSON_ENABLED",
        "VEDA_REDDIT_HTML_ENABLED",
        "VEDA_EXTERNAL_GITHUB_RAW_ENABLED",
        "VEDA_EXTERNAL_TIER1_ENABLED",
        "VEDA_EXTERNAL_TIER2_ENABLED",
        "VEDA_EXTERNAL_TIER3_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    config = get_scraping_config()

    assert config.reddit_json_enabled is False
    assert config.reddit_html_enabled is True
    assert config.external_github_raw_enabled is True
    assert config.external_tier_enabled("tier1") is True
    assert config.external_tier_enabled("tier2") is True
    assert config.external_tier_enabled("tier3") is True


def test_scraping_config_parses_env_flags(monkeypatch) -> None:
    monkeypatch.setenv("VEDA_REDDIT_JSON_ENABLED", "yes")
    monkeypatch.setenv("VEDA_REDDIT_HTML_ENABLED", "off")
    monkeypatch.setenv("VEDA_EXTERNAL_TIER2_ENABLED", "0")

    config = get_scraping_config()

    assert config.reddit_json_enabled is True
    assert config.reddit_html_enabled is False
    assert config.external_tier_enabled("tier2") is False
