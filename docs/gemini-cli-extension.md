# Gemini CLI extension

LintLang's repository root is a Gemini CLI extension. Its `AfterTool` hook runs
after successful `write_file` and `replace` calls, scans supported
language-bearing files, and appends concise repair guidance to the tool result.
It does not block or rewrite the file. Clean and unsupported files add no
context.

## Install

The extension requires [uv](https://docs.astral.sh/uv/) on `PATH`. The hook runs
the source bundled in the installed extension and asks uv for exactly
`PyYAML==6.0.3` in an isolated cached environment. It does not depend on an
ambient `lintlang` installation. The first scan may download that pinned wheel;
later scans reuse uv's cache.

From an already configured Gemini CLI, install the released 0.5.3 source:

```bash
gemini extensions install https://github.com/hermes-labs-ai/lintlang --ref=f89c3b0b8986fad162859dca052a8d5fe227eede
gemini extensions list
```

Review the installation consent prompt. The source commit pins
[v0.5.3](https://github.com/hermes-labs-ai/lintlang/releases/tag/v0.5.3).
This command was verified with Gemini CLI 0.32.1; the extension list reports
`lintlang (0.5.3)` as enabled, with `Type: git` and the source commit above.
Restart an active Gemini CLI session to load the installed extension.

Gemini CLI copies the extension, including `src/lintlang`, into its extension
directory. No separate LintLang installation is required.

For local development, install from a repository checkout instead:

```bash
gemini extensions validate .
gemini extensions install . --consent
```

## Behavior

The hook handles `.yaml`, `.yml`, `.json`, `.txt`, `.md`, `.prompt`, and `.py`.
It returns at most eight findings plus an omitted count, includes stable codes,
locations, severities, descriptions, and repair suggestions, and omits the raw
`evidence` field. Hook execution is capped at 30 seconds.
