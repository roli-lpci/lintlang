"""Deterministic, count-limited baselines for existing structural findings.

Only relative source paths and hashes are persisted. Matching includes the exact
finding location and message, so detector or source changes conservatively remain
visible. HERM scores and input errors are never changed by a baseline.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import __version__
from .patterns import Finding
from .scanner import ScanResult

SCHEMA = "lintlang/baseline-v1"


class BaselineError(ValueError):
    """A baseline or its source paths cannot be used safely."""


def _valid_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    if any(ord(character) < 32 for character in value):
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and not PureWindowsPath(value).drive
        and path.as_posix() == value
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def _validate(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"schema", "generator", "entries"}:
        raise BaselineError("Baseline must contain exactly schema, generator, and entries")
    if payload["schema"] != SCHEMA:
        raise BaselineError(f"Unsupported baseline schema; expected {SCHEMA}")
    if not isinstance(payload["generator"], str) or not payload["generator"].strip():
        raise BaselineError("Baseline generator must be a nonempty version string")
    if not isinstance(payload["entries"], list):
        raise BaselineError("Baseline entries must be a list")

    entries = []
    seen = set()
    for index, entry in enumerate(payload["entries"]):
        if not isinstance(entry, dict) or set(entry) != {"path", "fingerprint", "count"}:
            raise BaselineError(f"Baseline entry {index} must contain exactly path, fingerprint, and count")
        if not _valid_path(entry["path"]):
            raise BaselineError(f"Baseline entry {index} requires a canonical relative POSIX file path")
        fingerprint = entry["fingerprint"]
        if not isinstance(fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
            raise BaselineError(f"Baseline entry {index} requires a lowercase SHA-256 fingerprint")
        if type(entry["count"]) is not int or entry["count"] <= 0:
            raise BaselineError(f"Baseline entry {index} count must be a positive integer")
        identity = (entry["path"], fingerprint)
        if identity in seen:
            raise BaselineError(f"Baseline entry {index} duplicates a path and fingerprint")
        seen.add(identity)
        entries.append(dict(entry))
    return {
        "schema": SCHEMA,
        "generator": payload["generator"],
        "entries": sorted(entries, key=lambda entry: (entry["path"], entry["fingerprint"])),
    }


def _source_path(source: str, root: Path) -> str:
    try:
        relative = Path(source).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError) as error:
        raise BaselineError(f"Baseline source must be inside the root: {source}") from error
    if not _valid_path(relative):
        raise BaselineError(f"Baseline source requires a relative file path: {source}")
    return relative


def _fingerprint(finding: Finding) -> str:
    identity = {
        "code": finding.code,
        "severity": finding.severity.value,
        "location": finding.location,
        "description": finding.description,
        "evidence": finding.evidence,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_baseline(results: dict[str, ScanResult], root: Path) -> dict:
    """Record current findings, rejecting empty scans and any input failure.

    Aliases of one canonical file do not multiply the recorded allowance. Each
    fingerprint keeps the maximum count from any single result for that file.
    """
    if not results:
        raise BaselineError("Cannot create a baseline from an empty scan")
    if any(result.input_error is not None for result in results.values()):
        raise BaselineError("Cannot create a baseline while any input has an error")
    counts: dict[str, Counter[str]] = {}
    for result in results.values():
        path = _source_path(result.file, root)
        findings = Counter(_fingerprint(finding) for finding in result.structural_findings)
        counts[path] = counts.get(path, Counter()) | findings
    return _validate({
        "schema": SCHEMA,
        "generator": __version__,
        "entries": [
            {"path": path, "fingerprint": fingerprint, "count": count}
            for path, findings in counts.items()
            for fingerprint, count in findings.items()
        ],
    })


def write_baseline(path: Path, payload: dict) -> None:
    """Atomically publish a complete baseline without replacing any existing path."""
    validated = _validate(payload)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(validated, stream, indent=2, sort_keys=True, ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link publishes the completed file and atomically fails if the
        # destination exists, including a dangling symlink. replace() would clobber.
        os.link(temporary, path)
    except (OSError, UnicodeError) as error:
        raise BaselineError(f"Cannot write baseline: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BaselineError("Baseline JSON contains a duplicate object key")
        result[key] = value
    return result


def load_baseline(path: Path) -> dict:
    """Read a strictly validated baseline; unknown fields and versions are errors."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    except (OSError, ValueError, RecursionError) as error:
        raise BaselineError(f"Cannot read baseline: {error}") from error
    return _validate(payload)


def apply_baseline(results: dict[str, ScanResult], payload: dict, root: Path) -> dict[str, int]:
    """Remove counted exact matches in place and return suppressed counts per key.

    All paths are checked before results are changed. An input error is retained
    as-is, with zero suppressions, regardless of any recorded allowance.
    """
    validated = _validate(payload)
    remaining = Counter({
        (entry["path"], entry["fingerprint"]): entry["count"] for entry in validated["entries"]
    })
    paths = {
        key: _source_path(result.file, root)
        for key, result in results.items()
        if result.input_error is None
    }
    suppressed = {key: 0 for key in results}
    for key in sorted(paths):
        result = results[key]
        unmatched = []
        for finding in result.structural_findings:
            identity = (paths[key], _fingerprint(finding))
            if remaining[identity] > 0:
                remaining[identity] -= 1
                suppressed[key] += 1
            else:
                unmatched.append(finding)
        result.structural_findings = unmatched
    return suppressed
