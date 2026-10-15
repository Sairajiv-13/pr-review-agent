# ADR 0001: Composite action packaging and a dry-run default

Status: accepted, 2026-10-15.

## Context

This tool ships in two forms: a Python CLI that a developer runs by hand,
and a GitHub Action that runs inside other people's CI. The action form
drives the packaging decision, because that is where install time, cold
start, and first-run trust are won or lost. A reviewer bot that posts on a
pull request the first time it runs, with no preview, is a bot that gets
removed from the workflow the same day.

## Decision

Ship the action as a composite action. The steps set up Python 3.12,
install this repository as a package with pip, and call the `pr-review`
console script. The action defaults to the mock provider and to dry-run
mode: the review is printed to the job log and nothing is posted. Posting
requires two explicit opt-ins in the consumer workflow, `post: "true"`
and, for model reviews, an API key passed in as an input.

## Alternatives considered

A Docker action pins the whole runtime and behaves the same on every
runner. It also pays an image build or pull on every run, and debugging a
failure means reading through container logs instead of a plain pip
install. For a tool whose runtime is the Python standard library alone,
that weight buys little. A JavaScript action would start faster but means
writing the diff parser twice or shelling out to Python anyway, and the
CLI is the primary artifact, not a wrapper.

Because the action is composite, there is no container image to publish,
so this repository intentionally has no GHCR publish workflow. The
Dockerfile that ships in the repo is for running the CLI itself in a
container, which is a different job.

## Consequences

Install takes seconds and failures read like ordinary Python failures in
the job log. The cost is a dependency on the runner's Python setup action
and on pip resolving the same versions the developer tested with, which
the pyproject lower bounds and the CI matrix (3.11 and 3.12) keep honest.

The dry-run default costs one extra edit before the tool posts anything.
That edit is the point. A team can watch the mock review in the log, then
watch a model review in the log, and only then let it write to the pull
request. Trust in automation is earned in that order.
