from pathlib import Path

from pr_review.diff import parse_diff
from pr_review.findings import Finding
from pr_review.providers import MockProvider
from pr_review.review import deduplicate, render_markdown, run_review

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.diff"


def _sample_review():
    files = parse_diff(SAMPLE.read_text(encoding="utf-8"))
    return run_review(files, MockProvider())


def test_end_to_end_on_sample_diff():
    review = _sample_review()
    assert review.files == 3
    found = {(f.file, f.line, f.category) for f in review.findings}
    assert ("src/app.py", 3, "security") in found
    assert ("src/app.py", 8, "style") in found
    assert ("src/worker.py", 5, "todo") in found
    # The clean report.py changes produce no findings.
    assert not any(f.file == "src/report.py" for f in review.findings)
    severities = review.counts_by_severity()
    assert severities["high"] == 1
    # Positions are anchored for posting.
    secret = next(f for f in review.findings if f.category == "security")
    assert secret.position == 4


def test_deduplicate():
    f1 = Finding("a.py", 1, "low", "style", "msg")
    f2 = Finding("a.py", 1, "low", "style", "msg")
    f3 = Finding("a.py", 2, "low", "style", "msg")
    assert deduplicate([f1, f2, f3]) == [f1, f3]


def test_render_includes_summary_and_steps():
    md = render_markdown(_sample_review())
    assert md.startswith("# Pull request review")
    assert "1 high" in md
    assert "### src/app.py" in md
    assert "## Suggested next steps" in md
    assert "rotate" in md
    # Secret values never appear in the rendered review.
    assert "sk-live" not in md


def test_render_clean_review():
    files = parse_diff(
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,1 +1,2 @@\n"
        " keep = 1\n"
        "+other = 2\n"
    )
    review = run_review(files, MockProvider())
    assert review.findings == []
    md = render_markdown(review)
    assert "No findings" in md
