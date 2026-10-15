"""Split a parsed diff into review-sized chunks.

Chunks never split a hunk in half. The one exception is a single hunk that
is larger than the whole token budget on its own; that hunk is split at
line boundaries and the split is logged, because dropping code from a
review silently would be worse.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .diff import FileDiff, Hunk

logger = logging.getLogger("pr_review.chunking")

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token estimate: four characters per token, minimum one."""
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class Chunk:
    """A set of hunks sent to the provider in one request."""

    parts: list[tuple[FileDiff, Hunk]] = field(default_factory=list)
    was_split: bool = False

    @property
    def text(self) -> str:
        blocks = []
        for file_diff, hunk in self.parts:
            blocks.append(f"File: {file_diff.path}\n{hunk.render()}")
        return "\n\n".join(blocks)

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


def _split_hunk(file_diff: FileDiff, hunk: Hunk, max_tokens: int) -> list[Hunk]:
    """Split one oversized hunk at line boundaries.

    Returns synthetic hunks that share the original header counts but hold
    only a slice of the lines. New-file line numbers live on the lines
    themselves, so findings stay correctly anchored after a split.
    """
    logger.warning(
        "hunk in %s (%d tokens) exceeds budget %d; splitting at line boundaries",
        file_diff.path,
        estimate_tokens(hunk.render()),
        max_tokens,
    )
    body = [line for line in hunk.lines if line.kind != "hunk"]
    slices: list[Hunk] = []
    current: list = []
    for line in body:
        trial = current + [line]
        size = estimate_tokens("\n".join(item.text for item in trial))
        if current and size > max_tokens:
            slices.append(_slice_hunk(hunk, current))
            current = [line]
        else:
            current = trial
    if current:
        slices.append(_slice_hunk(hunk, current))
    return slices


def _slice_hunk(original: Hunk, lines: list) -> Hunk:
    return Hunk(
        old_start=original.old_start,
        old_count=original.old_count,
        new_start=original.new_start,
        new_count=original.new_count,
        section=original.section,
        lines=list(lines),
    )


def chunk_diff(files: list[FileDiff], max_tokens: int = 6000) -> list[Chunk]:
    """Pack files and hunks into chunks under the token budget."""
    if max_tokens < 50:
        raise ValueError("max_tokens is too small to review anything")

    # Expand oversized hunks first so packing sees final sizes.
    expanded: list[tuple[FileDiff, Hunk, bool]] = []
    for file_diff in files:
        for hunk in file_diff.hunks:
            if estimate_tokens(hunk.render()) > max_tokens:
                for piece in _split_hunk(file_diff, hunk, max_tokens):
                    expanded.append((file_diff, piece, True))
            else:
                expanded.append((file_diff, hunk, False))

    chunks: list[Chunk] = []
    current = Chunk()
    for file_diff, hunk, was_split in expanded:
        size = estimate_tokens(f"File: {file_diff.path}\n{hunk.render()}")
        if current.parts and current.tokens + size > max_tokens:
            chunks.append(current)
            current = Chunk()
        current.parts.append((file_diff, hunk))
        current.was_split = current.was_split or was_split
    if current.parts:
        chunks.append(current)
    return chunks
