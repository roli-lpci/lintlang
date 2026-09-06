# LintLang

[![CI](https://github.com/hermes-labs-ai/lintlang/actions/workflows/ci.yml/badge.svg)](https://github.com/hermes-labs-ai/lintlang/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/lintlang)](https://pypi.org/project/lintlang/)
[![PyPI downloads](https://img.shields.io/pypi/dm/lintlang?label=downloads%2Fmonth)](https://pypistats.org/packages/lintlang)
[![Python](https://img.shields.io/pypi/pyversions/lintlang)](https://pypi.org/project/lintlang/)
[![License](https://img.shields.io/pypi/l/lintlang)](LICENSE)

**Product page:** [lintlang.ai](https://lintlang.ai/)

**LintLang statically analyzes the natural-language instructions that control
AI agents, catching ambiguous tools, missing limits, and conflicting directives
before runtime.**

It flags patterns such as:

- empty, vague, or overlapping tool descriptions;
- tool pairs with no term that distinguishes one from the other (`H1.6`);
- missing stop conditions and unbounded retries;
- inconsistencies between tool schemas and their descriptions;
- unscoped context and vague instructions;
- conflicting output formats and malformed message roles;
- embedded prompts and uncalibrated thresholds in Python pipelines.

LintLang's default static checks are deterministic and local. They make no LLM,
API, telemetry, or network calls.

LintLang was developed as the engineering offshoot of
[A Taxonomy of Epistemic Failure Modes in Large Language Models](https://doi.org/10.5281/zenodo.19042468),
but its bounded detectors do not claim to implement or validate every failure
mode in the paper.

## Technical note

[Tool Differentia: Relational Static Analysis for AI Agent Tool Descriptions](https://hermes-labs.ai/research/tool-differentia)
documents LintLang H1.6, the bounded pairwise check for tool descriptions that
do not supply an analyzed distinction from a neighboring tool. It is a
technical note, not a semantic-equivalence proof or a runtime-selection
evaluation. Use its version-independent concept DOI,
[10.5281/zenodo.21817243](https://doi.org/10.5281/zenodo.21817243), for citation;
the current archived release is Version 1.0.1.

## Quick start

Run once without installing, using [uv](https://docs.astral.sh/uv/):

```bash
uvx lintlang scan AGENTS.md
```

For a persistent command in an isolated environment, use
[pipx](https://pipx.pypa.io/stable/):

```bash
pipx install lintlang
lintlang scan AGENTS.md
```

If pipx's app directory is not on `PATH`, run `pipx ensurepath`, open a new
shell, and retry the scan.

Or install from PyPI into the current Python environment:

```bash
python -m pip install lintlang
```

Requires Python 3.10+.

From your project root, point LintLang at an actual instruction file:

```bash
lintlang scan AGENTS.md
```

If your project uses another filename, replace `AGENTS.md` with its prompt,
tool-definition, agent-configuration, or supported directory path.

## Lint the instructions your coding agent actually reads

LintLang treats agent instruction files as ordinary local inputs. It does not
need a vendor API, an always-running agent hook, or a separate integration for
each host.

| Coding-agent workflow | Native instruction surface | Local gate | Generate CI/SARIF gate |
| --- | --- | --- | --- |
| Codex | `AGENTS.md` | `lintlang scan AGENTS.md` | `lintlang init --github --path AGENTS.md` |
| Claude Code | `CLAUDE.md` | `lintlang scan CLAUDE.md` | `lintlang init --github --path CLAUDE.md` |
| GitHub Copilot | `.github/copilot-instructions.md` or `.github/instructions/` | `lintlang scan .github/copilot-instructions.md` | `lintlang init --github --path .github/copilot-instructions.md` |
| Gemini CLI | `GEMINI.md` | `lintlang scan GEMINI.md` | `lintlang init --github --path GEMINI.md` |

For a repository that has exactly one of these common paths, `lintlang init
--github` detects it automatically. Pass `--path` when the repository has
more than one instruction surface or when you want to scan an instruction
directory. The generated workflow runs the same local scanner and uploads
SARIF; it does not change how the coding agent loads its instructions.

[Character.AI's public Larch repository](https://github.com/character-ai/larch/blob/ef7ee4b7f946f29fa51981f5422a1a93e83c79a7/.github/workflows/requirements-agent-linters.txt)
pins `lintlang==0.3.1` in recurring CI. Larch's
[linting reference](https://github.com/character-ai/larch/blob/210d08a8f6c1b0dd14c27b709c66471bd31a5636/docs/linting.md)
links this repository as the upstream and documents the gate: its consolidated
`agent-lint` job scans `agents/`, `.claude/agents/`, `skills/`, and
`.claude/skills/` and fails on HIGH or CRITICAL findings
([merged July 2026](https://github.com/character-ai/larch/pull/7960)).
LintLang also has independent Gentoo packaging in the unofficial
[Haven overlay](https://github.com/thehaven/haven-overlay/tree/d052d950b05389fcd7c8f22939033319a5aec348/dev-util/lintlang),
not the official tree or GURU; its ebuilds have tracked upstream releases since
0.2.1, and its `metadata.xml` records this repository as the upstream remote.

When you are ready to make `HIGH` or `CRITICAL` findings block CI:

```bash
lintlang scan AGENTS.md --fail-on fail
```

Each finding identifies the affected location, the detected pattern, its
severity, and a suggested review action.

### Adopt LintLang in an existing repository

An existing instruction backlog does not have to delay a CI gate. The
[baseline workflow](docs/baselines.md) records reviewed findings and lets the
same scanner report and gate findings that are not acknowledged. It works in
the CLI and the first-party GitHub Action, without disabling an entire rule.

This feature is **unreleased**; use a source checkout containing this change.
From the root of the project you want to scan:

```bash
# Review the full report before committing the generated baseline.
lintlang scan AGENTS.md --write-baseline .lintlang-baseline.json

# Keep the known backlog acknowledged while blocking new MEDIUM+ findings.
lintlang scan AGENTS.md --baseline .lintlang-baseline.json --fail-on review
```

Baseline matching is exact and count-limited. Changed findings and findings in
another file remain visible. Invalid inputs still fail; HERM scores are
unchanged. See the guide for CI configuration, maintenance, and matching limits.

## Try the bundled example

The source repository includes a deliberately broken example:

```bash
git clone --depth 1 https://github.com/hermes-labs-ai/lintlang.git
cd lintlang

lintlang scan samples/bad_tool_descriptions.yaml --fail-on fail
```

Excerpt from `lintlang 0.5.3`:

```text
LINTLANG v0.5.3

FAIL — 1 CRITICAL, 2 HIGH, 7 MEDIUM, 3 LOW

H1: Tool Description Ambiguity

  [CRITICAL] H1.1 tool:process_ticket
  Tool 'process_ticket' has no description.

  [HIGH] H1.2 tool:get_user_info
  Tool 'get_user_info' has a very short description (13 chars):
  "Get user info"

…

H2: Missing Constraint Scaffolding

  [HIGH] system_prompt
  System prompt defines tools but contains no termination conditions,
  retry budgets, or progress checks.
```

The command exits with status `1` because it includes `--fail-on fail`.

## Verdicts and CI behavior

| Verdict | Practical meaning |
|---|---|
| `PASS` | No `MEDIUM`, `HIGH`, or `CRITICAL` finding remained after the selected checks and filters |
| `REVIEW` | At least one `MEDIUM` finding remained |
| `FAIL` | At least one `HIGH` or `CRITICAL` finding remained |
| `ERROR` | A requested input could not be inspected |

`PASS` applies only to recognized content extracted from the requested inputs
and the checks and severity filters selected for that run. It does not mean
that every structure in an arbitrary JSON or YAML file was extracted.
A clean LintLang scan is not evidence that an agent is safe or runtime-correct.

By default, findings are reported without failing the process.

- `--fail-on fail` blocks on `FAIL`.
- `--fail-on review` blocks on `REVIEW` or `FAIL`.
- Missing, malformed, unreadable, or otherwise unscannable requested inputs
  remain nonzero regardless of the chosen finding threshold.
- An invocation that finds no eligible files exits nonzero.

Filters such as `--min-severity` are applied before the verdict. For initial
adoption, keep the full output visible and use `--fail-on fail` to block only
the highest-severity findings.

## Add it to CI

From a Git repository containing `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, a
Copilot instructions file or directory, or an agent YAML/JSON config, create
the pinned GitHub Code Scanning workflow in one command:

```bash
lintlang init --github
```

Use `--path path/to/instructions` when auto-detection should not choose the
input. The initializer will not replace a different existing workflow unless
you pass `--force`; inspect that diff before committing it. Generated workflows
pin the latest reviewed, already-released LintLang action to its immutable
commit, with the release tag retained as a human-readable comment. The pin can
intentionally trail the package being prepared because that package's release
commit does not exist yet when its artifacts are built.

After choosing one real instruction path in your repository:

```yaml
jobs:
  lint-agent-instructions:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Inspect agent instructions
        uses: hermes-labs-ai/lintlang@v0.5.3
        with:
          path: AGENTS.md
```

The release tag pins both the action and the LintLang source it installs.
Upgrade that pin deliberately and inspect newly introduced findings before
making them blocking.

## Hermes Agent verification hook

When LintLang and [Hermes Agent](https://github.com/NousResearch/hermes-agent)
are installed in the same Python environment, Hermes discovers LintLang through
its native `hermes_agent.plugins` entry-point contract. LintLang registers one
bounded `pre_verify` hook: after a coding turn changes a recognized agent
instruction, prompt, skill, tool, or agent-config surface, it runs the same
local deterministic scan before the turn finishes.

`PASS` and `REVIEW` do not interrupt the turn. `FAIL` or an input `ERROR` keeps
the turn open once with the exact `lintlang scan` command to run. The hook
self-throttles on Hermes' `attempt` field and ignores ordinary source and
documentation files, so it cannot create an unbounded retry loop or turn a
general code edit into a prompt-lint gate.

Verify discovery with:

```bash
hermes plugins list
```

Disable the `lintlang` plugin through Hermes' normal plugin controls if the
workspace should use only LintLang's CI or pre-commit surfaces.

## Add it to pre-commit

Add the hook to `.pre-commit-config.yaml` with the explicit instruction paths
to scan:

```yaml
repos:
  - repo: https://github.com/hermes-labs-ai/lintlang
    rev: v0.5.3
    hooks:
      - id: lintlang
        args: [AGENTS.md]
```

Activate it and test the configured paths:

```bash
pre-commit install
pre-commit run lintlang
```

In CI, after installing `pre-commit`, run that same configured hook across the
repository:

```yaml
- name: Lint agent instructions
  run: pre-commit run lintlang --all-files
```

Replace or extend `args` with the prompt, tool-definition, agent-configuration,
or supported directory paths your repository owns. The hook scans only those
configured paths and reports findings without blocking on a verdict by default.

After reviewing the repository's baseline, opt into blocking `FAIL` findings:

```yaml
hooks:
  - id: lintlang
    args: [AGENTS.md, --fail-on, fail]
```

Missing, unreadable, or malformed configured inputs still return nonzero.

## Use it with MegaLinter

The external MegaLinter plugin exposes LintLang as `AI_LINTLANG`, installing the
pinned release at run time through MegaLinter's plugin loader. See the
[MegaLinter plugin guide](mega-linter-plugin-lintlang/README.md) for the exact
`PLUGINS` and `ENABLE_LINTERS` configuration and the container verification
steps.

## Use it with Gemini CLI

The repository root is also a Gemini CLI extension. Its non-blocking
`AfterTool` hook returns LintLang repair guidance after Gemini changes supported
files with `write_file` or `replace`. See the
[Gemini CLI extension guide](docs/gemini-cli-extension.md) for the pinned,
isolated dependency contract and installation steps.

## Machine-readable output and GitHub Code Scanning

For machine-readable output:

```bash
lintlang scan AGENTS.md --format json --fail-on fail
```

For deterministic SARIF 2.1.0 output on stdout:

```bash
lintlang scan AGENTS.md --format sarif --fail-on fail > lintlang.sarif
```

Relative inputs are resolved from the current directory. Artifact URIs are
URI-encoded paths relative to the nearest Git worktree root (or the current
directory when there is no Git worktree). A resolved source outside that root
is a fatal output error rather than an absolute-path leak. Python AST findings
carry supported line spans; YAML, JSON, and text findings intentionally remain
file-level.

The composite Action can write the same report with its optional `sarif-file`
input. In that mode SARIF stdout is redirected to the requested file, while
verdict messages remain on stderr and `fail-on` keeps its normal exit status.
Directory creation or file-write errors are fatal.

To ask GitHub to ingest the report without exposing Code Scanning write
permission to LintLang or its scan-time dependencies, use separate scan and
upload jobs. The upload job checks out source without persisting credentials so
GitHub can calculate missing fingerprints. The artifact handoff runs even after
a blocking LintLang verdict; the scan job still keeps that failure as its
conclusion:

```yaml
name: LintLang Code Scanning

on:
  push:
  pull_request:

jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Check out repository
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Run LintLang
        uses: hermes-labs-ai/lintlang@f89c3b0b8986fad162859dca052a8d5fe227eede # v0.5.3
        with:
          path: AGENTS.md
          fail-on: fail
          sarif-file: lintlang.sarif

      - name: Preserve LintLang SARIF
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: lintlang-sarif
          path: lintlang.sarif
          if-no-files-found: error

  upload-sarif:
    needs: scan
    if: always() && (github.event_name == 'push' || (github.actor != 'dependabot[bot]' && github.event.pull_request.head.repo.full_name == github.repository))
    runs-on: ubuntu-latest
    permissions:
      actions: read
      contents: read
      security-events: write
    steps:
      - name: Check out repository for SARIF fingerprinting
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - name: Download LintLang SARIF
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
        with:
          name: lintlang-sarif

      - name: Upload LintLang SARIF
        uses: github/codeql-action/upload-sarif@5595ccaf912efad79be6eef63a5619ff05969be3 # v4
        with:
          sarif_file: lintlang.sarif
```

The complete copy-paste workflow is
[`examples/github-code-scanning.yml`](examples/github-code-scanning.yml).
LintLang emits code-quality/static-language results without security tags,
security severity, source snippets, or custom fingerprints. GitHub's upload
Action may calculate fingerprints during ingestion.

## What it inspects

LintLang currently accepts:

- JSON and YAML objects using recognized top-level agent fields such as
  `system_prompt`, `instructions`, `tools`, `functions`, `messages`, and
  selected response-schema fields;
- `.txt`, `.md`, and `.prompt` instruction files;
- Python files, using AST extraction for prompt-like strings and
  threshold assignments.

Nested vendor-specific layouts and raw top-level YAML arrays are not
automatically normalized. A syntactically valid input must still match a
recognized shape for its structured tools or messages to be inspected.

The checks cover reader-facing categories including tool clarity, execution
bounds, schema-description alignment, context boundaries, instruction
specificity, output contracts, message-role structure, and Python pipeline
hygiene.

### H1.6: tool descriptions without a differentia

Per-tool schema validation assesses one definition at a time. Within one parsed
input, H1.6 instead compares tool definitions with each other and reports a pair
when, under LintLang's term-and-synonym model, one or both descriptions provide
no distinguishing term. Both tools can be individually valid, so per-tool
validation has nothing to report. A *mutual* finding means neither description
distinguishes itself; *domination* means one tool's terms are all covered by the
other, and the finding names which description to repair. Directory scans do
not aggregate tool definitions across files or infer a shared namespace.

Findings print the sub-code:
`~ [MEDIUM] H1.6 tool:find_tickets vs tool:search_tickets`. `pattern_id` stays
`H1`; JSON output adds a `code` field holding the most specific identifier.

H1.6 is MEDIUM, so `--fail-on fail` does not block on it. Matching uses a
finite English synonym lexicon, so pairs that say the same thing in different
words or a different sentence shape are missed. The absence of an H1.6 finding
is not evidence that no such pair exists.

Use narrow, intentional paths. Directory scans can discover Markdown and Python
files that were not written as agent configuration; use `.lintlangignore` or
`--exclude` where needed.

For the exact H-series identifiers:

```bash
lintlang patterns
```

`lintlang patterns` lists the H1-H7 structural detectors only. Python pipeline
findings report as `P1` and `P2` in scan, JSON, and SARIF output.

See the [full technical reference](llms-full.txt) for detector details.

## Where it fits

```text
syntax and schema validation
        ↓
LintLang static language checks
        ↓
runtime agent evaluation
        ↓
domain and security review
```

LintLang is useful during authoring and pull-request review, before runtime
testing. It does not:

- determine whether an instruction is factually or semantically correct;
- observe an agent selecting or executing tools;
- prove that a finding causes a runtime failure;
- certify an agent as safe or production-ready;
- replace runtime evaluation or human review.

Suggestions are review aids, not guaranteed meaning-preserving fixes.

## Optional instruction preflight

Secondary capability: [provider-neutral instruction preflight](docs/preflight.md)
inspects one present instruction plus explicit context.

## More

- [Technical reference](llms-full.txt)
- [Product scope and invariants](INTENT.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Report an issue or disputed finding](https://github.com/hermes-labs-ai/lintlang/issues)
- [Security policy](SECURITY.md)

## License

[Apache License 2.0](LICENSE)

LintLang is maintained by [Hermes Labs](https://hermes-labs.ai).
