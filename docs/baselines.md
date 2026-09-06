# Baselines: adopt now, review the backlog deliberately

Baselines acknowledge a reviewed set of existing structural findings. They let
a repository enable a gate while its maintainers work through that backlog.
The default scanner behavior is unchanged until you pass `--baseline`.

**Availability:** this feature is unreleased. Install a source checkout that
contains it with `python -m pip install /path/to/lintlang`, preferably in a
virtual environment. The published `lintlang==0.5.3` package and `v0.5.3` Action
do not support these options.

## Start from a reviewed scan

Run from your project's Git root. Replace `AGENTS.md` with the actual file or
supported directory your team wants to gate:

```bash
lintlang scan AGENTS.md --write-baseline .lintlang-baseline.json
```

This prints the complete scan report and writes a new baseline. Review those
findings and decide which backlog you are accepting before committing the
file. Creation is explicit; it never overwrites an existing file, including a
symlink, and writes nothing if an input fails or no input is scanned. As with a
normal scan, findings only produce a nonzero exit when you also request
`--fail-on` or `--fail-under`; omit those flags for the initial inventory.

Then enable the gate:

```bash
lintlang scan AGENTS.md --baseline .lintlang-baseline.json --fail-on review
```

`--fail-on review` blocks remaining MEDIUM, HIGH, or CRITICAL findings.
`--fail-on fail` blocks remaining HIGH or CRITICAL findings. An unchanged scan
with all findings acknowledged passes either structural gate. A newly added
file receives no allowance from another file's entries. Missing, malformed, or
unsupported baselines and source input errors return a nonzero exit even when
no severity gate is requested.

Use the same scan paths, `--patterns`, `--min-severity`, and `--exclude` options
when creating and applying a baseline. Filters run before baseline matching.
Expanding the selected rules or severity range can reveal findings that were
never acknowledged.

## GitHub Action

Use the optional `baseline` input with an Action commit that contains this
feature. The Action installs the scanner from that same commit. After the
change is merged, replace `<BASELINE_ENABLED_COMMIT_SHA>` below with its full
reviewed commit SHA; `v0.5.3` cannot be used for this workflow.

```yaml
name: Lint agent instructions
on: [push, pull_request]
permissions:
  contents: read
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: hermes-labs-ai/lintlang@<BASELINE_ENABLED_COMMIT_SHA>
        with:
          path: AGENTS.md
          baseline: .lintlang-baseline.json
          fail-on: review
```

The same input works with `sarif-file`. Only remaining findings are emitted as
SARIF results; the run's `properties.lintlangBaseline` contains the suppressed
count and verdict scope. The Action rejects a SARIF destination that resolves
to the baseline, including symlink aliases. For uploading SARIF, follow the
[Code Scanning permission and upload guidance](../README.md#machine-readable-output-and-github-code-scanning).

CI only reads the committed baseline. It never creates or updates one. Review
baseline edits as carefully as changes to the CI gate itself: anyone who can
change the baseline can acknowledge findings.

## What is matched and what is preserved

- Each entry identifies a repository-relative POSIX path, a SHA-256 finding
  fingerprint, and an occurrence count. In a non-Git directory, the invocation
  directory is the root. Inputs outside that root are rejected for baseline
  matching. Run from the same project root in local and CI workflows.
- The fingerprint includes the diagnostic code, severity, location,
  description, and evidence. Matching is exact; there are no wildcards or
  rule-wide exemptions. A changed location, message, or evidence can reopen a
  finding, including after a detector upgrade. Suggestions are not identity.
- Additional occurrences beyond the recorded count remain visible. Repeating
  the same file through multiple CLI paths does not enlarge its allowance.
- HERM scores, quality thresholds, and source input errors are unchanged.
  Terminal and Markdown reports state that their verdict covers remaining
  findings. JSON reports add `baseline.suppressed` to each scanned result.

The baseline stores paths and hashes, not raw prompts or finding evidence.
Hashes are not encryption: review filenames and the sensitivity of your inputs
before publishing a baseline. Ordinary scan reports may still contain evidence.

## Maintain a shrinking backlog

After fixing findings, create a candidate at a new path and review it before
replacing the committed baseline:

```bash
lintlang scan AGENTS.md --write-baseline .lintlang-baseline.candidate.json
git diff --no-index .lintlang-baseline.json .lintlang-baseline.candidate.json
# After review:
mv .lintlang-baseline.candidate.json .lintlang-baseline.json
```

`git diff --no-index` exits 1 when the files differ; that is expected. Compare
the complete scan report as well as the hash changes. Never refresh a baseline
automatically after a failed gate: doing so can accept the very changes the
gate was meant to surface.

Unused entries are allowed, so removing a finding does not itself break CI.
Prune them through the reviewed refresh above. An identical finding reintroduced
at the same identity can still match an old entry until it is removed. A
baseline records acknowledged identities, not the history of when each defect
was fixed. It does not assess runtime agent behavior or establish safety.
