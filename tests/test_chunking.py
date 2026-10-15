import pytest

from pr_review.chunking import chunk_diff, estimate_tokens
from pr_review.diff import parse_diff


def _diff_with_hunks(n_hunks: int, lines_per_hunk: int = 2) -> str:
    parts = [
        "diff --git a/app.py b/app.py",
        "index 1111111..2222222 100644",
        "--- a/app.py",
        "+++ b/app.py",
    ]
    line_no = 1
    for _ in range(n_hunks):
        parts.append(f"@@ -{line_no},1 +{line_no},1 @@")
        parts.append(f" line {line_no} stays here")
        parts.append(f"+added line number {line_no} with some text")
        line_no += lines_per_hunk
    return "\n".join(parts) + "\n"


def test_estimate_tokens_minimum():
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) == 10


def test_small_diff_is_one_chunk():
    files = parse_diff(_diff_with_hunks(2))
    chunks = chunk_diff(files, max_tokens=6000)
    assert len(chunks) == 1
    assert chunks[0].was_split is False


def test_packing_respects_budget():
    files = parse_diff(_diff_with_hunks(6))
    budget = 90
    chunks = chunk_diff(files, max_tokens=budget)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.tokens <= budget
    total_parts = sum(len(c.parts) for c in chunks)
    assert total_parts == 6


def test_oversized_hunk_is_split_without_losing_lines():
    body = ["diff --git a/big.py b/big.py", "--- a/big.py", "+++ b/big.py"]
    body.append("@@ -1,1 +1,200 @@")
    body.append(" seed")
    for i in range(2, 201):
        body.append(f"+value {i} = compute_something({i})")
    files = parse_diff("\n".join(body) + "\n")
    chunks = chunk_diff(files, max_tokens=120)
    assert len(chunks) > 1
    assert any(c.was_split for c in chunks)
    added = sum(
        1
        for chunk in chunks
        for _, hunk in chunk.parts
        for line in hunk.lines
        if line.kind == "add"
    )
    assert added == 199


def test_split_chunks_keep_line_numbers():
    body = ["diff --git a/big.py b/big.py", "--- a/big.py", "+++ b/big.py"]
    body.append("@@ -1,1 +1,100 @@")
    body.append(" seed")
    for i in range(2, 101):
        body.append(f"+v{i} = {i}")
    files = parse_diff("\n".join(body) + "\n")
    chunks = chunk_diff(files, max_tokens=100)
    numbers = set()
    for chunk in chunks:
        for _, hunk in chunk.parts:
            for line in hunk.lines:
                if line.kind == "add":
                    numbers.add(line.new_lineno)
    assert numbers == set(range(2, 101))


def test_budget_floor():
    files = parse_diff(_diff_with_hunks(1))
    with pytest.raises(ValueError):
        chunk_diff(files, max_tokens=10)
