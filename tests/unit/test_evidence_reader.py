"""Reader-side error paths not already covered by test_bundle_ingest_safety.py
(which targets the low-level streaming primitives) or test_evidence_schema.py
(which targets the golden-bundle happy path)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chainbreak.core.errors import EvidenceError
from chainbreak.evidence.reader import (
    read_credentials,
    read_events,
    read_findings,
    read_manifest,
    read_observations,
    read_policy_states,
)

pytestmark = pytest.mark.unit


def test_read_manifest_rejects_a_structurally_invalid_document(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"run_id": "x"}), encoding="utf-8")  # missing required fields
    with pytest.raises(EvidenceError):
        read_manifest(path)


def test_read_findings_rejects_a_non_object_document(tmp_path: Path) -> None:
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    with pytest.raises(EvidenceError):
        read_findings(path)


def test_read_findings_rejects_a_malformed_detector_check(tmp_path: Path) -> None:
    path = tmp_path / "findings.json"
    path.write_text(
        json.dumps({"findings": [], "detector_checks": [{"negative_control": "nc-01"}]}),
        encoding="utf-8",
    )
    with pytest.raises(EvidenceError):
        read_findings(path)


def test_read_findings_accepts_a_well_formed_document(tmp_path: Path) -> None:
    path = tmp_path / "findings.json"
    path.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "fnd_01",
                        "type": "EXPECTED_BEHAVIOR",
                        "confidence": "HIGH",
                        "severity_hint": "INFORMATIONAL",
                        "subject_kind": "identity",
                        "observation": "matched expectation",
                    }
                ],
                "detector_checks": [
                    {
                        "negative_control": "nc-01",
                        "expected": "AUTHORITY_EXPANSION",
                        "produced": True,
                        "result": "DETECTOR_OK",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    document = read_findings(path)
    assert document["findings"][0]["finding_id"] == "fnd_01"


def test_read_events_streams_bare_dicts(tmp_path: Path) -> None:
    (tmp_path / "events.jsonl").write_text(
        json.dumps({"kind": "RUN_STARTED"}) + "\n", encoding="utf-8"
    )
    events = list(read_events(tmp_path))
    assert events == [{"kind": "RUN_STARTED"}]


def test_read_observations_rejects_an_invalid_record(tmp_path: Path) -> None:
    (tmp_path / "observations.jsonl").write_text(
        json.dumps({"not": "a valid observation"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(EvidenceError):
        list(read_observations(tmp_path))


def test_read_policy_states_rejects_an_invalid_record(tmp_path: Path) -> None:
    (tmp_path / "policy_states.jsonl").write_text(
        json.dumps({"not": "a valid snapshot"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(EvidenceError):
        list(read_policy_states(tmp_path))


def test_read_credentials_rejects_an_invalid_record(tmp_path: Path) -> None:
    (tmp_path / "credentials.jsonl").write_text(
        json.dumps({"not": "a valid credential"}) + "\n", encoding="utf-8"
    )
    with pytest.raises(EvidenceError):
        list(read_credentials(tmp_path))
