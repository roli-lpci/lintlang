"""Behavior and adversarial cases for structural-finding adoption baselines."""

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from lintlang import __version__
from lintlang.baseline import SCHEMA, BaselineError, apply_baseline, create_baseline, load_baseline, write_baseline
from lintlang.herm import score_text
from lintlang.patterns import Finding, Severity, SourceRegion
from lintlang.scanner import ScanResult


def finding(**changes):
    defaults = {
        "pattern_id": "H1",
        "sub_id": "H1.6",
        "pattern_name": "Tool Description Ambiguity",
        "severity": Severity.HIGH,
        "location": "tools[0].description",
        "description": "Private description: alpha-secret",
        "suggestion": "Private suggestion: bravo-secret",
        "evidence": "Private prompt excerpt: charlie-secret",
    }
    defaults.update(changes)
    return Finding(**defaults)


def result(path, findings=(), error=None):
    herm = score_text("", source_path=str(path))
    return ScanResult(str(path), herm.score, herm, list(findings), error)


def payload():
    return {
        "schema": SCHEMA,
        "generator": __version__,
        "entries": [{"path": "agent.yaml", "fingerprint": "a" * 64, "count": 1}],
    }


def test_generation_is_deterministic_and_omits_private_content(tmp_path):
    first = result(tmp_path / "z.prompt", [finding(), finding(), finding(evidence="different")])
    second = result(tmp_path / "nested" / "a.yaml", [finding()])
    forward = create_baseline({"z": first, "a": second}, tmp_path)
    backward = create_baseline({"a": second, "z": result(first.file, reversed(first.structural_findings))}, tmp_path)
    assert forward == backward
    assert forward["entries"] == sorted(forward["entries"], key=lambda entry: (entry["path"], entry["fingerprint"]))
    assert sorted(entry["count"] for entry in forward["entries"]) == [1, 1, 2]
    write_baseline(tmp_path / "one.json", forward)
    write_baseline(tmp_path / "two.json", backward)
    contents = (tmp_path / "one.json").read_text()
    assert contents == (tmp_path / "two.json").read_text()
    assert contents.endswith("\n")
    for secret in ["alpha-secret", "bravo-secret", "charlie-secret", str(tmp_path), "tools[0].description"]:
        assert secret not in contents
    assert load_baseline(tmp_path / "one.json") == forward


def test_fingerprint_has_documented_canonical_identity(tmp_path):
    item = finding()
    expected = hashlib.sha256(json.dumps({
        "code": item.code,
        "severity": item.severity.value,
        "location": item.location,
        "description": item.description,
        "evidence": item.evidence,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    baseline = create_baseline({"file": result(tmp_path / "agent.yaml", [item])}, tmp_path)
    assert baseline["entries"][0]["fingerprint"] == expected


@pytest.mark.parametrize("changes", [
    {"severity": Severity.CRITICAL},
    {"sub_id": "H1.7"},
    {"sub_id": "", "pattern_id": "H2"},
    {"location": "tools[1].description"},
    {"description": "Reworded diagnosis"},
    {"evidence": "Changed evidence"},
])
def test_changed_identity_remains_new(tmp_path, changes):
    path = tmp_path / "agent.yaml"
    baseline = create_baseline({str(path): result(path, [finding()])}, tmp_path)
    changed = finding(**changes)
    current = {str(path): result(path, [changed])}
    assert apply_baseline(current, baseline, tmp_path) == {str(path): 0}
    assert current[str(path)].structural_findings == [changed]


def test_suggestion_region_and_display_name_do_not_change_identity(tmp_path):
    path = tmp_path / "agent.yaml"
    baseline = create_baseline({"key": result(path, [finding()])}, tmp_path)
    current = {"key": result(path, [finding(
        suggestion="Updated guidance", source_region=SourceRegion(12, 15), pattern_name="New display name",
    )])}
    herm = current["key"].herm
    score = current["key"].score
    assert apply_baseline(current, baseline, tmp_path) == {"key": 1}
    assert current["key"].structural_findings == []
    assert current["key"].herm is herm
    assert current["key"].score == score


def test_count_budget_new_findings_and_different_files(tmp_path):
    path = tmp_path / "agent.yaml"
    baseline = create_baseline({"original": result(path, [finding(), finding()])}, tmp_path)
    extra = finding(evidence="new finding")
    current = {
        "original": result(path, [finding(), extra, finding(), finding()]),
        "different": result(tmp_path / "other.yaml", [finding()]),
    }
    assert apply_baseline(current, baseline, tmp_path) == {"original": 2, "different": 0}
    assert current["original"].structural_findings == [extra, finding()]
    assert current["different"].structural_findings == [finding()]


def test_aliases_share_allowance_on_generation_and_application(tmp_path):
    source = tmp_path / "agent.yaml"
    source.touch()
    alias = tmp_path / "alias.yaml"
    alias.symlink_to(source)
    baseline = create_baseline({
        "first": result(source, [finding()]),
        "second": result(alias, [finding(), finding()]),
    }, tmp_path)
    assert len(baseline["entries"]) == 1
    assert baseline["entries"][0]["path"] == "agent.yaml"
    assert baseline["entries"][0]["count"] == 2
    current = {"second": result(alias, [finding(), finding()]), "first": result(source, [finding()])}
    assert apply_baseline(current, baseline, tmp_path) == {"second": 1, "first": 1}
    assert current["first"].structural_findings == []
    assert current["second"].structural_findings == [finding()]


def test_relative_source_paths_follow_scan_path_semantics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    baseline = create_baseline({"key": result(Path("config") / "agent.yaml", [finding()])}, Path("config"))
    assert baseline["entries"][0]["path"] == "agent.yaml"


def test_no_findings_is_a_valid_baseline_but_empty_scan_is_not(tmp_path):
    with pytest.raises(BaselineError, match="empty scan"):
        create_baseline({}, tmp_path)
    baseline = create_baseline({"key": result(tmp_path / "agent.yaml")}, tmp_path)
    assert baseline["entries"] == []
    current = {"key": result(tmp_path / "agent.yaml", [finding()])}
    assert apply_baseline(current, baseline, tmp_path) == {"key": 0}
    assert current["key"].structural_findings == [finding()]


def test_input_errors_reject_generation_and_are_never_suppressed(tmp_path):
    path = tmp_path / "agent.yaml"
    clean = result(path, [finding()])
    baseline = create_baseline({"key": clean}, tmp_path)
    failed = replace(clean, input_error="Cannot parse source")
    with pytest.raises(BaselineError, match="input has an error"):
        create_baseline({"clean": clean, "failed": failed}, tmp_path)
    current = {"failed": failed, "clean": clean}
    assert apply_baseline(current, baseline, tmp_path) == {"failed": 0, "clean": 1}
    assert failed.input_error == "Cannot parse source"
    assert failed.structural_findings == [finding()]


@pytest.mark.parametrize("through_symlink", [False, True])
def test_outside_sources_are_rejected_before_any_mutation(tmp_path, through_symlink):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.touch()
    source = outside
    if through_symlink:
        source = root / "escape.yaml"
        source.symlink_to(outside)
    valid = result(root / "valid.yaml", [finding()])
    baseline = create_baseline({"valid": valid}, root)
    results = {"valid": valid, "outside": result(source, [finding()])}
    with pytest.raises(BaselineError, match="inside the root"):
        create_baseline(results, root)
    with pytest.raises(BaselineError, match="inside the root"):
        apply_baseline(results, baseline, root)
    assert valid.structural_findings == [finding()]


@pytest.mark.parametrize("invalid", [
    None, [], "baseline", {},
    {"schema": SCHEMA, "entries": []},
    {"schema": "lintlang/baseline-v2", "generator": "1", "entries": []},
    {"schema": SCHEMA, "generator": 1, "entries": []},
    {"schema": SCHEMA, "generator": " ", "entries": []},
    {"schema": SCHEMA, "generator": "1", "entries": {}},
    {"schema": SCHEMA, "generator": "1", "entries": [], "ignore_all": True},
])
def test_reject_invalid_top_level(tmp_path, invalid):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(invalid))
    with pytest.raises(BaselineError):
        load_baseline(path)


@pytest.mark.parametrize(("field", "value"), [
    ("path", value) for value in [
        None, True, 12, "", ".", "..", "../agent.yaml", "/agent.yaml", "a/../b.yaml", "./agent.yaml",
        "a//b.yaml", "agent.yaml/", "a/./b.yaml", "C:/agent.yaml", "C:agent.yaml", "a\\b.yaml",
        "//server/agent.yaml", "agent\x00.yaml", "agent\n.yaml",
    ]
] + [
    ("fingerprint", value) for value in [None, 123, True, "", "*", "a" * 63, "a" * 65, "A" * 64, "g" * 64]
] + [
    ("count", value) for value in [None, "1", True, False, 0, -1, 1.0, float("inf")]
])
def test_reject_invalid_entry_values(tmp_path, field, value):
    invalid = payload()
    invalid["entries"][0][field] = value
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(invalid))
    with pytest.raises(BaselineError):
        load_baseline(path)


@pytest.mark.parametrize("entry", [None, [], "all", {}, {"path": "agent.yaml", "fingerprint": "a" * 64}])
def test_reject_invalid_entry_shapes(tmp_path, entry):
    invalid = payload()
    invalid["entries"] = [entry]
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(invalid))
    with pytest.raises(BaselineError):
        load_baseline(path)


def test_reject_extra_fields_duplicate_entries_and_json_keys(tmp_path):
    invalid = payload()
    invalid["entries"][0]["ignore"] = True
    with pytest.raises(BaselineError):
        apply_baseline({}, invalid, tmp_path)
    invalid = payload()
    invalid["entries"].append(copy.deepcopy(invalid["entries"][0]))
    with pytest.raises(BaselineError, match="duplicates"):
        write_baseline(tmp_path / "invalid.json", invalid)
    assert not (tmp_path / "invalid.json").exists()
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"bad","schema":"lintlang/baseline-v1","generator":"1","entries":[]}')
    with pytest.raises(BaselineError, match="duplicate object key"):
        load_baseline(path)


@pytest.mark.parametrize("contents", ["{", "", "null", "{} {}"])
def test_load_invalid_json(tmp_path, contents):
    path = tmp_path / "baseline.json"
    path.write_text(contents)
    with pytest.raises(BaselineError):
        load_baseline(path)


def test_load_missing_file_and_invalid_utf8(tmp_path):
    with pytest.raises(BaselineError):
        load_baseline(tmp_path / "missing.json")
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff")
    with pytest.raises(BaselineError):
        load_baseline(path)


def test_excessively_nested_json_reports_baseline_error(tmp_path):
    path = tmp_path / "nested.json"
    path.write_text("[" * 10000 + "0" + "]" * 10000)
    with pytest.raises(BaselineError):
        load_baseline(path)


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "dangling-symlink"])
def test_write_never_clobbers_existing_destination(tmp_path, kind):
    destination = tmp_path / "baseline.json"
    target = tmp_path / "target"
    if kind == "file":
        destination.write_text("existing baseline")
    elif kind == "directory":
        destination.mkdir()
    else:
        if kind == "symlink":
            target.write_text("private data")
        destination.symlink_to(target)
    before = sorted(path.name for path in tmp_path.iterdir())
    with pytest.raises(BaselineError, match="Cannot write baseline"):
        write_baseline(destination, payload())
    assert sorted(path.name for path in tmp_path.iterdir()) == before
    if kind == "file":
        assert destination.read_text() == "existing baseline"
    elif kind == "symlink":
        assert destination.is_symlink()
        assert target.read_text() == "private data"
    elif kind == "dangling-symlink":
        assert destination.is_symlink()
        assert not target.exists()
    else:
        assert destination.is_dir()


def test_failed_write_leaves_no_partial_destination_or_temporary_file(tmp_path, monkeypatch):
    def fail_sync(_descriptor):
        raise OSError("simulated disk error")

    monkeypatch.setattr("lintlang.baseline.os.fsync", fail_sync)
    with pytest.raises(BaselineError, match="simulated disk error"):
        write_baseline(tmp_path / "baseline.json", payload())
    assert list(tmp_path.iterdir()) == []


def test_invalid_payload_apply_is_atomic(tmp_path):
    current = {"key": result(tmp_path / "agent.yaml", [finding()])}
    invalid = create_baseline(current, tmp_path)
    invalid["entries"][0]["count"] = True
    with pytest.raises(BaselineError):
        apply_baseline(current, invalid, tmp_path)
    assert current["key"].structural_findings == [finding()]


def test_literal_glob_path_cannot_match_unrelated_files(tmp_path):
    wildcard = result(tmp_path / "*.yaml", [finding()])
    baseline = create_baseline({"wildcard": wildcard}, tmp_path)
    current = {"key": result(tmp_path / "agent.yaml", [finding()])}
    assert apply_baseline(current, baseline, tmp_path) == {"key": 0}
    assert current["key"].structural_findings == [finding()]
