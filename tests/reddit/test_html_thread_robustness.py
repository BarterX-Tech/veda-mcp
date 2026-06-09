from __future__ import annotations

from veda.reddit import _html_thread
from veda.reddit.thread import _normalize_html_comments, count_stats

ROBUST_HTML = """
<html><body>
<div class="thing link self over18 locked archived" data-author="op"
     data-subreddit="macapps" data-timestamp="1710000000000"
     data-permalink="/r/macapps/comments/abc/post/">
  <a class="title" href="https://old.reddit.com/r/macapps/comments/abc/post/">Title</a>
  <span class="linkflairlabel" title="Promo">Promo</span>
  <span class="score likes" title="99">99</span>
  <a class="comments">8 comments</a>
  <div class="entry"><div class="usertext-body"><div class="md"><p>body</p></div></div></div>
</div>
<div class="commentarea"><div class="sitetable nestedlisting">
  <div class="thing comment" data-author="alice" data-fullname="t1_c1"
       data-parent="t3_abc" data-timestamp="1710000100000">
    <div class="entry">
      <span class="score likes" title="10">10</span>
      <span class="score unvoted" title="7">7</span>
      <span class="stickied-tag">stickied</span>
      <div class="usertext-body"><div class="md"><p>kept</p></div></div>
    </div>
    <div class="child"><div class="sitetable listing">
      <div class="thing morechildren"><span class="morecomments"><a>4 more replies</a></span></div>
    </div></div>
  </div>
  <div class="thing comment" data-author="[deleted]" data-fullname="t1_c2">
    <div class="entry"><div class="usertext-body"><div class="md"><p>[deleted]</p></div></div></div>
  </div>
  <div class="thing morechildren"><span class="morecomments"><a>3 more comments</a></span></div>
</div></div>
</body></html>
"""


def test_html_thread_handles_flags_deleted_and_more_nodes() -> None:
    parsed = _html_thread.parse_thread_html(ROBUST_HTML)

    assert parsed["post"]["score"] == 99
    assert parsed["post"]["link_flair"] == "Promo"
    assert parsed["post"]["over_18"] is True
    assert parsed["post"]["locked"] is True
    assert parsed["post"]["archived"] is True
    assert parsed["comments"][0]["body"] == "kept"
    assert parsed["comments"][0]["stickied"] is True
    assert parsed["comments"][0]["score"] == 7
    assert parsed["comments"][0]["replies"][0]["_type"] == "more"
    assert parsed["comments"][0]["replies"][0]["count"] == 4
    assert parsed["comments"][1]["_type"] == "more"


def test_html_comment_normalizer_preserves_more_counts() -> None:
    parsed = _html_thread.parse_thread_html(ROBUST_HTML)
    normalized = _normalize_html_comments(parsed["comments"])
    stats = count_stats(normalized)

    assert stats == {"fetched": 1, "collapsed": 7}
