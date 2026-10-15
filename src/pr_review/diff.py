"""Unified diff parsing with GitHub diff position mapping.

GitHub's review API does not take file line numbers for inline comments. It
takes a "position": the 1-based index of a line inside one file's diff body,
counting the first hunk header as position 1 and every following line,
including later hunk headers, as one more. This module parses a unified diff
and keeps, for every added or context line, both its new-file line number and
its diff position, so findings can be posted back as inline comments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

KIND_CONTEXT = "context"
KIND_ADD = "add"
KIND_DELETE = "delete"
KIND_HUNK = "hunk"


@dataclass
class DiffLine:
    """One line inside a hunk."""

    kind: str
    content: str
    position: int
    old_lineno: int | None = None
    new_lineno: int | None = None

    @property
    def text(self) -> str:
        prefix = {"context": " ", "add": "+", "delete": "-"}.get(self.kind, " ")
        return prefix + self.content


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str = ""
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def header(self) -> str:
        return (
            f"@@ -{self.old_start},{self.old_count} "
            f"+{self.new_start},{self.new_count} @@{self.section}"
        )

    def render(self) -> str:
        parts = [self.header]
        parts.extend(
            line.text for line in self.lines if line.kind != KIND_HUNK
        )
        return "\n".join(parts)


@dataclass
class FileDiff:
    old_path: str | None
    new_path: str | None
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    is_binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def path(self) -> str:
        """The path findings should be reported against."""
        if self.new_path:
            return self.new_path
        return self.old_path or ""

    def position_for_new_line(self, new_lineno: int) -> int | None:
        """Return the diff position for a new-file line number, or None."""
        for hunk in self.hunks:
            for line in hunk.lines:
                if line.new_lineno == new_lineno and line.kind in (
                    KIND_ADD,
                    KIND_CONTEXT,
                ):
                    return line.position
        return None

    def added_lines(self) -> list[DiffLine]:
        out: list[DiffLine] = []
        for hunk in self.hunks:
            for line in hunk.lines:
                if line.kind == KIND_ADD:
                    out.append(line)
        return out

    def render(self) -> str:
        parts = [f"--- a/{self.old_path or '/dev/null'}"]
        parts.append(f"+++ b/{self.new_path or '/dev/null'}")
        parts.extend(hunk.render() for hunk in self.hunks)
        return "\n".join(parts)


def _strip_prefix(path: str) -> str | None:
    path = path.strip()
    if path == "/dev/null":
        return None
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def parse_diff(text: str) -> list[FileDiff]:
    """Parse a unified diff into a list of FileDiff objects."""
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    position = 0
    old_no = 0
    new_no = 0

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            current = FileDiff(old_path=None, new_path=None)
            files.append(current)
            hunk = None
            position = 0
            # "diff --git a/old b/new"
            rest = raw[len("diff --git ") :]
            if rest.startswith("a/") and " b/" in rest:
                old_part, new_part = rest.split(" b/", 1)
                current.old_path = old_part[2:]
                current.new_path = new_part
            continue
        if current is None:
            continue
        if raw.startswith("new file mode"):
            current.is_new = True
            continue
        if raw.startswith("deleted file mode"):
            current.is_deleted = True
            continue
        if raw.startswith("rename from "):
            current.is_renamed = True
            current.old_path = raw[len("rename from ") :].strip()
            continue
        if raw.startswith("rename to "):
            current.is_renamed = True
            current.new_path = raw[len("rename to ") :].strip()
            continue
        if raw.startswith("Binary files") or raw == "GIT binary patch":
            current.is_binary = True
            continue
        if raw.startswith("--- "):
            current.old_path = _strip_prefix(raw[4:])
            continue
        if raw.startswith("+++ "):
            current.new_path = _strip_prefix(raw[4:])
            continue

        match = HUNK_RE.match(raw)
        if match:
            position += 1
            hunk = Hunk(
                old_start=int(match.group(1)),
                old_count=int(match.group(2) or "1"),
                new_start=int(match.group(3)),
                new_count=int(match.group(4) or "1"),
                section=match.group(5) or "",
            )
            header_line = DiffLine(kind=KIND_HUNK, content=raw, position=position)
            hunk.lines.append(header_line)
            current.hunks.append(hunk)
            old_no = hunk.old_start
            new_no = hunk.new_start
            continue

        if hunk is None:
            # Metadata lines (index, mode changes) carry no position.
            continue

        position += 1
        if raw.startswith("\\"):
            # "\ No newline at end of file" still occupies a diff position.
            hunk.lines.append(
                DiffLine(kind=KIND_CONTEXT, content=raw, position=position)
            )
            continue
        if raw.startswith("+"):
            hunk.lines.append(
                DiffLine(
                    kind=KIND_ADD,
                    content=raw[1:],
                    position=position,
                    new_lineno=new_no,
                )
            )
            new_no += 1
        elif raw.startswith("-"):
            hunk.lines.append(
                DiffLine(
                    kind=KIND_DELETE,
                    content=raw[1:],
                    position=position,
                    old_lineno=old_no,
                )
            )
            old_no += 1
        else:
            content = raw.removeprefix(" ")
            hunk.lines.append(
                DiffLine(
                    kind=KIND_CONTEXT,
                    content=content,
                    position=position,
                    old_lineno=old_no,
                    new_lineno=new_no,
                )
            )
            old_no += 1
            new_no += 1

    return [f for f in files if f.old_path or f.new_path or f.hunks]
