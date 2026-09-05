"""Tests for the one-command GitHub Actions initializer."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lintlang.cli import main

LINTLANG_V053_SHA = "f89c3b0b8986fad162859dca052a8d5fe227eede"
UPLOAD_ARTIFACT_V7_SHA = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
DOWNLOAD_ARTIFACT_V8_SHA = "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
UPLOAD_SARIF_V4_SHA = "5595ccaf912efad79be6eef63a5619ff05969be3"
FORK_SAFE_UPLOAD_CONDITION = (
    "always() && (github.event_name == 'push' || "
    "(github.actor != 'dependabot[bot]' && "
    "github.event.pull_request.head.repo.full_name == github.repository))"
)


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
    return root


def test_init_github_creates_pinned_sarif_workflow(tmp_path, monkeypatch, capsys):
    root = _repository(tmp_path)
    nested = root / "packages" / "worker"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert main(["init", "--github"]) == 0

    workflow = root / ".github" / "workflows" / "lintlang.yml"
    text = workflow.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    assert "permissions" not in document
    assert set(document[True]) == {"pull_request", "push"}
    assert "pull_request_target" not in text

    scan = document["jobs"]["scan"]
    upload = document["jobs"]["upload-sarif"]
    assert scan["permissions"] == {"contents": "read"}
    assert upload["permissions"] == {
        "actions": "read",
        "contents": "read",
        "security-events": "write",
    }
    assert upload["needs"] == "scan"
    assert upload["if"] == FORK_SAFE_UPLOAD_CONDITION

    checkout = next(step for step in scan["steps"] if step["name"] == "Check out repository")
    lintlang = next(step for step in scan["steps"] if step["name"] == "Scan agent instructions")
    preserve = next(step for step in scan["steps"] if step["name"] == "Preserve SARIF")
    upload_checkout = next(
        step for step in upload["steps"] if step["name"] == "Check out repository for SARIF fingerprinting"
    )
    download = next(step for step in upload["steps"] if step["name"] == "Download SARIF")
    sarif_upload = next(step for step in upload["steps"] if step["name"] == "Upload SARIF")

    assert checkout["with"]["persist-credentials"] is False
    assert lintlang["uses"] == f"hermes-labs-ai/lintlang@{LINTLANG_V053_SHA}"
    assert lintlang["with"] == {
        "path": "AGENTS.md",
        "fail-on": "fail",
        "sarif-file": "lintlang.sarif",
    }
    assert "continue-on-error" not in lintlang
    assert preserve["if"] == "always()"
    assert preserve["uses"] == f"actions/upload-artifact@{UPLOAD_ARTIFACT_V7_SHA}"
    assert preserve["with"] == {
        "name": "lintlang-sarif",
        "path": "lintlang.sarif",
        "if-no-files-found": "error",
    }
    assert upload_checkout["with"]["persist-credentials"] is False
    assert download["uses"] == f"actions/download-artifact@{DOWNLOAD_ARTIFACT_V8_SHA}"
    assert download["with"]["name"] == preserve["with"]["name"]
    assert sarif_upload["uses"] == f"github/codeql-action/upload-sarif@{UPLOAD_SARIF_V4_SHA}"
    assert sarif_upload["with"]["sarif_file"] == preserve["with"]["path"]
    assert f"lintlang@{LINTLANG_V053_SHA} # v0.5.3" in text
    assert "Created: .github/workflows/lintlang.yml" in capsys.readouterr().out


def test_init_github_is_idempotent(tmp_path, monkeypatch, capsys):
    root = _repository(tmp_path)
    monkeypatch.chdir(root)

    assert main(["init", "--github"]) == 0
    first = (root / ".github/workflows/lintlang.yml").read_bytes()
    capsys.readouterr()
    assert main(["init", "--github"]) == 0

    assert (root / ".github/workflows/lintlang.yml").read_bytes() == first
    assert "Up to date" in capsys.readouterr().out


@pytest.mark.parametrize(
    "instruction_path",
    (
        "CLAUDE.md",
        ".github/copilot-instructions.md",
        ".github/instructions",
        "GEMINI.md",
    ),
)
def test_init_github_detects_common_coding_agent_instruction_paths(
    tmp_path, monkeypatch, instruction_path
):
    root = tmp_path / "repository"
    root.mkdir()
    (root / ".git").mkdir()
    target = root / instruction_path
    if target.suffix:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Instructions\n", encoding="utf-8")
    else:
        target.mkdir(parents=True)
        (target / "review.instructions.md").write_text("# Instructions\n", encoding="utf-8")
    monkeypatch.chdir(root)

    assert main(["init", "--github"]) == 0

    text = (root / ".github/workflows/lintlang.yml").read_text(encoding="utf-8")
    assert f'path: "{instruction_path}"' in text


def test_init_github_refuses_to_overwrite_without_force(tmp_path, monkeypatch, capsys):
    root = _repository(tmp_path)
    workflow = root / ".github/workflows/lintlang.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: existing\n", encoding="utf-8")
    monkeypatch.chdir(root)

    assert main(["init", "--github"]) == 1

    assert workflow.read_text(encoding="utf-8") == "name: existing\n"
    assert "already exists and differs" in capsys.readouterr().err


def test_init_github_force_replaces_known_destination(tmp_path, monkeypatch):
    root = _repository(tmp_path)
    workflow = root / ".github/workflows/lintlang.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: existing\n", encoding="utf-8")
    monkeypatch.chdir(root)

    assert main(["init", "--github", "--force"]) == 0

    assert "name: LintLang" in workflow.read_text(encoding="utf-8")


def test_init_github_accepts_explicit_repository_relative_path(tmp_path, monkeypatch):
    root = _repository(tmp_path)
    config = root / "config" / "agent contract.yaml"
    config.parent.mkdir()
    config.write_text("system_prompt: Be concise.\n", encoding="utf-8")
    monkeypatch.chdir(root)

    assert main(["init", "--github", "--path", "config/agent contract.yaml"]) == 0

    text = (root / ".github/workflows/lintlang.yml").read_text(encoding="utf-8")
    assert 'path: "config/agent contract.yaml"' in text


def test_init_github_rejects_path_outside_repository(tmp_path, monkeypatch, capsys):
    root = _repository(tmp_path)
    outside = tmp_path / "private.yaml"
    outside.write_text("system_prompt: private\n", encoding="utf-8")
    monkeypatch.chdir(root)

    assert main(["init", "--github", "--path", str(outside)]) == 1

    assert not (root / ".github/workflows/lintlang.yml").exists()
    assert "must stay inside" in capsys.readouterr().err


def test_init_github_requires_real_scan_input(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repository"
    root.mkdir()
    (root / ".git").mkdir()
    monkeypatch.chdir(root)

    assert main(["init", "--github"]) == 1

    assert not (root / ".github/workflows/lintlang.yml").exists()
    assert "rerun with --path" in capsys.readouterr().err


def test_init_github_requires_git_repository(tmp_path, monkeypatch, capsys):
    (tmp_path / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--github"]) == 1

    assert "must run inside a Git repository" in capsys.readouterr().err
