"""Shared finding types used by providers and the review renderer."""

from __future__ import annotations

from dataclasses import dataclass

SEVERITIES = ("high", "medium", "low")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Finding:
    """One review comment candidate, anchored to a file and a line."""

    file: str
    line: int | None
    severity: str
    category: str
    message: str
    position: int | None = None

    def key(self) -> tuple[str, int | None, str, str]:
        return (self.file, self.line, self.category, self.message)

    def sort_key(self) -> tuple[str, int, int]:
        line = self.line if self.line is not None else 0
        return (self.file, line, SEVERITY_ORDER.get(self.severity, 3))
