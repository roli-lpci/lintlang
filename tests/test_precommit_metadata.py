"""Contract tests for the native pre-commit hook."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = yaml.safe_load((REPO_ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
CHECKOUT_V7_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
LINTLANG_ACTION_VERSION = "v0.5.3"
LINTLANG_V053_SHA = "f89c3b0b8986fad162859dca052a8d5fe227eede"


def test_precommit_hook_is_explicit_and_advisory_by_default():
    assert len(HOOKS) == 1
    hook = HOOKS[0]

    assert hook["id"] == "lintlang"
    assert hook["entry"] == "lintlang scan"
    assert hook["language"] == "python"
    assert hook["args"] == ["AGENTS.md"]
    assert hook["pass_filenames"] is False
    assert hook["always_run"] is True
    assert hook["verbose"] is True


def test_public_docs_show_exercised_install_and_hook_paths():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    reference = (REPO_ROOT / "llms-full.txt").read_text(encoding="utf-8")
    code_scanning_example = (
        REPO_ROOT / "examples" / "github-code-scanning.yml"
    ).read_text(encoding="utf-8")

    for text in (readme, reference):
        assert "uvx lintlang scan AGENTS.md" in text
        assert "pipx install lintlang" in text
        assert "pipx ensurepath" in text
        assert "repo: https://github.com/hermes-labs-ai/lintlang" in text
        assert "rev: v0.5.3" in text
        assert "id: lintlang" in text
        assert "args: [AGENTS.md, --fail-on, fail]" in text
        assert f"hermes-labs-ai/lintlang@{LINTLANG_ACTION_VERSION}" in text

    for text in (readme, code_scanning_example, reference):
        assert f"actions/checkout@{CHECKOUT_V7_SHA} # v7.0.1" in text
        assert "actions/checkout@v7" not in text
        assert "hermes-labs-ai/lintlang@v0.4.0" not in text

    assert f"hermes-labs-ai/lintlang@{LINTLANG_V053_SHA} # v0.5.3" in code_scanning_example
    assert f"hermes-labs-ai/lintlang@{LINTLANG_ACTION_VERSION}" not in code_scanning_example
