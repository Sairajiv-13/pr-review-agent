"""Review orchestration: prompts, finding collection, Markdown output."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .chunking import Chunk, chunk_diff
from .diff import FileDiff
from .findings import SEVERITY_ORDER, Finding
from .providers import Provider

logger = logging.getLogger("pr_review.review")

PROMPT_TEMPLATE = """Review this pull request diff chunk like a senior engineer.

Rules:
- Report only issues you can point at: a real bug risk, a security problem,
  a reliability problem, or a clear style issue a human reviewer would raise.
- One finding per issue. Give the file, the new-file line number, a severity
  (high, medium, or low), a short category, and a message a teammate can
  act on without more context.
- If the chunk has no real issues, return an empty list.

{chunk_text}
"""


NEXT_STEPS = {
    "security": (
        "Remove any credential material from the diff and rotate anything "
        "that was committed, even briefly."
    ),
    "reliability": (
        "Narrow broad exception handling and add a test that exercises "
        "the failure path."
    ),
    "style": (
        "Run the project formatter and linter, then clear the leftover "
        "debug output."
    ),
    "todo": "File issues for the new TODO items or finish them in this PR.",
    "testing": "Add or update tests for the changed behavior.",
    "general": "Address the findings above or reply on the thread with context.",
}


@dataclass
class Review:
    findings: list[Finding] = field(default_factory=list)
    chunks: int = 0
    files: int = 0

    def counts_by_severity(self) -> dict[str, int]:
        counts = {"high": 0, "medium": 0, "low": 0}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts


def build_prompt(chunk: Chunk) -> str:
    return PROMPT_TEMPLATE.format(chunk_text=chunk.text)


def deduplicate(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple] = set()
    out: list[Finding] = []
    for finding in findings:
        key = finding.key()
        if key in seen:
            continue
        seen.add(key)
        out.append(finding)
    return out


def run_review(
    files: list[FileDiff], provider: Provider, max_tokens: int = 6000
) -> Review:
    review = Review(files=len(files))
    all_findings: list[Finding] = []
    chunks = chunk_diff(files, max_tokens=max_tokens)
    review.chunks = len(chunks)
    for chunk in chunks:
        prompt = build_prompt(chunk)
        all_findings.extend(provider.review_chunk(prompt, chunk))
    review.findings = sorted(deduplicate(all_findings), key=lambda f: f.sort_key())
    return review


def render_markdown(review: Review, title: str = "Pull request review") -> str:
    counts = review.counts_by_severity()
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("Automated review by pr-review-agent. Treat every finding as")
    lines.append("a prompt for a human look, not as a verdict.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    if not review.findings:
        lines.append(
            f"No findings across {review.files} file(s) in "
            f"{review.chunks} chunk(s). The configured checks are clean."
        )
        return "\n".join(lines) + "\n"
    lines.append(
        f"{len(review.findings)} finding(s) across {review.files} file(s): "
        f"{counts.get('high', 0)} high, {counts.get('medium', 0)} medium, "
        f"{counts.get('low', 0)} low."
    )
    lines.append("")
    lines.append("## Findings")
    current_file = None
    for finding in review.findings:
        if finding.file != current_file:
            current_file = finding.file
            lines.append("")
            lines.append(f"### {current_file}")
            lines.append("")
        where = f"Line {finding.line}" if finding.line else "File level"
        lines.append(
            f"- **{finding.severity}** ({finding.category}), {where}: "
            f"{finding.message}"
        )
    lines.append("")
    lines.append("## Suggested next steps")
    lines.append("")
    categories = {f.category for f in review.findings}
    ordered = sorted(
        categories,
        key=lambda c: min(
            SEVERITY_ORDER.get(f.severity, 3)
            for f in review.findings
            if f.category == c
        ),
    )
    for category in ordered:
        step = NEXT_STEPS.get(category, NEXT_STEPS["general"])
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)
