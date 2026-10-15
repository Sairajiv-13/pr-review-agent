# pr-review-agent

An AI pull request reviewer that runs as a CLI and as a GitHub Action. It
reads a pull request diff, sends it to a model in review-sized chunks, and
brings back findings anchored to the exact diff lines they belong on. Out
of the box it runs in dry-run mode with a deterministic mock provider, so
the first review you see costs nothing, needs no API key, and posts
nothing.

Built by Sai Rajiv Nagula.

## See it run

The repository ships a crafted sample diff (`examples/sample.diff`) with a
hardcoded credential, a stray print, and a TODO, next to clean changes.
This is the actual output of `make demo` on that file:

```text
# Pull request review (local diff)

## Summary

3 finding(s) across 3 file(s): 1 high, 0 medium, 2 low.

## Findings

### src/app.py

- **high** (security), Line 3: Possible hardcoded credential assignment added in code. Remove it, rotate the credential if it was ever real, and load it from the environment instead.
- **low** (style), Line 8: print call added in application code. Use the logging module so output can be controlled.

### src/worker.py

- **low** (todo), Line 5: TODO or FIXME added. Link it to a tracked issue or resolve it before merge.
```

The clean file in the same diff (`src/report.py`) produces no findings,
and the credential value itself never appears anywhere in the output.
Findings name the file, the line, and the kind of problem. Nothing else.

## How the diff position mapping works

GitHub does not let a review comment point at a file line number. Inline
comments take a position: the 1-based index of a line inside one file's
diff body, where the first hunk header counts as position 1 and every
later line, hunk headers included, adds one. The parser in
`src/pr_review/diff.py` tracks that index alongside old and new line
numbers for every line it reads, so a finding on new-file line 3 of the
sample diff resolves to position 4 when it is posted back. Deleted files,
new files, and multi-hunk files all follow the same counting, and the
test suite pins the arithmetic down on crafted diffs.

## Usage

### Local diff, no GitHub involved

```bash
pip install pr-review-agent          # or: pip install .
pr-review review-diff --file changes.diff
```

This prints the Markdown review and always exits 0 when the review ran.
Findings are a result, not a failure.

### A GitHub pull request

```bash
export GITHUB_TOKEN=...              # read access is enough for a dry run
pr-review review --repo owner/name --pr 123
```

Dry run is the default. Add `--post` to publish the review: anchored
findings become inline comments, the rest fold into the review body.

### GitHub Action

Copy `examples/workflow.yml` into `.github/workflows/` in your repo. The
defaults run the mock provider in dry-run mode on every pull request and
print the review to the job log. When you are ready for real comments,
switch the step to the openai provider, pass your key from secrets, and
set `post` to `"true"`. The reasoning behind the packaging and the
dry-run default is written up in
[ADR 0001](docs/adr/0001-action-packaging-and-dry-run-default.md).

### Docker

```bash
docker build -t pr-review-agent .
docker run --rm pr-review-agent review-diff --file /work/changes.diff
```

## Providers

| Setting | mock | openai |
| --- | --- | --- |
| API key | none | `PR_REVIEW_API_KEY` or `OPENAI_API_KEY` |
| Findings come from | fixed rules in `providers.py` | the model, parsed from JSON |
| Network | none | your endpoint |
| Model name | n/a | `PR_REVIEW_MODEL` (default `gpt-4o-mini`) |
| Base URL | n/a | `OPENAI_BASE_URL` (default `https://api.openai.com/v1`) |

The openai provider talks to any OpenAI-compatible chat completions
endpoint, so a self-hosted or gateway model works by setting the base
URL. The mock provider runs the same checks the sample demo shows:
secret patterns (AWS key ids, private key blocks, hardcoded credential
assignments, bearer token literals), broad exception handlers, debugger
statements, leftover print calls, new TODO items, and lines over 120
characters.

## Safety defaults

- Dry run first. Nothing is posted unless `--post` or `post: "true"` is
  set on purpose.
- Secret values are never printed, logged, or copied into a finding.
  A finding reports the file, the line, and the pattern type only.
- The review states in its own header that findings are prompts for a
  human look, not verdicts.

## Limitations

- One pass per chunk. The model sees the diff, not the whole repository,
  so findings that need cross-file context are out of scope for now.
- Findings anchor to added and context lines only. Comments on removed
  lines are not supported, matching what the GitHub API allows.
- The mock provider is a fixed rule set. It is honest about that in its
  name and in this README.

## Development

```bash
make setup    # pip install -e ".[dev]"
make lint     # ruff over src and tests
make test     # pytest with coverage
make demo     # mock review of examples/sample.diff
```

The suite has 36 tests and runs fully offline: the diff parser and its
position arithmetic, chunk budgets and oversized hunk splitting, secret
pattern hits and clean-code misses, the mock provider end to end on a
fixture diff, review rendering, the GitHub client against a fake
transport, and CLI exit codes. Coverage of the package is 89 percent.
CI runs the same checks on Python 3.11 and 3.12.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Sai Rajiv Nagula.
