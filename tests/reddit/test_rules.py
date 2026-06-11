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


MODTOOLS_RULES_HTML = """
<html><body class="modtools-page">
  <div class="subreddit-rule-item" data-priority="0"
       data-description="Search before posting. Choose flair."
       data-violation-reason="Read Before Posting" data-kind="link">
    <div class="subreddit-rule "><div class="subreddit-rule-contents">
      <div class="subreddit-rule-content-number">1</div>
    </div></div>
  </div>
  <div class="subreddit-rule-item" data-priority="1"
       data-description="No referral or affiliate links."
       data-violation-reason="No Affiliate Links" data-kind="all">
    <div class="subreddit-rule "></div>
  </div>
</body></html>
"""


def test_parse_rules_html_reads_modtools_data_attributes() -> None:
    # Current old.reddit /about/rules/ markup: subreddit-rule-item divs with
    # the rule content in data attributes, no short-name/description classes.
    result = rules._parse_rules_html(MODTOOLS_RULES_HTML)

    assert result == [
        {
            "short_name": "Read Before Posting",
            "description": "Search before posting. Choose flair.",
        },
        {"short_name": "No Affiliate Links", "description": "No referral or affiliate links."},
    ]


def test_fetch_rules_uses_json_when_populated(monkeypatch) -> None:
    monkeypatch.setenv("VEDA_REDDIT_JSON_ENABLED", "1")

    result = rules.fetch_rules(
        "macapps",
        json_fetcher=lambda subreddit: [{"short_name": "A", "description": "B"}],
        html_fetcher=lambda url: [],
    )

    assert result == [{"short_name": "A", "description": "B"}]
