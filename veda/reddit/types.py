from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


class Rule(TypedDict, total=False):
    short_name: str
    description: str


class Post(TypedDict):
    title: str
    author: str
    subreddit: str
    subreddit_prefixed: str
    score: int
    upvote_ratio: float
    num_comments: int
    created_utc: float
    permalink: str
    url: str
    selftext: str
    link_flair: str | None
    is_self: bool
    over_18: bool
    locked: bool
    archived: bool


class Comment(TypedDict):
    id: str
    author: str
    body: str
    score: int
    created_utc: float
    depth: int
    parent_id: str
    permalink: str
    is_op: bool
    edited: bool
    gilded: int
    replies: list[Comment]
    _type: NotRequired[str]
    count: NotRequired[int]
    more_ids: NotRequired[list[str]]
    _note: NotRequired[str]


class ThreadMeta(TypedDict, total=False):
    scraped_at: str
    source_url: str
    json_url: str
    comments_fetched: int
    comments_collapsed: int
    sort: str
    route: Literal["json", "html"]
    note: str


class ThreadResult(TypedDict):
    post: Post
    comments: list[Comment]
    subreddit_rules: list[Rule]
    meta: ThreadMeta


class UserPost(TypedDict):
    type: Literal["post"]
    subreddit: str
    title: str
    score: int
    created_utc: float
    permalink: str


class UserComment(TypedDict):
    type: Literal["comment"]
    subreddit: str
    body: str
    score: int
    created_utc: float
    permalink: str


class UserResult(TypedDict):
    username: str
    bio: str | None
    links: list[str]
    post_karma: int | None
    comment_karma: int | None
    created_utc: float | None
    posts: list[UserPost]
    comments: list[UserComment]




class ExternalDoc(TypedDict):
    url: str
    status: int
    route: str
    content_type: str
    text: str
    title: str | None
    truncated: bool


JsonDict = dict[str, Any]
