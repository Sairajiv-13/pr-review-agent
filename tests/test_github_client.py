import json

from pr_review.findings import Finding
from pr_review.github_client import GitHubClient


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _client(captured, payload=b"{}"):
    def opener(request, timeout=None):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["data"] = request.data
        captured["accept"] = request.headers.get("Accept")
        return FakeResponse(payload)

    return GitHubClient(token="test-token", opener=opener)


def test_get_pr_diff_uses_diff_accept_header():
    captured = {}
    client = _client(captured, payload=b"diff --git a/x b/x\n")
    text = client.get_pr_diff("owner/repo", 7)
    assert text.startswith("diff --git")
    assert captured["url"].endswith("/repos/owner/repo/pulls/7")
    assert captured["accept"] == "application/vnd.github.diff"
    assert captured["method"] == "GET"


def test_post_review_maps_positions_to_comments():
    captured = {}
    client = _client(captured, payload=b'{"id": 42}')
    findings = [
        Finding("a.py", 3, "high", "security", "anchored", position=5),
        Finding("b.py", None, "low", "style", "not anchored"),
    ]
    result = client.post_review("owner/repo", 7, "body", findings)
    assert result["id"] == 42
    payload = json.loads(captured["data"].decode("utf-8"))
    assert payload["event"] == "COMMENT"
    assert payload["comments"] == [
        {"path": "a.py", "position": 5, "body": "**high** (security): anchored"}
    ]
    # Unanchored findings are folded into the body, not dropped.
    assert "not anchored" in payload["body"]
    assert captured["method"] == "POST"
