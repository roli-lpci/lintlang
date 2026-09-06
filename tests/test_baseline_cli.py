"""Baseline adoption through the real CLI, including output and error contracts."""

import json
import shutil

import pytest

from lintlang.cli import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    source = tmp_path / "agent.yaml"
    source.write_text("system_prompt: Keep trying until it works.\n")
    return tmp_path


def scan(capsys, *args):
    status = main(["scan", *args, "--format", "json"])
    output = capsys.readouterr()
    return status, json.loads(output.out), output.err


def baseline(capsys):
    status, original, _ = scan(capsys, "agent.yaml", "--write-baseline", "baseline.json")
    assert status == 0
    assert original[0]["structural_findings"]
    return original[0]


def test_existing_findings_acknowledged_new_file_blocks_and_herm_unchanged(project, capsys):
    original = baseline(capsys)
    status, data, _ = scan(capsys, ".", "--baseline", "baseline.json", "--fail-on", "review")
    assert status == 0
    assert len(data) == 1  # The stored baseline is not an instruction input.
    assert data[0]["structural_findings"] == []
    assert data[0]["baseline"]["suppressed"] == len(original["structural_findings"])
    assert data[0]["herm"] == original["herm"]
    assert "baseline" not in original

    shutil.copyfile("agent.yaml", "new-agent.yaml")
    status, data, _ = scan(capsys, ".", "--baseline", "baseline.json", "--fail-on", "review")
    assert status == 1
    new = next(result for result in data if result["file"].endswith("new-agent.yaml"))
    assert new["structural_findings"]
    assert new["baseline"]["suppressed"] == 0


def test_baseline_portable_to_new_checkout_and_git_subdirectory(project, tmp_path_factory, monkeypatch, capsys):
    (project / "configs").mkdir()
    (project / "agent.yaml").rename(project / "configs/agent.yaml")
    assert scan(capsys, "configs", "--write-baseline", "baseline.json")[0] == 0
    copied = tmp_path_factory.mktemp("checkout")
    shutil.copytree(project, copied, dirs_exist_ok=True)
    monkeypatch.chdir(copied / "configs")
    status, data, _ = scan(capsys, "agent.yaml", "--baseline", "../baseline.json", "--fail-on", "review")
    assert status == 0
    assert data[0]["baseline"]["suppressed"] > 0


def test_input_failure_never_creates_or_is_hidden_by_baseline(project, capsys):
    original = baseline(capsys)
    status, data, _ = scan(capsys, "agent.yaml", "missing.yaml", "--baseline", "baseline.json")
    assert status == 1
    assert data[0]["herm"] == original["herm"]
    assert data[1]["verdict"] == "ERROR"
    assert data[1]["baseline"]["suppressed"] == 0
    assert scan(capsys, "agent.yaml", "missing.yaml", "--write-baseline", "candidate.json")[0] == 1
    assert not (project / "candidate.json").exists()


def test_empty_scan_and_existing_destination_cannot_write(project, capsys):
    (project / "empty").mkdir()
    assert scan(capsys, "empty", "--write-baseline", "empty.json")[0] == 1
    assert not (project / "empty.json").exists()
    baseline(capsys)
    before = (project / "baseline.json").read_bytes()
    assert scan(capsys, "agent.yaml", "--write-baseline", "baseline.json")[0] == 1
    assert (project / "baseline.json").read_bytes() == before


@pytest.mark.parametrize("output_format", ["terminal", "markdown"])
def test_human_output_states_verdict_scope(project, capsys, output_format):
    baseline(capsys)
    assert main(["scan", "agent.yaml", "--baseline", "baseline.json", "--format", output_format]) == 0
    assert "verdict covers remaining findings" in capsys.readouterr().out


def test_sarif_reports_baseline_scope_and_empty_results(project, capsys):
    baseline(capsys)
    assert main(["scan", "agent.yaml", "--baseline", "baseline.json", "--format", "sarif"]) == 0
    run = json.loads(capsys.readouterr().out)["runs"][0]
    assert run["results"] == []
    assert run["properties"]["lintlangBaseline"]["suppressed"] > 0
    assert run["properties"]["lintlangBaseline"]["verdictScope"] == "remaining findings"


def test_baseline_does_not_bypass_legacy_quality_gate(project, capsys):
    original = baseline(capsys)
    threshold = str(original["herm"]["score"] + 1)
    assert scan(capsys, "agent.yaml", "--baseline", "baseline.json", "--fail-under", threshold)[0] == 1


def test_repeated_cli_aliases_do_not_duplicate_output_or_allowance(project, capsys):
    original = baseline(capsys)
    status, data, _ = scan(capsys, "agent.yaml", str(project / "agent.yaml"), "--baseline", "baseline.json")
    assert status == 0
    assert len(data) == 1
    assert data[0]["baseline"]["suppressed"] == len(original["structural_findings"])
