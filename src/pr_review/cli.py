"""Command line entry point.

Exit codes: 0 means the review ran (findings are a normal result, not a
failure). 1 means the review could not run (bad diff, network, API). 2
means the command line itself was wrong, via argparse.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .diff import parse_diff
from .github_client import GitHubClient
from .providers import get_provider
from .review import render_markdown, run_review

logger = logging.getLogger("pr_review")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr-review",
        description="AI pull request reviewer. Dry-run by default.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser("review", help="review a GitHub pull request")
    review.add_argument("--repo", required=True, help="owner/name")
    review.add_argument("--pr", required=True, type=int, help="PR number")
    review.add_argument("--provider", default="mock", choices=["mock", "openai"])
    review.add_argument("--max-tokens", type=int, default=6000)
    review.add_argument(
        "--post",
        action="store_true",
        help="post the review to GitHub (default is dry-run)",
    )
    review.add_argument(
        "--dry-run",
        action="store_true",
        help="print the review and post nothing (the default)",
    )

    local = sub.add_parser("review-diff", help="review a local diff file")
    local.add_argument("--file", required=True, help="path to a unified diff")
    local.add_argument("--provider", default="mock", choices=["mock", "openai"])
    local.add_argument("--max-tokens", type=int, default=6000)
    return parser


def _github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise ValueError("set GITHUB_TOKEN to fetch or post to GitHub")
    return token


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "review-diff":
            with open(args.file, encoding="utf-8") as handle:
                diff_text = handle.read()
            files = parse_diff(diff_text)
            if not files:
                print("No files found in diff.", file=sys.stderr)
                return 1
            provider = get_provider(args.provider)
            review = run_review(files, provider, max_tokens=args.max_tokens)
            print(render_markdown(review, title="Pull request review (local diff)"))
            return 0

        if args.command == "review":
            client = GitHubClient(token=_github_token())
            diff_text = client.get_pr_diff(args.repo, args.pr)
            files = parse_diff(diff_text)
            if not files:
                print("The PR diff has no reviewable files.", file=sys.stderr)
                return 1
            provider = get_provider(args.provider)
            review = run_review(files, provider, max_tokens=args.max_tokens)
            title = f"Pull request review: {args.repo}#{args.pr}"
            body = render_markdown(review, title=title)
            if args.post:
                result = client.post_review(
                    args.repo, args.pr, body, review.findings
                )
                print(f"Posted review {result.get('id')} to {args.repo}#{args.pr}")
            else:
                print(body)
                print(
                    "Dry run: nothing was posted. Add --post to publish.",
                    file=sys.stderr,
                )
            return 0
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
