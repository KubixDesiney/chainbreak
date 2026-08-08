"""T-10: a bundle received from someone else is untrusted input. The reader
must reject an oversized line or malformed JSON with a bounded, named
exception -- never a crash, never unbounded memory growth, never ``eval``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chainbreak.core.errors import EvidenceError
from chainbreak.evidence.reader import (
    MAX_JSON_DOCUMENT_BYTES,
    MAX_LINE_BYTES,
    _load_json_document,
    _stream_jsonl,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MALICIOUS_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "bundles" / "malicious" / "01J8XKQ4V7ZP3N2M9YB6TCBAD"
)


def test_oversized_line_is_rejected_before_json_parsing() -> None:
    with pytest.raises(EvidenceError) as excinfo:
        list(_stream_jsonl(MALICIOUS_DIR / "oversized_line.jsonl"))
    assert "exceeds" in str(excinfo.value)


def test_malformed_json_line_is_rejected() -> None:
    with pytest.raises(EvidenceError) as excinfo:
        list(_stream_jsonl(MALICIOUS_DIR / "malformed_line.jsonl"))
    assert "invalid JSON" in str(excinfo.value)


def test_wellformed_line_streams_normally() -> None:
    records = list(_stream_jsonl(MALICIOUS_DIR / "wellformed_line.jsonl"))
    assert records == [{"ok": True}]


def test_missing_file_streams_as_empty() -> None:
    assert list(_stream_jsonl(MALICIOUS_DIR / "does_not_exist.jsonl")) == []


def test_oversized_single_document_is_rejected(tmp_path: Path) -> None:
    huge = tmp_path / "huge.json"
    huge.write_text(
        json.dumps({"padding": "x" * (MAX_JSON_DOCUMENT_BYTES + 1024)}), encoding="utf-8"
    )
    with pytest.raises(EvidenceError):
        _load_json_document(huge)


def test_malformed_single_document_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(EvidenceError):
        _load_json_document(bad)


def test_streaming_does_not_load_the_whole_file_at_once(tmp_path: Path) -> None:
    """A regression guard on the streaming contract itself: the function must
    be a generator (lazy), not a list-returning function that already
    exhausted memory before the first bounds check ever ran."""
    import inspect

    assert inspect.isgeneratorfunction(_stream_jsonl)


def test_a_hostile_line_size_exactly_at_the_boundary_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "boundary.jsonl"
    overhead = len(json.dumps({"k": ""}).encode("utf-8"))
    payload = "x" * (MAX_LINE_BYTES - overhead)
    line = json.dumps({"k": payload})
    assert len(line.encode("utf-8")) == MAX_LINE_BYTES
    path.write_text(line + "\n", encoding="utf-8")
    records = list(_stream_jsonl(path))
    assert records[0]["k"] == payload


def test_findings_reader_rejects_a_structurally_invalid_finding(tmp_path: Path) -> None:
    from chainbreak.evidence.reader import read_findings

    bad_findings = tmp_path / "findings.json"
    bad_findings.write_text(
        json.dumps({"findings": [{"finding_id": "fnd_01", "type": "NOT_A_REAL_TYPE"}]}),
        encoding="utf-8",
    )
    with pytest.raises(EvidenceError):
        read_findings(bad_findings)
