"""Contract tests for the first-party composite GitHub Action."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ACTION = yaml.safe_load((REPO_ROOT / "action.yml").read_text(encoding="utf-8"))


def _real_lintlang_path(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command = fake_bin / "lintlang"
    command.write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" -m lintlang "$@"\n', encoding="utf-8")
    command.chmod(0o755)
    return fake_bin


def _action_env(tmp_path: Path, source: Path, baseline: Path | None = None, **extra: str) -> dict[str, str]:
    lintlang_bin = _real_lintlang_path(tmp_path)
    return {
        **os.environ,
        "PATH": f"{lintlang_bin}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "LINTLANG_PATH": str(source),
        "LINTLANG_FAIL_ON": "fail",
        "LINTLANG_BASELINE": str(baseline) if baseline is not None else "",
        **extra,
    }


def _run_action(output_format: str, tmp_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    scan = ACTION["runs"]["steps"][3 if output_format == "sarif" else 2]
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", scan["run"]],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _create_baseline(source: Path, baseline: Path, tmp_path: Path) -> bytes:
    completed = subprocess.run(
        [sys.executable, "-m", "lintlang", "scan", str(source), "--write-baseline", str(baseline)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return baseline.read_bytes()


def test_marketplace_metadata_and_inputs_are_minimal():
    assert ACTION["name"] == "LintLang Agent Config Linter"
    assert ACTION["description"]
    assert ACTION["branding"] == {"icon": "check-circle", "color": "blue"}
    assert ACTION["runs"]["using"] == "composite"
    assert ACTION.get("outputs") is None

    inputs = ACTION["inputs"]
    assert set(inputs) == {"path", "fail-on", "baseline", "python-version", "sarif-file"}
    assert inputs["path"]["required"] is True
    assert inputs["fail-on"]["default"] == "fail"
    assert inputs["baseline"]["required"] is False
    assert inputs["baseline"]["default"] == ""
    assert inputs["python-version"]["default"] == "3.12"
    assert inputs["sarif-file"]["required"] is False
    assert inputs["sarif-file"]["default"] == ""


def test_setup_python_is_pinned_to_a_full_commit_sha():
    setup = ACTION["runs"]["steps"][0]
    owner_repo, sha = setup["uses"].split("@", maxsplit=1)
    assert owner_repo == "actions/setup-python"
    assert re.fullmatch(r"[0-9a-f]{40}", sha)
    assert setup["with"]["python-version"] == "${{ inputs.python-version }}"


def test_selected_action_ref_is_installed_and_inputs_are_not_shell_interpolated():
    install, scan, sarif_scan = ACTION["runs"]["steps"][1:]
    assert install["run"] == 'python -m pip install "$GITHUB_ACTION_PATH"'
    assert scan["if"] == "inputs.sarif-file == ''"
    assert scan["env"] == {
        "LINTLANG_PATH": "${{ inputs.path }}",
        "LINTLANG_FAIL_ON": "${{ inputs.fail-on }}",
        "LINTLANG_BASELINE": "${{ inputs.baseline }}",
    }
    assert 'LINTLANG_ARGS=(scan "$LINTLANG_PATH" --fail-on "$LINTLANG_FAIL_ON")' in scan["run"]
    assert sarif_scan["if"] == "inputs.sarif-file != ''"
    assert sarif_scan["env"] == {
        "LINTLANG_PATH": "${{ inputs.path }}",
        "LINTLANG_FAIL_ON": "${{ inputs.fail-on }}",
        "LINTLANG_BASELINE": "${{ inputs.baseline }}",
        "LINTLANG_SARIF_FILE": "${{ inputs.sarif-file }}",
    }
    for step in (scan, sarif_scan):
        assert 'LINTLANG_ARGS+=(--baseline "$LINTLANG_BASELINE")' in step["run"]
        assert 'lintlang "${LINTLANG_ARGS[@]}"' in step["run"]
        assert "--write-baseline" not in step["run"]
    assert "${{" not in install["run"]
    assert "${{" not in scan["run"]
    assert "${{" not in sarif_scan["run"]


def test_default_action_command_preserves_clean_and_failing_fixtures(tmp_path):
    lintlang_bin = _real_lintlang_path(tmp_path)
    scan = ACTION["runs"]["steps"][2]
    base_env = {
        **os.environ,
        "PATH": f"{lintlang_bin}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "LINTLANG_FAIL_ON": "fail",
    }

    outcomes = []
    for fixture in ("clean_config.yaml", "bad_tool_descriptions.yaml"):
        completed = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", scan["run"]],
            cwd=REPO_ROOT,
            env={**base_env, "LINTLANG_PATH": f"samples/{fixture}"},
            text=True,
            capture_output=True,
            check=False,
        )
        outcomes.append(completed.returncode)

    assert outcomes == [0, 1]


def test_sarif_step_writes_real_report_before_preserving_failing_verdict(tmp_path):
    lintlang_bin = _real_lintlang_path(tmp_path)
    report = tmp_path / "nested" / "lintlang.sarif"
    sarif_scan = ACTION["runs"]["steps"][3]
    env = {
        **os.environ,
        "PATH": f"{lintlang_bin}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "LINTLANG_PATH": "samples/bad_tool_descriptions.yaml",
        "LINTLANG_FAIL_ON": "fail",
        "LINTLANG_SARIF_FILE": str(report),
    }

    completed = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", sarif_scan["run"]],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    document = json.loads(report.read_text(encoding="utf-8"))
    assert document["version"] == "2.1.0"
    assert document["runs"][0]["results"]


def test_sarif_step_rejects_output_that_is_the_input_without_overwriting_it(tmp_path):
    lintlang_bin = _real_lintlang_path(tmp_path)
    source = tmp_path / "agent.yaml"
    original = "system_prompt: Be concise.\n"
    source.write_text(original, encoding="utf-8")
    sarif_scan = ACTION["runs"]["steps"][3]
    env = {
        **os.environ,
        "PATH": f"{lintlang_bin}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "LINTLANG_PATH": str(source),
        "LINTLANG_FAIL_ON": "fail",
        "LINTLANG_SARIF_FILE": str(source),
    }

    completed = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", sarif_scan["run"]],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert source.read_text(encoding="utf-8") == original
    assert "must differ" in completed.stderr


def test_sarif_step_rejects_an_existing_directory_as_the_output(tmp_path):
    lintlang_bin = _real_lintlang_path(tmp_path)
    source = tmp_path / "agent.yaml"
    source.write_text("system_prompt: Be concise.\n", encoding="utf-8")
    report_directory = tmp_path / "reports"
    report_directory.mkdir()
    sarif_scan = ACTION["runs"]["steps"][3]
    env = {
        **os.environ,
        "PATH": f"{lintlang_bin}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "LINTLANG_PATH": str(source),
        "LINTLANG_FAIL_ON": "fail",
        "LINTLANG_SARIF_FILE": str(report_directory),
    }

    completed = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", sarif_scan["run"]],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert list(report_directory.iterdir()) == []
    assert "must name a file" in completed.stderr


def test_sarif_step_does_not_add_its_output_to_a_directory_scan(tmp_path):
    lintlang_bin = _real_lintlang_path(tmp_path)
    scan_root = tmp_path / "configs"
    scan_root.mkdir()
    (scan_root / "agent.yaml").write_text("system_prompt: Be concise.\n", encoding="utf-8")
    report = scan_root / "lintlang.sarif.json"
    sarif_scan = ACTION["runs"]["steps"][3]
    env = {
        **os.environ,
        "PATH": f"{lintlang_bin}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "LINTLANG_PATH": str(scan_root),
        "LINTLANG_FAIL_ON": "fail",
        "LINTLANG_SARIF_FILE": str(report),
    }

    completed = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", sarif_scan["run"]],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    document = json.loads(report.read_text(encoding="utf-8"))
    assert document["runs"][0]["invocations"][0]["executionSuccessful"] is True


@pytest.mark.parametrize("output_format", ["terminal", "sarif"])
@pytest.mark.parametrize("fail_on", ["fail", "review"])
def test_action_baseline_passes_known_findings_and_fails_new_findings(tmp_path, output_format, fail_on):
    scan_root = tmp_path / "configs"
    scan_root.mkdir()
    source = scan_root / "agent.yaml"
    original = (REPO_ROOT / "samples" / "bad_tool_descriptions.yaml").read_bytes()
    source.write_bytes(original)
    baseline = tmp_path / "baseline.json"
    baseline_bytes = _create_baseline(scan_root, baseline, tmp_path)
    report = tmp_path / "report.sarif"
    env = _action_env(
        tmp_path,
        scan_root,
        baseline,
        LINTLANG_FAIL_ON=fail_on,
        LINTLANG_SARIF_FILE=str(report),
    )

    known = _run_action(output_format, tmp_path, env)

    assert known.returncode == 0, known.stdout + known.stderr
    if output_format == "sarif":
        assert json.loads(report.read_text(encoding="utf-8"))["runs"][0]["results"] == []

    new_source = scan_root / "new-agent.yaml"
    new_source.write_bytes(original)
    new = _run_action(output_format, tmp_path, env)

    assert new.returncode == 1, new.stdout + new.stderr
    if output_format == "sarif":
        assert json.loads(report.read_text(encoding="utf-8"))["runs"][0]["results"]
    assert baseline.read_bytes() == baseline_bytes
    assert source.read_bytes() == original
    assert new_source.read_bytes() == original


@pytest.mark.parametrize("output_format", ["terminal", "sarif"])
@pytest.mark.parametrize("baseline_state", ["missing", "invalid"])
def test_action_rejects_missing_or_invalid_baseline_without_creating_or_changing_it(
    tmp_path, output_format, baseline_state
):
    source = tmp_path / "agent.yaml"
    original = b"system_prompt: Be concise.\n"
    source.write_bytes(original)
    baseline = tmp_path / "baseline.json"
    invalid_bytes = b'{"not": "a lintlang baseline"}\n'
    if baseline_state == "invalid":
        baseline.write_bytes(invalid_bytes)
    env = _action_env(tmp_path, source, baseline, LINTLANG_SARIF_FILE=str(tmp_path / "report.sarif"))

    completed = _run_action(output_format, tmp_path, env)

    assert completed.returncode != 0
    assert source.read_bytes() == original
    if baseline_state == "missing":
        assert not baseline.exists()
    else:
        assert baseline.read_bytes() == invalid_bytes


@pytest.mark.parametrize("output_format", ["terminal", "sarif"])
def test_action_baseline_does_not_hide_input_errors(tmp_path, output_format):
    source = tmp_path / "agent.yaml"
    source.write_bytes((REPO_ROOT / "samples" / "bad_tool_descriptions.yaml").read_bytes())
    baseline = tmp_path / "baseline.json"
    baseline_bytes = _create_baseline(source, baseline, tmp_path)
    invalid_bytes = b"tools: [\n"
    source.write_bytes(invalid_bytes)
    env = _action_env(tmp_path, source, baseline, LINTLANG_SARIF_FILE=str(tmp_path / "report.sarif"))

    completed = _run_action(output_format, tmp_path, env)

    assert completed.returncode != 0
    assert baseline.read_bytes() == baseline_bytes
    assert source.read_bytes() == invalid_bytes


@pytest.mark.parametrize("output_format", ["terminal", "sarif"])
def test_action_baseline_path_with_shell_metacharacters_is_inert(tmp_path, output_format):
    source = tmp_path / "agent.yaml"
    original = (REPO_ROOT / "samples" / "bad_tool_descriptions.yaml").read_bytes()
    source.write_bytes(original)
    baseline = tmp_path / "known findings; touch BASELINE_EXECUTED; $(touch BASELINE_SUBSTITUTED).json"
    baseline_bytes = _create_baseline(source, baseline, tmp_path)
    env = _action_env(tmp_path, source, baseline, LINTLANG_SARIF_FILE=str(tmp_path / "report.sarif"))

    completed = _run_action(output_format, tmp_path, env)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not (tmp_path / "BASELINE_EXECUTED").exists()
    assert not (tmp_path / "BASELINE_SUBSTITUTED").exists()
    assert baseline.read_bytes() == baseline_bytes
    assert source.read_bytes() == original


@pytest.mark.parametrize("alias", ["same-path", "relative-path", "report-symlink", "baseline-symlink"])
def test_sarif_step_rejects_baseline_output_collision_before_scanning(tmp_path, alias):
    source = tmp_path / "agent.yaml"
    original = (REPO_ROOT / "samples" / "bad_tool_descriptions.yaml").read_bytes()
    source.write_bytes(original)
    baseline = tmp_path / "baseline.json"
    baseline_bytes = _create_baseline(source, baseline, tmp_path)
    report = baseline
    if alias == "relative-path":
        (tmp_path / "nested").mkdir()
        report = Path("nested/../baseline.json")
    elif alias == "report-symlink":
        report = tmp_path / "report.sarif"
        report.symlink_to(baseline)
    elif alias == "baseline-symlink":
        baseline = tmp_path / "baseline-link.json"
        baseline.symlink_to(report)
    env = _action_env(tmp_path, source, baseline, LINTLANG_SARIF_FILE=str(report))
    # Trace the Action's shell: collision rejection must happen before the CLI
    # invocation and before any report staging or replacement.
    scan = ACTION["runs"]["steps"][3]
    completed = subprocess.run(
        ["bash", "-x", "-e", "-o", "pipefail", "-c", scan["run"]],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "inputs baseline and sarif-file must differ" in completed.stderr
    assert "+ lintlang " not in completed.stderr
    assert "+ mktemp " not in completed.stderr
    assert "+ mv " not in completed.stderr
    assert baseline.read_bytes() == baseline_bytes
    assert (tmp_path / "baseline.json").read_bytes() == baseline_bytes
    assert source.read_bytes() == original
    if alias == "report-symlink":
        assert report.is_symlink()
    elif alias == "baseline-symlink":
        assert baseline.is_symlink()
