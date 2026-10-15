from pathlib import Path

import pytest

from pr_review.cli import main

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample.diff"


def test_review_diff_dry_run(capsys):
    rc = main(["review-diff", "--file", str(SAMPLE)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "# Pull request review (local diff)" in out
    assert "security" in out
    assert "src/app.py" in out


def test_review_diff_missing_file(capsys):
    rc = main(["review-diff", "--file", "/nonexistent/nope.diff"])
    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_review_diff_empty_file(tmp_path, capsys):
    empty = tmp_path / "empty.diff"
    empty.write_text("not a diff at all\n")
    rc = main(["review-diff", "--file", str(empty)])
    assert rc == 1
    assert "No files found" in capsys.readouterr().err


def test_bad_subcommand_is_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        main(["frobnicate"])
    assert excinfo.value.code == 2


def test_review_requires_token(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    rc = main(["review", "--repo", "owner/repo", "--pr", "1"])
    assert rc == 1
    assert "GITHUB_TOKEN" in capsys.readouterr().err
