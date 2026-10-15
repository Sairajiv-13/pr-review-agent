"""A small GitHub REST client for fetching diffs and posting reviews.

All HTTP goes through one injectable opener so tests can run offline
against recorded payloads.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from .findings import Finding


@dataclass
class GitHubClient:
    token: str
    base_url: str = "https://api.github.com"
    opener: object = None

    def __post_init__(self) -> None:
        if self.opener is None:
            self.opener = urllib.request.urlopen

    def _request(
        self, path: str, accept: str, data: bytes | None = None
    ) -> bytes:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "pr-review-agent",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method="POST" if data is not None else "GET",
        )
        with self.opener(request, timeout=60) as response:
            return response.read()

    def get_pr_diff(self, repo: str, pr_number: int) -> str:
        raw = self._request(
            f"/repos/{repo}/pulls/{pr_number}",
            accept="application/vnd.github.diff",
        )
        return raw.decode("utf-8")

    def post_review(
        self,
        repo: str,
        pr_number: int,
        body: str,
        findings: list[Finding],
        event: str = "COMMENT",
    ) -> dict:
        """Post one review. Findings with a diff position become inline."""
        comments = []
        general: list[Finding] = []
        for finding in findings:
            if finding.position is not None and finding.line is not None:
                comments.append(
                    {
                        "path": finding.file,
                        "position": finding.position,
                        "body": (
                            f"**{finding.severity}** ({finding.category}): "
                            f"{finding.message}"
                        ),
                    }
                )
            else:
                general.append(finding)
        if general:
            extra = ["", "Findings that could not be anchored to a diff line:"]
            for finding in general:
                extra.append(
                    f"- {finding.file}: **{finding.severity}** "
                    f"({finding.category}): {finding.message}"
                )
            body = body + "\n".join(extra) + "\n"
        payload = {"body": body, "event": event, "comments": comments}
        raw = self._request(
            f"/repos/{repo}/pulls/{pr_number}/reviews",
            accept="application/vnd.github+json",
            data=json.dumps(payload).encode("utf-8"),
        )
        return json.loads(raw.decode("utf-8"))
