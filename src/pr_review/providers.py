"""Model providers: an OpenAI-compatible HTTP provider and a mock.

The mock provider is deterministic and rule based. It exists so the whole
pipeline, and any first-time user of the GitHub Action, can run a real
end-to-end review with no API key and no network. Its findings come from
the checks in this module, including the secret patterns below.

Secret handling rule: a finding names the file, the line, and the kind of
secret. The matched text is never copied into a finding, a log line, or
any output.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .chunking import Chunk
from .findings import Finding

logger = logging.getLogger("pr_review.providers")

MAX_LINE_LENGTH = 120


@dataclass(frozen=True)
class SecretPattern:
    name: str
    regex: re.Pattern


SECRET_PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern(
        "AWS access key id",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    SecretPattern(
        "private key block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    SecretPattern(
        "hardcoded credential assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b"
            r"\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
        ),
    ),
    SecretPattern(
        "bearer token literal",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{20,}"),
    ),
)


def find_secret_kinds(line_text: str) -> list[str]:
    """Return the names of secret patterns matching a line. Never the text."""
    return [p.name for p in SECRET_PATTERNS if p.regex.search(line_text)]


class Provider(Protocol):
    name: str

    def review_chunk(self, prompt: str, chunk: Chunk) -> list[Finding]:
        ...


class MockProvider:
    """Deterministic rule-based provider for tests and dry runs."""

    name = "mock"

    def review_chunk(self, prompt: str, chunk: Chunk) -> list[Finding]:
        findings: list[Finding] = []
        for file_diff, hunk in chunk.parts:
            for line in hunk.lines:
                if line.kind != "add":
                    continue
                findings.extend(self._check_line(file_diff.path, line))
        return findings

    def _check_line(self, path: str, line) -> list[Finding]:
        out: list[Finding] = []
        text = line.content
        for kind in find_secret_kinds(text):
            out.append(
                Finding(
                    file=path,
                    line=line.new_lineno,
                    severity="high",
                    category="security",
                    message=(
                        f"Possible {kind} added in code. Remove it, rotate "
                        "the credential if it was ever real, and load it "
                        "from the environment instead."
                    ),
                    position=line.position,
                )
            )
        stripped = text.strip()
        if re.search(r"(?<![\w.])print\s*\(", text) and not path.startswith(
            ("examples/", "scripts/")
        ):
            out.append(
                Finding(
                    file=path,
                    line=line.new_lineno,
                    severity="low",
                    category="style",
                    message=(
                        "print call added in application code. Use the "
                        "logging module so output can be controlled."
                    ),
                    position=line.position,
                )
            )
        if "TODO" in text or "FIXME" in text:
            out.append(
                Finding(
                    file=path,
                    line=line.new_lineno,
                    severity="low",
                    category="todo",
                    message=(
                        "TODO or FIXME added. Link it to a tracked issue "
                        "or resolve it before merge."
                    ),
                    position=line.position,
                )
            )
        if re.search(r"except\s*:", text) or re.search(
            r"except\s+Exception\s*:\s*$", text
        ):
            out.append(
                Finding(
                    file=path,
                    line=line.new_lineno,
                    severity="medium",
                    category="reliability",
                    message=(
                        "Broad exception handler added. Catch the specific "
                        "exception you expect so real failures stay visible."
                    ),
                    position=line.position,
                )
            )
        if stripped.startswith("import pdb") or "breakpoint()" in text:
            out.append(
                Finding(
                    file=path,
                    line=line.new_lineno,
                    severity="medium",
                    category="style",
                    message="Debugger statement added. Remove it before merge.",
                    position=line.position,
                )
            )
        if len(text) > MAX_LINE_LENGTH:
            out.append(
                Finding(
                    file=path,
                    line=line.new_lineno,
                    severity="low",
                    category="style",
                    message=(
                        f"Line is {len(text)} characters, over the "
                        f"{MAX_LINE_LENGTH} character guide. Long lines "
                        "hide diffs in review."
                    ),
                    position=line.position,
                )
            )
        return out


class OpenAIProvider:
    """Calls any OpenAI-compatible chat completions endpoint."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: int = 60,
        opener=None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> OpenAIProvider:
        api_key = os.environ.get("PR_REVIEW_API_KEY") or os.environ.get(
            "OPENAI_API_KEY"
        )
        if not api_key:
            raise ValueError(
                "no API key found; set PR_REVIEW_API_KEY or OPENAI_API_KEY"
            )
        base_url = os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        model = os.environ.get("PR_REVIEW_MODEL", "gpt-4o-mini")
        return cls(api_key=api_key, model=model, base_url=base_url)

    def review_chunk(self, prompt: str, chunk: Chunk) -> list[Finding]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You review pull request diffs. Reply with a JSON "
                        "array only. Each item has file, line, severity "
                        "(high, medium, or low), category, and message."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self._opener(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        return parse_findings_json(content, chunk)


def parse_findings_json(content: str, chunk: Chunk) -> list[Finding]:
    """Parse a model reply into findings, anchoring positions from the diff."""
    start = content.find("[")
    end = content.rfind("]")
    if start == -1 or end == -1:
        logger.warning("model reply was not a JSON array; ignoring chunk")
        return []
    try:
        items = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("model reply was not valid JSON; ignoring chunk")
        return []
    positions: dict[tuple[str, int], int] = {}
    for file_diff, hunk in chunk.parts:
        for line in hunk.lines:
            if line.new_lineno is not None:
                positions[(file_diff.path, line.new_lineno)] = line.position
    findings: list[Finding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "low"))
        if severity not in ("high", "medium", "low"):
            severity = "low"
        line_no = item.get("line")
        if not isinstance(line_no, int):
            line_no = None
        path = str(item.get("file", ""))
        findings.append(
            Finding(
                file=path,
                line=line_no,
                severity=severity,
                category=str(item.get("category", "general")),
                message=str(item.get("message", "")),
                position=positions.get((path, line_no))
                if line_no is not None
                else None,
            )
        )
    return findings


def get_provider(name: str) -> Provider:
    if name == "mock":
        return MockProvider()
    if name == "openai":
        return OpenAIProvider.from_env()
    raise ValueError(f"unknown provider: {name}")
