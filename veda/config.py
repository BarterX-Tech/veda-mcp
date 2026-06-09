from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return default


@dataclass(frozen=True)
class ScrapingConfig:
    reddit_json_enabled: bool = False
    reddit_html_enabled: bool = True
    external_github_raw_enabled: bool = True
    external_tier1_enabled: bool = True
    external_tier2_enabled: bool = True
    external_tier3_enabled: bool = True

    def as_dict(self) -> dict[str, bool]:
        return {
            "reddit_json_enabled": self.reddit_json_enabled,
            "reddit_html_enabled": self.reddit_html_enabled,
            "external_github_raw_enabled": self.external_github_raw_enabled,
            "external_tier1_enabled": self.external_tier1_enabled,
            "external_tier2_enabled": self.external_tier2_enabled,
            "external_tier3_enabled": self.external_tier3_enabled,
        }

    def external_tier_enabled(self, tier: str) -> bool:
        return {
            "tier1": self.external_tier1_enabled,
            "tier2": self.external_tier2_enabled,
            "tier3": self.external_tier3_enabled,
        }.get(tier, False)


def get_scraping_config() -> ScrapingConfig:
    return ScrapingConfig(
        reddit_json_enabled=_env_bool("VEDA_REDDIT_JSON_ENABLED", default=False),
        reddit_html_enabled=_env_bool("VEDA_REDDIT_HTML_ENABLED", default=True),
        external_github_raw_enabled=_env_bool("VEDA_EXTERNAL_GITHUB_RAW_ENABLED", default=True),
        external_tier1_enabled=_env_bool("VEDA_EXTERNAL_TIER1_ENABLED", default=True),
        external_tier2_enabled=_env_bool("VEDA_EXTERNAL_TIER2_ENABLED", default=True),
        external_tier3_enabled=_env_bool("VEDA_EXTERNAL_TIER3_ENABLED", default=True),
    )
