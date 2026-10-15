from pr_review.chunking import chunk_diff
from pr_review.diff import parse_diff
from pr_review.providers import MockProvider, parse_findings_json

DIFF = """\
diff --git a/src/app.py b/src/app.py
index 1234567..89abcde 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,6 @@
 import os
+API_KEY = "sk-live-9f8e7d6c5b4a3210"
+print("boot")
+# TODO: wire this up
 def main():
     pass
"""


def _chunk():
    files = parse_diff(DIFF)
    return chunk_diff(files, max_tokens=6000)[0]


def test_mock_provider_finds_rules():
    findings = MockProvider().review_chunk("prompt", _chunk())
    by_cat = {(f.category, f.line) for f in findings}
    assert ("security", 2) in by_cat
    assert ("style", 3) in by_cat
    assert ("todo", 4) in by_cat
    for finding in findings:
        assert finding.position is not None
        assert "sk-live" not in finding.message


def test_mock_provider_ignores_context_and_deletes():
    diff = """\
diff --git a/a.py b/a.py
index 1111111..2222222 100644
--- a/a.py
+++ b/a.py
@@ -1,2 +1,1 @@
-print("old debug")
 keep = 1
"""
    files = parse_diff(diff)
    chunk = chunk_diff(files, max_tokens=6000)[0]
    assert MockProvider().review_chunk("p", chunk) == []


def test_mock_provider_long_line_and_debugger():
    long_line = "+" + "x = " + ("a" * 130)
    diff = (
        "diff --git a/a.py b/a.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,1 +1,3 @@\n"
        " keep = 1\n"
        f"{long_line}\n"
        "+    breakpoint()\n"
    )
    files = parse_diff(diff)
    chunk = chunk_diff(files, max_tokens=6000)[0]
    findings = MockProvider().review_chunk("p", chunk)
    messages = [f.message for f in findings]
    assert any("characters" in m for m in messages)
    assert any("Debugger" in m for m in messages)


def test_parse_findings_json_anchors_positions():
    chunk = _chunk()
    payload = (
        '[{"file": "src/app.py", "line": 2, "severity": "high",'
        ' "category": "security", "message": "key in code"}]'
    )
    findings = parse_findings_json(payload, chunk)
    assert len(findings) == 1
    assert findings[0].position is not None
    assert findings[0].severity == "high"


def test_parse_findings_json_tolerates_junk():
    chunk = _chunk()
    assert parse_findings_json("no json here", chunk) == []
    assert parse_findings_json("[not valid", chunk) == []
    payload = '[{"file": "x", "line": "NaN", "severity": "weird"}]'
    findings = parse_findings_json(payload, chunk)
    assert findings[0].severity == "low"
    assert findings[0].line is None
