"""Tests for optional-skills/social-media/reddit-reading/scripts/reddit.py — backend selection and throttle handling."""

import io
import sys
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "optional-skills" / "social-media" / "reddit-reading" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import reddit

THREAD_ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><author><name>/u/op</name></author><title>Post title</title>
  <link href="https://www.reddit.com/r/test/comments/abc123/post_title/"/><updated>2026-09-01T00:00:00+00:00</updated>
  <content type="html">&lt;div&gt;body text&lt;/div&gt; submitted by /u/op [link] [comments]</content></entry>
<entry><author><name>/u/c1</name></author><title>/u/c1 on Post title</title>
  <link href="https://www.reddit.com/r/test/comments/abc123/post_title/k1/"/><updated>2026-09-01T01:00:00+00:00</updated>
  <content type="html">&lt;p&gt;first comment&lt;/p&gt;</content></entry>
</feed>"""


def _http_error(code, headers):
    return urllib.error.HTTPError("https://www.reddit.com/x", code, "msg", headers, io.BytesIO(b""))


def test_anonymous_thread_uses_atom_feed_and_waits_out_a_429_exactly_once(monkeypatch):
    """Without OAuth credentials the .rss endpoint is used; a 429 sleeps for x-ratelimit-reset and retries once,
    and the parsed thread separates the post from its comments with feed noise stripped."""
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    assert reddit.oauth_credentials() is None

    calls = []
    sleeps = []

    class Resp(io.BytesIO):
        headers = {"x-ratelimit-remaining": "0.0"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if len(calls) == 1:
            raise _http_error(429, {"x-ratelimit-reset": "7"})
        return Resp(THREAD_ATOM)

    with mock.patch.object(reddit.urllib.request, "urlopen", fake_urlopen), \
         mock.patch.object(reddit.time, "sleep", sleeps.append):
        post = reddit.atom_thread("test", "abc123", limit=10)

    assert calls[0].startswith("https://www.reddit.com/r/test/comments/abc123/.rss") and len(calls) == 2
    assert sleeps == [8]  # reset + 1s margin, one retry only
    assert post["title"] == "Post title" and post["author"] == "op"
    assert post["body"] == "body text"  # "submitted by … [link] [comments]" footer stripped
    assert [c["author"] for c in post["comments"]] == ["c1"]

    # a second 429 after the retry propagates instead of looping
    with mock.patch.object(reddit.urllib.request, "urlopen", side_effect=_http_error(429, {})), \
         mock.patch.object(reddit.time, "sleep", lambda s: None), pytest.raises(urllib.error.HTTPError):
        reddit._get("https://www.reddit.com/r/test/.rss")


def test_oauth_credentials_route_to_oauth_host_and_flatten_nested_comments(monkeypatch):
    """With REDDIT_CLIENT_ID/SECRET the script talks to oauth.reddit.com with a bearer token and
    returns nested comments flattened with depth and scores — data the anonymous path cannot provide."""
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "sec")
    assert reddit.oauth_credentials() == ("cid", "sec")

    listing = [
        {"data": {"children": [{"kind": "t3", "data": {"title": "T", "author": "op", "subreddit": "test", "score": 42,
                                                      "num_comments": 2, "created_utc": 1.0, "permalink": "/r/test/comments/abc123/t/",
                                                      "is_self": True, "url": "https://www.reddit.com/r/test/comments/abc123/t/", "selftext": "s"}}]}},
        {"data": {"children": [{"kind": "t1", "data": {"author": "a", "score": 5, "body": "top", "permalink": "/p/1",
                                                      "replies": {"data": {"children": [{"kind": "t1", "data": {"author": "b", "score": 1, "body": "reply", "replies": ""}}]}}}},
                               {"kind": "more", "data": {}}]}},
    ]
    seen = {}

    def fake_api(path, token, **params):
        seen["path"], seen["token"] = path, token
        return listing

    with mock.patch.object(reddit, "_api", fake_api):
        post = reddit.api_thread("tok", "test", "abc123", limit=10)

    assert seen == {"path": "/r/test/comments/abc123", "token": "tok"}
    assert post["score"] == 42 and post["url"] == "https://www.reddit.com/r/test/comments/abc123/t/"
    assert [(c["author"], c["depth"], c["score"]) for c in post["comments"]] == [("a", 0, 5), ("b", 1, 1)]

    # the bearer header actually reaches the OAuth host
    captured = {}

    def fake_get(url, headers=None, retry_on_429=True):
        captured["url"], captured["headers"] = url, headers
        return b'{"data": {"children": []}}', {}

    with mock.patch.object(reddit, "_get", fake_get):
        reddit._api("/r/test/hot", "tok", limit=1)
    assert captured["url"].startswith("https://oauth.reddit.com/r/test/hot?")
    assert captured["headers"]["Authorization"] == "Bearer tok"


def _coverage_comment(body, replies=""):
    return {"kind": "t1", "data": {"author": "fixture", "body": body,
                                      "replies": replies, "score": 1}}


@pytest.mark.parametrize("body, children, limit, expected", [
    ("汉🙂" * 2001, [_coverage_comment("a", {"data": {"children": [
        _coverage_comment("c" * 4001), {"kind": "more", "data": {"count": 0}}]}}),
        _coverage_comment("b"), {"kind": "t9"}], 2, (3, 2, 1, 1, 1, True)),
    ("short", [_coverage_comment("ok")], 40, (1, 1, 0, 0, 0, None)),
    (None, [], 40, (0, 0, 0, 0, 0, None)),
])
def test_json_coverage_oauth_thread(monkeypatch, capsys, body, children, limit, expected):
    """The CLI must expose local loss without certifying a full thread."""
    monkeypatch.setattr(reddit, "oauth_credentials", lambda: ("synthetic", "synthetic"))
    monkeypatch.setattr(reddit, "oauth_token", lambda *args: "synthetic-token")
    seen = []

    def fake_api(path, token, **params):
        seen.append((path, params))
        return [{"data": {"children": [{"kind": "t3", "data": {
            "selftext": body, "title": "Synthetic", "num_comments": 99}}]}},
            {"data": {"children": children}}]

    monkeypatch.setattr(reddit, "_api", fake_api)
    assert reddit.main(["--json", "thread", "https://www.reddit.com/r/test/comments/abc123/",
                        "--limit", str(limit)]) == 0
    import json
    result = json.loads(capsys.readouterr().out)
    original = body or ""
    assert result["body"] == original[:4000]
    assert type(result["body_length"]) is int and result["body_length"] == len(original)
    assert type(result["body_returned_length"]) is int
    assert result["body_returned_length"] == len(result["body"])
    assert result["body_truncated"] is (len(original) > 4000)
    cov = result["comments_coverage"]
    assert cov["backend"] == "oauth" and cov["scope"] == "single_api_response"
    assert (cov["available_in_response"], cov["returned"], cov["omitted_by_limit"],
            cov["more_nodes"], cov["skipped_nodes"], cov["has_more"]) == expected
    assert cov["has_more"] is expected[-1]
    assert cov["full_thread_verified"] is False
    assert cov["limit_truncated"] is (expected[2] > 0)
    assert seen == [("/r/test/comments/abc123", {"limit": limit, "depth": 10, "sort": "top"})]
    for comment in result["comments"]:
        assert type(comment["body_length"]) is int
        assert comment["body_returned_length"] == len(comment["body"])
        assert comment["body_truncated"] is (comment["body_length"] > 4000)
    if expected[-1]:
        assert [(c["body"][:1], c["depth"]) for c in result["comments"]] == [("a", 0), ("c", 1)]
    if not children:
        assert result["comments"] == []


@pytest.mark.parametrize("bodies, limit", [(["汉" * 4001, "long " * 1001, "short"], 1),
                                           (["short", "ok"], 40), (["post only"], 40)])
def test_json_coverage_atom_thread(monkeypatch, capsys, bodies, limit):
    """Feed output is normalized and advisory, including post-only results."""
    from xml.sax.saxutils import escape
    import json
    raw = ('<feed xmlns="http://www.w3.org/2005/Atom">' + ''.join(
        '<entry><title>Synthetic</title><content type="html">' + escape(b) +
        '</content></entry>' for b in bodies) + '</feed>').encode()
    monkeypatch.setattr(reddit, "oauth_credentials", lambda: None)
    calls = []

    def fake_get(url, *args, **kwargs):
        calls.append(url)
        return raw, {}

    monkeypatch.setattr(reddit, "_get", fake_get)
    assert reddit.main(["--json", "thread", "https://www.reddit.com/r/test/comments/abc123/",
                        "--limit", str(limit)]) == 0
    result = json.loads(capsys.readouterr().out)
    cov = result["comments_coverage"]
    assert cov["backend"] == "anonymous-atom" and cov["scope"] == "single_feed_response"
    assert cov["has_more"] is None and cov["full_thread_verified"] is False
    assert cov["limit_is_advisory"] is True and cov["limit_truncated"] is False
    assert cov["scores_available"] is False and cov["nesting_available"] is False
    assert cov["returned"] == cov["available_in_response"] == len(bodies) - 1
    assert cov["omitted_by_limit"] == 0 and cov["requested_limit"] == limit
    assert calls == [f"https://www.reddit.com/r/test/comments/abc123/.rss?limit={limit}"]
    for entry, original in zip([result] + result["comments"], bodies):
        normalized = reddit.strip_html(original)
        assert entry["body"] == normalized[:4000]
        assert entry["body_length"] == len(normalized)
        assert entry["body_returned_length"] == len(entry["body"])
        assert entry["body_truncated"] is (len(normalized) > 4000)
        assert entry["coverage"]["full_content_verified"] is False


@pytest.mark.parametrize("oauth", [False, True])
def test_json_coverage_empty_listing(monkeypatch, capsys, oauth):
    """No new result envelope or false completeness claim for no matches."""
    monkeypatch.setattr(reddit, "oauth_credentials", lambda: ("synthetic", "synthetic") if oauth else None)
    monkeypatch.setattr(reddit, "oauth_token", lambda *args: "synthetic-token")
    monkeypatch.setattr(reddit, "_api", lambda *args, **kwargs: {"data": {"children": []}})
    monkeypatch.setattr(reddit, "_get", lambda *args, **kwargs: (
        b'<feed xmlns="http://www.w3.org/2005/Atom"/>', {}))
    assert reddit.main(["--json", "search", "synthetic"]) == 0
    assert capsys.readouterr().out.strip() == "[]"


def test_json_coverage_empty_atom_thread_error(monkeypatch):
    monkeypatch.setattr(reddit, "oauth_credentials", lambda: None)
    monkeypatch.setattr(reddit, "_get", lambda *args, **kwargs: (
        b'<feed xmlns="http://www.w3.org/2005/Atom"/>', {}))
    with pytest.raises(SystemExit, match="thread feed returned no entries"):
        reddit.main(["--json", "thread", "https://www.reddit.com/r/test/comments/abc123/"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
