from __future__ import annotations

from veda.reddit import rules

RULES_HTML = """
<html><body>
  <div class="rule-item">
    <h2 class="short-name">Be kind</h2>
    <div class="description"><p>No abuse.</p></div>
  </div>
  <section class="rule">
    <strong>No spam</strong>
    <div class="md"><p>Keep promos useful.</p></div>
  </section>
</body></html>
"""


def test_fetch_rules_falls_back_to_html_when_json_empty() -> None:
    result = rules.fetch_rules(
        "r/macapps",
        json_fetcher=lambda subreddit: [],
        html_fetcher=lambda url: RULES_HTML,
    )

    assert result == [
        {"short_name": "Be kind", "description": "No abuse."},
        {"short_name": "No spam", "description": "Keep promos useful."},
    ]


def test_fetch_rules_uses_json_when_populated() -> None:
    result = rules.fetch_rules(
        "macapps",
        json_fetcher=lambda subreddit: [{"short_name": "A", "description": "B"}],
        html_fetcher=lambda url: [],
    )

    assert result == [{"short_name": "A", "description": "B"}]
